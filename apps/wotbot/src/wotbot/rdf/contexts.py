from __future__ import annotations

from copy import deepcopy
from typing import Any

WOT_TD_11_CONTEXT_URL = "https://www.w3.org/2022/wot/td/v1.1"

_JSON_SCHEMA_CONTEXT: dict[str, Any] = {
    "td": "https://www.w3.org/2019/wot/td#",
    "jsonschema": "https://www.w3.org/2019/wot/json-schema#",
    "schema": "http://schema.org/",
    "@vocab": "https://www.w3.org/2019/wot/json-schema#",
    "type": {"@id": "@type"},
    "object": "jsonschema:ObjectSchema",
    "array": "jsonschema:ArraySchema",
    "boolean": "jsonschema:BooleanSchema",
    "string": "jsonschema:StringSchema",
    "number": "jsonschema:NumberSchema",
    "integer": "jsonschema:IntegerSchema",
    "null": "jsonschema:NullSchema",
    "title": {"@id": "td:title", "@language": "en"},
    "description": {"@id": "td:description", "@language": "en"},
    "properties": {
        "@id": "jsonschema:properties",
        "@container": "@index",
        "@index": "propertyName",
    },
    "propertyName": {"@id": "jsonschema:propertyName"},
    "items": {"@id": "jsonschema:items", "@type": "@id"},
    "required": {"@id": "jsonschema:required", "@container": "@set"},
    "enum": {"@id": "jsonschema:enum", "@container": "@set"},
    "oneOf": {"@id": "jsonschema:oneOf", "@container": "@set"},
    "allOf": {"@id": "jsonschema:allOf", "@container": "@set"},
    "anyOf": {"@id": "jsonschema:anyOf", "@container": "@set"},
    "unit": {"@id": "schema:unitCode", "@type": "@vocab"},
    "readOnly": {"@id": "jsonschema:readOnly"},
    "writeOnly": {"@id": "jsonschema:writeOnly"},
    "format": {"@id": "jsonschema:format"},
    "minimum": {"@id": "jsonschema:minimum"},
    "maximum": {"@id": "jsonschema:maximum"},
}

_SECURITY_CONTEXT: dict[str, Any] = {
    "td": "https://www.w3.org/2019/wot/td#",
    "wotsec": "https://www.w3.org/2019/wot/security#",
    "@vocab": "https://www.w3.org/2019/wot/security#",
    "scheme": {"@id": "@type"},
    "description": {"@id": "td:description"},
    "in": {"@id": "wotsec:in"},
    "name": {"@id": "wotsec:name"},
    "scopes": {"@id": "wotsec:scopes"},
    "allOf": {"@id": "wotsec:allOf", "@container": "@set"},
    "oneOf": {"@id": "wotsec:oneOf", "@container": "@set"},
    "nosec": "wotsec:NoSecurityScheme",
    "auto": "wotsec:AutoSecurityScheme",
    "combo": "wotsec:ComboSecurityScheme",
    "basic": "wotsec:BasicSecurityScheme",
    "digest": "wotsec:DigestSecurityScheme",
    "apikey": "wotsec:APIKeySecurityScheme",
    "bearer": "wotsec:BearerSecurityScheme",
    "cert": "wotsec:CertSecurityScheme",
    "psk": "wotsec:PSKSecurityScheme",
    "public": "wotsec:PublicSecurityScheme",
    "pop": "wotsec:PoPSecurityScheme",
    "oauth2": "wotsec:OAuth2SecurityScheme",
}

_FORM_CONTEXT: dict[str, Any] = {
    "td": "https://www.w3.org/2019/wot/td#",
    "hctl": "https://www.w3.org/2019/wot/hypermedia#",
    "wotsec": "https://www.w3.org/2019/wot/security#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "@vocab": "https://www.w3.org/2019/wot/hypermedia#",
    "href": {"@id": "hctl:hasTarget", "@type": "xsd:anyURI"},
    "op": {"@id": "hctl:hasOperationType", "@type": "@vocab"},
    "contentType": {"@id": "hctl:forContentType"},
    "contentCoding": {"@id": "hctl:forContentCoding"},
    "subprotocol": {"@id": "hctl:forSubProtocol"},
    "security": {"@id": "td:hasSecurityConfiguration", "@type": "@id"},
    "scopes": {"@id": "wotsec:scopes"},
    "response": {"@id": "hctl:returns"},
    "readproperty": "td:readProperty",
    "writeproperty": "td:writeProperty",
    "observeproperty": "td:observeProperty",
    "invokeaction": "td:invokeAction",
    "queryaction": "td:queryAction",
    "subscribeevent": "td:subscribeEvent",
    "unsubscribeevent": "td:unsubscribeEvent",
}

WOT_TD_11_CONTEXT: dict[str, Any] = {
    "td": "https://www.w3.org/2019/wot/td#",
    "jsonschema": "https://www.w3.org/2019/wot/json-schema#",
    "wotsec": "https://www.w3.org/2019/wot/security#",
    "hctl": "https://www.w3.org/2019/wot/hypermedia#",
    "dct": "http://purl.org/dc/terms/",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "@vocab": "https://www.w3.org/2019/wot/td#",
    "id": "@id",
    "Thing": {"@id": "td:Thing"},
    "title": {"@id": "td:title", "@language": "en"},
    "description": {"@id": "td:description", "@language": "en"},
    "created": {"@id": "dct:created", "@type": "xsd:dateTime"},
    "modified": {"@id": "dct:modified", "@type": "xsd:dateTime"},
    "properties": {
        "@id": "td:hasPropertyAffordance",
        "@type": "@id",
        "@container": "@index",
        "@index": "name",
        "@context": _JSON_SCHEMA_CONTEXT,
    },
    "actions": {
        "@id": "td:hasActionAffordance",
        "@type": "@id",
        "@container": "@index",
        "@index": "name",
    },
    "events": {
        "@id": "td:hasEventAffordance",
        "@type": "@id",
        "@container": "@index",
        "@index": "name",
    },
    "name": {"@id": "td:name"},
    "security": {"@id": "td:hasSecurityConfiguration", "@type": "xsd:string"},
    "securityDefinitions": {
        "@id": "td:definesSecurityScheme",
        "@type": "@id",
        "@container": "@index",
        "@index": "hasInstanceConfiguration",
        "@context": _SECURITY_CONTEXT,
    },
    "forms": {
        "@id": "td:hasForm",
        "@type": "@id",
        "@container": "@set",
        "@context": _FORM_CONTEXT,
    },
    "input": {
        "@id": "td:hasInputSchema",
        "@type": "@id",
        "@context": _JSON_SCHEMA_CONTEXT,
    },
    "output": {
        "@id": "td:hasOutputSchema",
        "@type": "@id",
        "@context": _JSON_SCHEMA_CONTEXT,
    },
    "uriVariables": {
        "@id": "td:hasUriTemplateSchema",
        "@type": "@id",
        "@container": "@index",
        "@index": "name",
        "@context": _JSON_SCHEMA_CONTEXT,
    },
    "safe": {"@id": "td:isSafe"},
    "idempotent": {"@id": "td:isIdempotent"},
    "observable": {"@id": "td:isObservable"},
    "@version": 1.1,
}

_CONTEXTS_BY_URL = {
    WOT_TD_11_CONTEXT_URL: WOT_TD_11_CONTEXT,
}


def expand_cached_jsonld_contexts(document: dict[str, Any]) -> dict[str, Any]:
    """Replace supported remote JSON-LD contexts with local cached contexts."""
    return _expand_value(document)


def _expand_value(value: Any) -> Any:
    if isinstance(value, str):
        return _expand_context_url(value)
    if isinstance(value, list):
        return [_expand_value(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _expand_value(item) if key == "@context" else _expand_document_value(item)
            for key, item in value.items()
        }
    return value


def _expand_document_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_expand_document_value(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _expand_value(item) if key == "@context" else _expand_document_value(item)
            for key, item in value.items()
        }
    return value


def _expand_context_url(value: str) -> Any:
    context = _CONTEXTS_BY_URL.get(value)
    if context is None:
        if value.startswith(("http://", "https://")):
            raise ValueError(f"Unsupported remote JSON-LD context: {value}")
        return value
    return deepcopy(context)
