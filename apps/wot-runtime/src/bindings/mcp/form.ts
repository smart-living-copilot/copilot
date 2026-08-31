import type { Form } from '@node-wot/core';

import { createRuntimeError } from '../../services/errors.js';

/** Vendor extension naming the MCP tool that an action form invokes. */
export const MCP_TOOL_FIELD = 'mcp:tool';

/** Vendor extension naming the MCP resource URI that a property form reads. */
export const MCP_RESOURCE_FIELD = 'mcp:resource';

/**
 * Vendor extension carrying the server's unmodified JSON Schema for a tool's input.
 *
 * WoT's DataSchema cannot express `$ref`, `anyOf` or `additionalProperties`, so the
 * action's `input` holds the closest translation while the original is preserved here.
 * Arguments are sent through untouched and the MCP server validates them, so nothing
 * depends on the translation being faithful.
 */
export const MCP_INPUT_SCHEMA_FIELD = 'mcp:inputSchema';

const MCP_SCHEME_PREFIX = 'mcp+';
const SUPPORTED_TRANSPORT_SCHEMES = new Set(['http', 'https']);

/**
 * Reads a non-empty string field from a form, returning null when absent or blank.
 */
function readStringField(form: Form, field: string): string | null {
  const value = form[field];
  if (typeof value !== 'string') {
    return null;
  }

  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

/**
 * Returns the MCP tool name a form invokes, or null when the form names none.
 */
export function getMcpToolName(form: Form): string | null {
  return readStringField(form, MCP_TOOL_FIELD);
}

/**
 * Returns the MCP resource URI a form reads, or null when the form names none.
 */
export function getMcpResourceUri(form: Form): string | null {
  return readStringField(form, MCP_RESOURCE_FIELD);
}

/**
 * Returns the tool name a form must name, failing with a usable message when it does not.
 */
export function requireMcpToolName(form: Form): string {
  const toolName = getMcpToolName(form);
  if (!toolName) {
    throw createRuntimeError(
      'invalid_argument',
      `MCP form '${String(form.href)}' is missing '${MCP_TOOL_FIELD}'. ` +
        `Add the tool name to the form, for example "${MCP_TOOL_FIELD}": "search".`,
    );
  }

  return toolName;
}

/**
 * Returns the resource URI a form must name, failing with a usable message when it does not.
 */
export function requireMcpResourceUri(form: Form): string {
  const resourceUri = getMcpResourceUri(form);
  if (!resourceUri) {
    throw createRuntimeError(
      'invalid_argument',
      `MCP form '${String(form.href)}' is missing '${MCP_RESOURCE_FIELD}'. ` +
        `Add the resource URI to the form, for example "${MCP_RESOURCE_FIELD}": "file:///data.json".`,
    );
  }

  return resourceUri;
}

/**
 * Translates an `mcp+http(s)://` form href into the transport URL to connect to.
 *
 * The `mcp+` prefix is what routes a form to this binding: node-wot selects a client
 * factory by URI scheme. Stripping the prefix textually rather than rebuilding the URL
 * keeps userinfo, port, path and query exactly as authored.
 */
export function resolveMcpEndpoint(href: unknown): string {
  if (typeof href !== 'string' || href.trim().length === 0) {
    throw createRuntimeError('invalid_argument', 'MCP form is missing an href');
  }

  const trimmed = href.trim();
  if (!trimmed.toLowerCase().startsWith(MCP_SCHEME_PREFIX)) {
    throw createRuntimeError(
      'invalid_argument',
      `MCP form href '${trimmed}' must use an '${MCP_SCHEME_PREFIX}' scheme, for example 'mcp+https://host/mcp'.`,
    );
  }

  const endpoint = trimmed.slice(MCP_SCHEME_PREFIX.length);

  let parsed: URL;
  try {
    parsed = new URL(endpoint);
  } catch {
    throw createRuntimeError('invalid_argument', `MCP form href '${trimmed}' is not a valid URL`);
  }

  const transportScheme = parsed.protocol.replace(/:$/, '');
  if (!SUPPORTED_TRANSPORT_SCHEMES.has(transportScheme)) {
    throw createRuntimeError(
      'invalid_argument',
      `MCP transport '${transportScheme}' is not supported. Use 'mcp+http' or 'mcp+https'.`,
    );
  }

  return endpoint;
}
