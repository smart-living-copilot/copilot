from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any, Literal, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from copilot.rdf.federation import service_constraint_diagnostics, service_iris


class SparqlDraft(BaseModel):
    query: str = Field(description="A complete read-only SPARQL query")
    rationale: str = Field(default="", description="Brief reason for the query shape")


class SparqlSummary(BaseModel):
    summary: str = Field(description="Compact natural-language summary of the SPARQL result")


class SparqlQueryState(TypedDict, total=False):
    intent: str
    selected_endpoints: list[str]
    limit: int
    endpoint_context: list[dict[str, Any]]
    attempts: list[dict[str, Any]]
    draft_query: str
    last_error: str
    last_error_category: str
    last_error_retryable: bool
    last_result: dict[str, Any]
    diagnostics: list[dict[str, str]]
    final_summary: str
    status: Literal["ok", "partial", "failed"]


EndpointContextLoader = Callable[[], list[dict[str, Any]]]
RdfExecutor = Callable[..., Any]

_DRAFT_SYSTEM_PROMPT = """\
You draft SPARQL for the Smart Living Copilot.

Rules:
- Use only read-only SPARQL: SELECT, ASK, CONSTRUCT, or DESCRIBE.
- For federated endpoint Things, write SERVICE <endpoint-thing-id> blocks.
- Constrain every SERVICE block's remote work inside the SERVICE block with VALUES,
  FILTER, BIND, or equivalent inline bindings; do not rely on outer joins to bound
  the remote endpoint.
- Use hard SERVICE for data required to answer the request.
- Use SERVICE SILENT only for optional enrichment where remote failure should not
  invalidate the answer.
- Never invent external endpoint URLs; only use provided endpoint Thing ids.
- Keep result size bounded and compatible with the requested limit.
- Include explicit PREFIX declarations for every prefixed name you use.
- Use endpoint examples as few-shot patterns when available.
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


def _result_status(result: dict[str, Any]) -> Literal["ok", "partial"]:
    return "partial" if result.get("truncated") else "ok"


def _bounded_repair_retries(value: int) -> int:
    return min(max(value, 0), 2)


def _known_endpoint_ids(endpoint_context: list[dict[str, Any]]) -> set[str]:
    return {
        endpoint_id
        for item in endpoint_context
        if isinstance((endpoint_id := item.get("id")), str) and endpoint_id
    }


def _selected_endpoint_ids(
    query: str,
    endpoint_context: list[dict[str, Any]],
) -> list[str]:
    known_endpoint_ids = _known_endpoint_ids(endpoint_context)
    selected: list[str] = []
    seen: set[str] = set()
    for iri in service_iris(query):
        if iri not in known_endpoint_ids or iri in seen:
            continue
        selected.append(iri)
        seen.add(iri)
    return selected


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
    diagnostics: list[dict[str, str]],
    error: str | None = None,
    error_category: str | None = None,
    result: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    attempts = list(state.get("attempts", []))
    attempt: dict[str, Any] = {
        "attempt": len(attempts) + 1,
        "query": query,
        "status": status,
        "diagnostics": diagnostics,
    }
    if error:
        attempt["error"] = error
    if error_category:
        attempt["error_category"] = error_category
    if result is not None:
        attempt["result"] = _attempt_result_summary(result)
    attempts.append(attempt)
    return attempts


def _executor_error_metadata(error: Exception) -> tuple[str, bool | None]:
    category = getattr(error, "category", "")
    retryable = getattr(error, "retryable", None)
    if isinstance(category, str) and category:
        return category, bool(retryable)
    return "", None


def _is_retryable_executor_error(error: str, *, category: str = "") -> bool:
    if category:
        return category not in {"auth", "security", "credential"}
    normalized = error.lower()
    if any(
        marker in normalized
        for marker in (
            "401",
            "403",
            "unauthorized",
            "forbidden",
            "credential",
            "security",
            "scheme",
        )
    ):
        return False
    return any(
        marker in normalized
        for marker in (
            "syntax",
            "parse",
            "endpoint thing ids",
            "service targets",
            "timeout",
            "timed out",
            "504",
            "response exceeded",
            "size limit",
            "too large",
        )
    )


def _can_retry(state: SparqlQueryState, *, max_repair_retries: int) -> bool:
    if state.get("status") != "failed":
        return False
    last_error = state.get("last_error", "")
    if not last_error:
        return False
    retryable = state.get("last_error_retryable")
    if retryable is False:
        return False
    if retryable is not True and not _is_retryable_executor_error(
        last_error,
        category=state.get("last_error_category", ""),
    ):
        return False
    return len(state.get("attempts", [])) <= max_repair_retries


def _draft_prompt(state: SparqlQueryState) -> list[Any]:
    payload = {
        "intent": state.get("intent", ""),
        "limit": state.get("limit", 50),
        "available_endpoints": state.get("endpoint_context", []),
    }
    attempts = state.get("attempts", [])
    if attempts:
        payload["repair"] = {
            "instruction": (
                "The previous SPARQL draft failed. Draft a corrected query and do not "
                "repeat the failed query unchanged."
            ),
            "last_error": state.get("last_error", ""),
            "previous_attempts": attempts,
            "latest_diagnostics": state.get("diagnostics", []),
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
        "selected_endpoints": state.get("selected_endpoints", []),
        "attempts": state.get("attempts", []),
        "result": state.get("last_result"),
        "error": state.get("last_error", ""),
    }
    return [
        SystemMessage(content=_SUMMARY_SYSTEM_PROMPT),
        HumanMessage(content=_json_dumps(payload)),
    ]


def _silence_streaming(llm: Any) -> Any:
    """Keep a subgraph-internal LLM out of the chat message stream.

    The draft/summary nodes use structured output (tool-calling). Under LangGraph
    messages-mode streaming (what CopilotKit consumes) their tool-args JSON would
    stream into the chat as transient, non-persisted messages that flash and then
    disappear on reconcile. Setting ``disable_streaming=True`` makes the model emit a
    single result instead of token chunks, so nothing surfaces to the UI — and for
    structured output we want the whole object anyway. Falls back to the original LLM
    for test doubles that lack ``model_copy``.
    """
    try:
        return llm.model_copy(update={"disable_streaming": True})
    except (AttributeError, TypeError):
        return llm


def build_sparql_query_subgraph(
    *,
    llm: Any,
    rdf_executor: RdfExecutor,
    endpoint_context_loader: EndpointContextLoader,
    max_repair_retries: int = 1,
):
    max_repair_retries = _bounded_repair_retries(max_repair_retries)
    internal_llm = _silence_streaming(llm)
    draft_llm = internal_llm.with_structured_output(SparqlDraft)
    summary_llm = internal_llm.with_structured_output(SparqlSummary)

    async def assemble_context(state: SparqlQueryState) -> dict[str, Any]:
        try:
            endpoint_context = await asyncio.to_thread(endpoint_context_loader)
        except Exception as exc:
            return {
                "endpoint_context": [],
                "selected_endpoints": [],
                "diagnostics": [],
                "last_error": str(exc),
                "last_error_category": "context",
                "last_error_retryable": False,
                "status": "failed",
            }
        return {
            "endpoint_context": endpoint_context,
            "selected_endpoints": [],
            "diagnostics": [],
            "last_error": "",
            "last_error_category": "",
            "last_error_retryable": False,
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
                "draft_query": "",
                "selected_endpoints": [],
                "diagnostics": [],
                "last_error": f"SPARQL draft failed: {exc}",
                "last_error_category": "draft",
                "last_error_retryable": False,
                "status": "failed",
            }
        return {
            "draft_query": query,
            "selected_endpoints": _selected_endpoint_ids(
                query,
                state.get("endpoint_context", []),
            ),
            "diagnostics": service_constraint_diagnostics(query),
            "last_error": "",
            "last_error_category": "",
            "last_error_retryable": False,
        }

    async def execute_query(state: SparqlQueryState) -> dict[str, Any]:
        query = state.get("draft_query", "")
        diagnostics = service_constraint_diagnostics(query)
        try:
            result = await rdf_executor(
                query=query,
                endpoints=state.get("selected_endpoints", []),
                limit=state.get("limit", 50),
            )
        except Exception as exc:
            error = str(exc)
            category, retryable = _executor_error_metadata(exc)
            return {
                "last_error": error,
                "last_error_category": category,
                "last_error_retryable": (
                    retryable
                    if retryable is not None
                    else _is_retryable_executor_error(error, category=category)
                ),
                "diagnostics": diagnostics,
                "status": "failed",
                "attempts": _append_attempt(
                    state,
                    query=query,
                    status="error",
                    diagnostics=diagnostics,
                    error=error,
                    error_category=category or None,
                ),
            }

        return {
            "last_error": "",
            "last_error_category": "",
            "last_error_retryable": False,
            "last_result": result,
            "diagnostics": diagnostics,
            "status": _result_status(result),
            "attempts": _append_attempt(
                state,
                query=query,
                status="ok",
                diagnostics=diagnostics,
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
            summary = (
                "SPARQL query completed."
                if not last_error
                else f"SPARQL query failed: {last_error}"
            )

        return {
            "status": status,
            "final_summary": summary,
        }

    def route_after_context(state: SparqlQueryState) -> str:
        return "summarize" if state.get("last_error") else "draft"

    def route_after_draft(state: SparqlQueryState) -> str:
        return (
            "summarize" if state.get("last_error") and not state.get("draft_query") else "execute"
        )

    def route_after_execute(state: SparqlQueryState) -> str:
        return "draft" if _can_retry(state, max_repair_retries=max_repair_retries) else "summarize"

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
    limit: int,
    llm: Any,
    rdf_executor: RdfExecutor,
    endpoint_context_loader: EndpointContextLoader,
    max_repair_retries: int = 1,
) -> dict[str, Any]:
    graph = build_sparql_query_subgraph(
        llm=llm,
        rdf_executor=rdf_executor,
        endpoint_context_loader=endpoint_context_loader,
        max_repair_retries=max_repair_retries,
    )
    state = await graph.ainvoke(
        {
            "intent": intent,
            "selected_endpoints": [],
            "limit": limit,
            "attempts": [],
            "diagnostics": [],
        }
    )
    return {
        "status": state.get("status", "failed"),
        "intent": intent,
        "query": state.get("draft_query", ""),
        "selected_endpoints": state.get("selected_endpoints", []),
        "attempts": state.get("attempts", []),
        "diagnostics": state.get("diagnostics", []),
        "summary": state.get("final_summary", ""),
        "result": state.get("last_result"),
    }
