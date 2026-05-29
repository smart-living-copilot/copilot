"""REST proxy endpoints for WoT runtime operations (read/write property, invoke action)."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from copilot.auth import User, require_scopes
from copilot.core.config import get_settings
from copilot.runtime.client import WotRuntimeClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wot", tags=["wot-operations"])


def _client() -> WotRuntimeClient:
    return WotRuntimeClient(get_settings())


class ReadPropertyRequest(BaseModel):
    thing_id: str
    property_name: str
    uri_variables: dict[str, Any] | None = None
    form_index: int | None = None


class WritePropertyRequest(BaseModel):
    thing_id: str
    property_name: str
    value: Any = None
    value_content_type: str | None = None
    value_base64: str | None = None
    uri_variables: dict[str, Any] | None = None
    form_index: int | None = None


class InvokeActionRequest(BaseModel):
    thing_id: str
    action_name: str
    input: Any = None
    input_content_type: str | None = None
    input_base64: str | None = None
    uri_variables: dict[str, Any] | None = None
    form_index: int | None = None
    idempotency_key: str | None = None


@router.post("/read-property")
async def read_property(
    body: ReadPropertyRequest,
    _user: User = Depends(require_scopes(["things:read"])),
) -> dict[str, Any]:
    try:
        return await _client().read_property(
            thing_id=body.thing_id,
            property_name=body.property_name,
            uri_variables=body.uri_variables,
            form_index=body.form_index,
        )
    except ValueError as e:
        logger.warning("WoT runtime error in read_property: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/write-property")
async def write_property(
    body: WritePropertyRequest,
    _user: User = Depends(require_scopes(["things:write"])),
) -> dict[str, Any]:
    try:
        return await _client().write_property(
            thing_id=body.thing_id,
            property_name=body.property_name,
            value=body.value,
            value_content_type=body.value_content_type,
            value_base64=body.value_base64,
            uri_variables=body.uri_variables,
            form_index=body.form_index,
        )
    except ValueError as e:
        logger.warning("WoT runtime error in write_property: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/invoke-action")
async def invoke_action(
    body: InvokeActionRequest,
    _user: User = Depends(require_scopes(["things:write"])),
) -> dict[str, Any]:
    try:
        return await _client().invoke_action(
            thing_id=body.thing_id,
            action_name=body.action_name,
            input=body.input,
            input_content_type=body.input_content_type,
            input_base64=body.input_base64,
            uri_variables=body.uri_variables,
            form_index=body.form_index,
            idempotency_key=body.idempotency_key,
        )
    except ValueError as e:
        logger.warning("WoT runtime error in invoke_action: %s", e)
        raise HTTPException(status_code=502, detail=str(e))
