from pydantic import BaseModel


class ExecuteRequest(BaseModel):
    session_id: str
    code: str


class ExecuteResponse(BaseModel):
    stdout: str
    images: list[str]
    plotly: list[str]
