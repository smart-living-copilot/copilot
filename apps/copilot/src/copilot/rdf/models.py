from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RdfQueryRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=50, ge=1, le=500)
    use_default_graph_as_union: bool = True
    endpoints: list[str] = Field(default_factory=list, max_length=20)


class RdfQueryResponse(BaseModel):
    type: Literal["select", "ask", "construct", "describe"]
    query: str
    limit: int
    truncated: bool = False
    variables: list[str] | None = None
    rows: list[dict[str, Any]] | None = None
    boolean: bool | None = None
    format: str | None = None
    rdf: str | None = None


class RdfReindexResponse(BaseModel):
    indexed: int
    failed: int = 0
    errors: list[dict[str, str]] = Field(default_factory=list)
