from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any, Literal, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field


class SparqlDraft(BaseModel):
    query: str = Field(description="A complete read-only SPARQL query")
    rationale: str = Field(default="", description="Brief reason for the query shape")


class SparqlSummary(BaseModel):
    summary: str = Field(description="Compact natural-language summary of the SPARQL result")


class SparqlQueryState(TypedDict, total=False):
    intent: str
    endpoints: list[str]
    limit: int
    endpoint_context: list[dict[str, Any]]
    attempts: list[dict[str, Any]]
    draft_query: str
    last_error: str
    last_result: dict[str, Any]
    final_summary: str
    status: Literal["ok", "partial", "failed"]
    max_attempts: int


EndpointContextLoader = Callable[[list[str]], list[dict[str, Any]]]
RdfExecutor = Callable[..., Any]

_DRAFT_SYSTEM_PROMPT = """\
You draft SPARQL for the Smart Living Copilot.

Rules:
- Use only read-only SPARQL: SELECT, ASK, CONSTRUCT, or DESCRIBE.
- For federated endpoint Things, write SERVICE <endpoint-thing-id> blocks.
- Prefer SERVICE SILENT when a remote endpoint is optional or might be slow.
- Never invent external endpoint URLs; only use provided endpoint Thing ids.
- Keep result size bounded and compatible with the requested limit.
- Include explicit PREFIX declarations for every prefixed name you use.
- Use endpoint examples as few-shot patterns when available.
- If repairing, address the exact prior error or empty-result cause.
"""

_SUMMARY_SYSTEM_PROMPT = """\
Summarize the SPARQL tool result for the parent agent.
Be concise, mention if the result is partial or empty, and do not invent facts.
"""


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _as_model_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {}


def _result_is_empty(result: dict[str, Any]) -> bool:
    result_type = result.get("type")
    if result_type == "ask":
        return False
    if result_type == "select":
        rows = result.get("rows")
        return not isinstance(rows, list) or not rows
    if result_type in {"construct", "describe"}:
        rdf = result.get("rdf")
        return not isinstance(rdf, str) or not rdf.strip()
    return False


def _result_status(result: dict[str, Any]) -> Literal["ok", "partial"]:
    return "partial" if result.get("truncated") else "ok"


def _attempt_result_summary(result: dict[str, Any]) -> dict[str, Any]:
    result_type = result.get("type")
    summary: dict[str, Any] = {
        "type": result_type,
        "truncated": bool(result.get("truncated")),
    }
    if result_type == "select":
        rows = result.get("rows")
        summary["row_count"] = len(rows) if isinstance(rows, list) else 0
    elif result_type == "ask":
        summary["boolean"] = bool(result.get("boolean"))
    elif result_type in {"construct", "describe"}:
        rdf = result.get("rdf")
        summary["rdf_bytes"] = len(rdf.encode("utf-8")) if isinstance(rdf, str) else 0
    return summary


def _append_attempt(
    state: SparqlQueryState,
    *,
    query: str,
    status: str,
    error: str | None = None,
    result: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    attempts = list(state.get("attempts", []))
    attempt: dict[str, Any] = {
        "attempt": len(attempts) + 1,
        "query": query,
        "status": status,
    }
    if error:
        attempt["error"] = error
    if result is not None:
        attempt["result"] = _attempt_result_summary(result)
    attempts.append(attempt)
    return attempts


def _draft_prompt(state: SparqlQueryState) -> list[Any]:
    payload = {
        "intent": state.get("intent", ""),
        "limit": state.get("limit", 50),
        "endpoints": state.get("endpoints", []),
        "endpoint_context": state.get("endpoint_context", []),
        "attempts": state.get("attempts", []),
        "previous_error": state.get("last_error", ""),
    }
    return [
        SystemMessage(content=_DRAFT_SYSTEM_PROMPT),
        HumanMessage(content=_json_dumps(payload)),
    ]


def _summary_prompt(state: SparqlQueryState) -> list[Any]:
    payload = {
        "intent": state.get("intent", ""),
        "status": state.get("status", "failed"),
        "query": state.get("draft_query", ""),
        "endpoints": state.get("endpoints", []),
        "attempts": state.get("attempts", []),
        "result": state.get("last_result"),
        "error": state.get("last_error", ""),
    }
    return [
        SystemMessage(content=_SUMMARY_SYSTEM_PROMPT),
        HumanMessage(content=_json_dumps(payload)),
    ]


def build_sparql_query_subgraph(
    *,
    llm: Any,
    rdf_executor: RdfExecutor,
    endpoint_context_loader: EndpointContextLoader,
):
    draft_llm = llm.with_structured_output(SparqlDraft)
    summary_llm = llm.with_structured_output(SparqlSummary)

    async def assemble_context(state: SparqlQueryState) -> dict[str, Any]:
        endpoints = state.get("endpoints", [])
        try:
            endpoint_context = await asyncio.to_thread(endpoint_context_loader, endpoints)
        except Exception as exc:
            return {
                "endpoint_context": [],
                "last_error": str(exc),
                "status": "failed",
            }
        return {
            "endpoint_context": endpoint_context,
            "last_error": "",
        }

    async def draft_query(state: SparqlQueryState) -> dict[str, Any]:
        try:
            raw_draft = await draft_llm.ainvoke(_draft_prompt(state))
            draft = _as_model_dict(raw_draft)
            query = str(draft.get("query") or "").strip()
            if not query:
                raise ValueError("SPARQL draft was empty")
        except Exception as exc:
            return {
                "last_error": f"SPARQL draft failed: {exc}",
                "status": "failed",
            }
        return {
            "draft_query": query,
            "last_error": "",
        }

    async def execute_query(state: SparqlQueryState) -> dict[str, Any]:
        query = state.get("draft_query", "")
        try:
            result = await rdf_executor(
                query=query,
                endpoints=state.get("endpoints", []),
                limit=state.get("limit", 50),
            )
        except Exception as exc:
            error = str(exc)
            return {
                "last_error": error,
                "attempts": _append_attempt(
                    state,
                    query=query,
                    status="error",
                    error=error,
                ),
            }

        if _result_is_empty(result):
            error = "SPARQL query returned an empty result"
            return {
                "last_error": error,
                "last_result": result,
                "attempts": _append_attempt(
                    state,
                    query=query,
                    status="empty",
                    error=error,
                    result=result,
                ),
            }

        return {
            "last_error": "",
            "last_result": result,
            "status": _result_status(result),
            "attempts": _append_attempt(
                state,
                query=query,
                status="ok",
                result=result,
            ),
        }

    async def summarize(state: SparqlQueryState) -> dict[str, Any]:
        result = state.get("last_result")
        last_error = state.get("last_error", "")
        if last_error and not result:
            return {
                "status": "failed",
                "final_summary": f"SPARQL query failed: {last_error}",
            }

        status: Literal["ok", "partial", "failed"] = (
            "failed" if last_error else state.get("status", "ok")
        )
        try:
            raw_summary = await summary_llm.ainvoke(_summary_prompt({**state, "status": status}))
            summary = str(_as_model_dict(raw_summary).get("summary") or "").strip()
        except Exception:
            summary = ""
        if not summary:
            summary = "SPARQL query completed." if not last_error else f"SPARQL query failed: {last_error}"

        return {
            "status": status,
            "final_summary": summary,
        }

    def route_after_context(state: SparqlQueryState) -> str:
        return "summarize" if state.get("last_error") else "draft"

    def route_after_draft(state: SparqlQueryState) -> str:
        return "summarize" if state.get("last_error") and not state.get("draft_query") else "execute"

    def route_after_execute(state: SparqlQueryState) -> str:
        if not state.get("last_error"):
            return "summarize"
        if len(state.get("attempts", [])) >= state.get("max_attempts", 3):
            return "summarize"
        return "draft"

    graph = StateGraph(SparqlQueryState)
    graph.add_node("assemble_context", assemble_context)
    graph.add_node("draft", draft_query)
    graph.add_node("execute", execute_query)
    graph.add_node("summarize", summarize)
    graph.add_edge(START, "assemble_context")
    graph.add_conditional_edges(
        "assemble_context",
        route_after_context,
        {
            "draft": "draft",
            "summarize": "summarize",
        },
    )
    graph.add_conditional_edges(
        "draft",
        route_after_draft,
        {
            "execute": "execute",
            "summarize": "summarize",
        },
    )
    graph.add_conditional_edges(
        "execute",
        route_after_execute,
        {
            "draft": "draft",
            "summarize": "summarize",
        },
    )
    graph.add_edge("summarize", END)
    return graph.compile()


async def run_sparql_query_subgraph(
    *,
    intent: str,
    endpoints: list[str],
    limit: int,
    max_attempts: int,
    llm: Any,
    rdf_executor: RdfExecutor,
    endpoint_context_loader: EndpointContextLoader,
) -> dict[str, Any]:
    graph = build_sparql_query_subgraph(
        llm=llm,
        rdf_executor=rdf_executor,
        endpoint_context_loader=endpoint_context_loader,
    )
    state = await graph.ainvoke(
        {
            "intent": intent,
            "endpoints": endpoints,
            "limit": limit,
            "attempts": [],
            "max_attempts": max_attempts,
        }
    )
    return {
        "status": state.get("status", "failed"),
        "intent": intent,
        "query": state.get("draft_query", ""),
        "endpoints": endpoints,
        "attempts": state.get("attempts", []),
        "summary": state.get("final_summary", ""),
        "result": state.get("last_result"),
    }
