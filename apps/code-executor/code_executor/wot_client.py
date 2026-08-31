"""Sandbox-facing WoT client used by executed code."""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Callable
from typing import Any


class SandboxWotClient:
    """Synchronous client for direct WoT device interactions from the sandbox."""

    def __init__(
        self,
        base_url: str,
        token: str,
        record_call: Callable[[dict[str, Any]], None],
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"Content-Type": "application/json"}
        self._record_call = record_call
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

    def read_property(
        self,
        thing_id: str,
        property_name: str,
        uri_variables: dict[str, Any] | None = None,
    ) -> Any:
        """Read a property value from a thing."""
        return self._execute(
            path="/runtime/read-property",
            body={
                "thing_id": thing_id,
                "property_name": property_name,
                "uri_variables": uri_variables or {},
            },
            call_type="read_property",
            thing_id=thing_id,
            name=property_name,
            uri_variables=uri_variables or {},
        )

    def write_property(
        self,
        thing_id: str,
        property_name: str,
        value: Any,
        uri_variables: dict[str, Any] | None = None,
    ) -> Any:
        """Write a property value to a thing."""
        return self._execute(
            path="/runtime/write-property",
            body={
                "thing_id": thing_id,
                "property_name": property_name,
                "value": value,
                "uri_variables": uri_variables or {},
            },
            call_type="write_property",
            thing_id=thing_id,
            name=property_name,
            uri_variables=uri_variables or {},
            value=value,
        )

    def invoke_action(
        self,
        thing_id: str,
        action_name: str,
        input: Any = None,
        uri_variables: dict[str, Any] | None = None,
    ) -> Any:
        """Invoke an action on a thing."""
        input_payload = self._parse_json_input(input)
        return self._execute(
            path="/runtime/invoke-action",
            body={
                "thing_id": thing_id,
                "action_name": action_name,
                "input": input_payload,
                "uri_variables": uri_variables or {},
            },
            call_type="invoke_action",
            thing_id=thing_id,
            input_value=input_payload,
            name=action_name,
            uri_variables=uri_variables or {},
        )

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        import requests as _req

        resp = _req.post(
            f"{self._base_url}{path}",
            json=body,
            headers=self._headers,
            timeout=120,
        )
        if not resp.ok:
            try:
                detail = resp.json().get("detail", resp.text[:500])
            except Exception:
                detail = resp.text[:500]
            raise RuntimeError(f"WoT request failed ({resp.status_code}): {detail}")
        return resp.json()

    def _execute(
        self,
        *,
        path: str,
        body: dict[str, Any],
        call_type: str,
        thing_id: str,
        name: str,
        input_value: Any = None,
        uri_variables: dict[str, Any] | None = None,
        value: Any = None,
    ) -> Any:
        try:
            raw = self._post(path, body)
            payload = self._extract_payload(raw)
        except Exception:
            self._record(
                call_type,
                thing_id,
                name,
                False,
                input_value=input_value,
                uri_variables=uri_variables,
                value=value,
            )
            raise

        self._record(
            call_type,
            thing_id,
            name,
            not self._is_failure_result(payload),
            input_value=input_value,
            uri_variables=uri_variables,
            value=value,
        )
        return payload

    @staticmethod
    def _extract_payload(result: Any) -> Any:
        """Extract the useful data from a runtime response envelope."""
        if not isinstance(result, dict):
            return result
        # read/write property responses
        r = result.get("result") or result.get("completed_result")
        if isinstance(r, dict):
            payload = r.get("payload", {})
            if payload.get("kind") == "inline":
                return payload.get("data")
            if payload.get("kind") == "binary":
                encoded = payload.get("body_base64")
                if not isinstance(encoded, str):
                    raise RuntimeError("WoT runtime returned an invalid binary payload")
                try:
                    return base64.b64decode(encoded, validate=True)
                except (binascii.Error, ValueError) as exc:
                    raise RuntimeError(
                        "WoT runtime returned invalid base64 data"
                    ) from exc
            return payload
        return result

    @staticmethod
    def _is_failure_result(result: Any) -> bool:
        if isinstance(result, str):
            return result.strip().lower().startswith("error")
        if not isinstance(result, dict):
            return False
        error = result.get("error")
        return isinstance(error, str) and bool(error.strip())

    @staticmethod
    def _normalize_summary_value(value: Any) -> Any:
        if value is None:
            return None

        try:
            return json.loads(json.dumps(value, default=str))
        except Exception:
            return str(value)

    @staticmethod
    def _parse_json_input(value: Any) -> Any:
        if not isinstance(value, str):
            return value

        stripped = value.lstrip()
        if not stripped.startswith(("{", "[")):
            return value

        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    def _record(
        self,
        call_type: str,
        thing_id: str,
        name: str,
        ok: bool,
        *,
        input_value: Any = None,
        uri_variables: dict[str, Any] | None = None,
        value: Any = None,
    ) -> None:
        entry: dict[str, Any] = {
            "type": call_type,
            "thing_id": thing_id,
            "name": name,
            "ok": ok,
        }
        normalized_input = self._normalize_summary_value(input_value)
        normalized_value = self._normalize_summary_value(value)
        normalized_uri_variables = self._normalize_summary_value(uri_variables)

        if normalized_input is not None:
            entry["input"] = normalized_input
        if normalized_value is not None:
            entry["value"] = normalized_value
        if isinstance(normalized_uri_variables, dict) and normalized_uri_variables:
            entry["uri_variables"] = normalized_uri_variables

        self._record_call(entry)
