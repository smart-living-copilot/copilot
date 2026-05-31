from typing import Any

from pydantic import BaseModel, Field


class ExecuteRequest(BaseModel):
    session_id: str
    code: str


class WotCall(BaseModel):
    type: str
    thing_id: str
    name: str
    ok: bool
    input: Any | None = None
    value: Any | None = None
    uri_variables: dict[str, Any] | None = None


class ExecuteResponse(BaseModel):
    stdout: str
    images: list[str]
    plotly: list[str]
    wot_calls: list[WotCall] = Field(default_factory=list)
