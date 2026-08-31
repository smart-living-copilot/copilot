import { Readable } from 'node:stream';

import wotCore from '@node-wot/core';
import type { Content } from '@node-wot/core';

import { createRuntimeError } from '../../services/errors.js';

const { Content: ContentClass } = wotCore as any;

const JSON_CONTENT_TYPE = 'application/json';
const TEXT_CONTENT_TYPE = 'text/plain';
const BINARY_CONTENT_TYPE = 'application/octet-stream';

/** A single content block as returned by an MCP tool call or resource read. */
export interface McpContentBlock {
  type?: string;
  [key: string]: unknown;
}

/** The subset of an MCP `tools/call` result this binding consumes. */
export interface McpToolResult {
  content?: McpContentBlock[];
  structuredContent?: unknown;
  isError?: boolean;
  [key: string]: unknown;
}

/**
 * Wraps a buffer as node-wot Content.
 *
 * The buffer is pushed as a single chunk — `Readable.from(buffer)` would iterate the
 * buffer as individual byte values.
 */
export function contentFromBuffer(contentType: string, body: Buffer): Content {
  return new ContentClass(contentType, Readable.from([body]));
}

/**
 * Wraps a JSON-serialisable value as `application/json` Content.
 */
export function contentFromJson(value: unknown): Content {
  return contentFromBuffer(JSON_CONTENT_TYPE, Buffer.from(JSON.stringify(value ?? null), 'utf-8'));
}

/**
 * Reports whether a string parses as JSON, so text blocks that carry JSON are
 * labelled `application/json` rather than `text/plain`.
 */
function looksLikeJson(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) {
    return false;
  }

  try {
    JSON.parse(trimmed);
    return true;
  } catch {
    return false;
  }
}

/**
 * Reads a non-empty string property from a content block.
 */
function blockString(block: McpContentBlock, key: string): string | null {
  const value = block[key];
  return typeof value === 'string' && value.length > 0 ? value : null;
}

/**
 * Converts a single content block to Content, or null when the block shape is not
 * one this binding can represent directly.
 */
function singleBlockToContent(block: McpContentBlock): Content | null {
  if (block.type === 'text') {
    const text = typeof block.text === 'string' ? block.text : null;
    if (text === null) {
      return null;
    }
    const contentType = looksLikeJson(text) ? JSON_CONTENT_TYPE : TEXT_CONTENT_TYPE;
    return contentFromBuffer(contentType, Buffer.from(text, 'utf-8'));
  }

  if (block.type === 'image' || block.type === 'audio') {
    const data = blockString(block, 'data');
    if (data === null) {
      return null;
    }
    const mimeType = blockString(block, 'mimeType') ?? BINARY_CONTENT_TYPE;
    return contentFromBuffer(mimeType, Buffer.from(data, 'base64'));
  }

  if (block.type === 'resource') {
    const resource = block.resource;
    if (typeof resource !== 'object' || resource === null) {
      return null;
    }

    const embedded = resource as Record<string, unknown>;
    const mimeType = typeof embedded.mimeType === 'string' ? embedded.mimeType : null;

    if (typeof embedded.text === 'string') {
      const contentType = mimeType ?? (looksLikeJson(embedded.text) ? JSON_CONTENT_TYPE : TEXT_CONTENT_TYPE);
      return contentFromBuffer(contentType, Buffer.from(embedded.text, 'utf-8'));
    }

    if (typeof embedded.blob === 'string') {
      return contentFromBuffer(mimeType ?? BINARY_CONTENT_TYPE, Buffer.from(embedded.blob, 'base64'));
    }
  }

  return null;
}

/**
 * Collects the text of a result's blocks, used to describe a tool-reported failure.
 */
function describeBlocks(blocks: McpContentBlock[]): string {
  const text = blocks
    .filter((block) => block.type === 'text' && typeof block.text === 'string')
    .map((block) => String(block.text))
    .join('\n')
    .trim();

  return text.length > 0 ? text : JSON.stringify(blocks);
}

/**
 * Converts an MCP `tools/call` result into node-wot Content.
 *
 * A result flagged `isError` is a tool-reported failure and is raised as an error
 * rather than handed back as a successful payload.
 */
export function toolResultToContent(toolName: string, result: McpToolResult): Content {
  const blocks = Array.isArray(result.content) ? result.content : [];

  if (result.isError === true) {
    throw createRuntimeError('unknown', `MCP tool '${toolName}' reported an error: ${describeBlocks(blocks)}`);
  }

  // Servers that speak the structured-output extension give a typed result directly,
  // which is a better match for an action's output schema than re-parsing text.
  if (result.structuredContent !== undefined) {
    return contentFromJson(result.structuredContent);
  }

  if (blocks.length === 1) {
    const single = singleBlockToContent(blocks[0]);
    if (single) {
      return single;
    }
  }

  if (blocks.length === 0) {
    return contentFromJson(null);
  }

  // Multiple blocks, or a shape with no direct representation: hand back the blocks
  // as they arrived rather than silently dropping any of them.
  return contentFromJson(blocks);
}

/**
 * Converts an MCP `resources/read` result into node-wot Content.
 */
export function resourceResultToContent(uri: string, result: { contents?: McpContentBlock[] }): Content {
  const contents = Array.isArray(result.contents) ? result.contents : [];

  if (contents.length === 0) {
    throw createRuntimeError('not_found', `MCP resource '${uri}' returned no contents`);
  }

  if (contents.length === 1) {
    // resources/read returns bare resource bodies, not wrapped in a "resource" block.
    const single = singleBlockToContent({ type: 'resource', resource: contents[0] });
    if (single) {
      return single;
    }
  }

  return contentFromJson(contents);
}
