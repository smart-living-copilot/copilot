from __future__ import annotations

from fastapi import HTTPException


def virtual_record_http_error(error: Exception) -> HTTPException:
    if isinstance(error, KeyError):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, ValueError):
        return HTTPException(status_code=400, detail=str(error))
    return HTTPException(status_code=502, detail=str(error))
