"""Code executor route handlers."""

import json
import os

from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from code_executor.api.app import app
from code_executor.api.dependencies import verify_api_key
from code_executor.models import ExecuteRequest, ExecuteResponse
from code_executor.utils import plotly_json_to_html


@app.post(
    "/execute", response_model=ExecuteResponse, dependencies=[Depends(verify_api_key)]
)
async def execute(req: ExecuteRequest, request: Request):
    pool = request.app.state.pool
    try:
        result = await pool.execute(req.session_id, req.code)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return ExecuteResponse(**result)


@app.get("/artifacts/{filename}", dependencies=[Depends(verify_api_key)])
async def get_artifact(filename: str, request: Request):
    """Serve an artifact file (PNG image or Plotly HTML from JSON)."""
    settings = request.app.state.settings

    # Prevent path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = os.path.join(settings.artifacts_dir, filename)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="Artifact not found")

    if filename.endswith(".png"):
        return FileResponse(filepath, media_type="image/png")

    if filename.endswith(".json"):
        with open(filepath, "r") as f:
            fig_json = json.load(f)
        html = plotly_json_to_html(fig_json)
        return HTMLResponse(content=html)

    return FileResponse(filepath)


@app.delete("/sessions/{session_id}", dependencies=[Depends(verify_api_key)])
async def delete_session(session_id: str, request: Request):
    pool = request.app.state.pool
    await pool.shutdown(session_id)
    return {"ok": True}


@app.get("/health")
async def health(request: Request):
    pool = request.app.state.pool
    return {"status": "ok", "active_sessions": pool.active_count}
