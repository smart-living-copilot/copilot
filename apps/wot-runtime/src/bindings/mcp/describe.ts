/**
 * Builds a draft Thing Description from what an MCP server says about itself.
 *
 * `tools/list` and `resources/list` are a typed, one-to-one description of a server's
 * surface, so translating them is mechanical and belongs in code. The result is a draft:
 * the caller is expected to improve titles, drop tools it does not want, and add
 * semantic types before storing it.
 */

import { MCP_INPUT_SCHEMA_FIELD, MCP_RESOURCE_FIELD, MCP_TOOL_FIELD } from './form.js';
import { toDataSchema } from './schema.js';

const TD_CONTEXT = 'https://www.w3.org/2022/wot/td/v1.1';
const MCP_VOCAB = 'https://modelcontextprotocol.io/specification#';
const JSON_CONTENT_TYPE = 'application/json';

/** A tool as reported by `tools/list`. */
export interface McpToolDescriptor {
  name: string;
  title?: string;
  description?: string;
  inputSchema?: unknown;
  outputSchema?: unknown;
}

/** A resource as reported by `resources/list`. */
export interface McpResourceDescriptor {
  uri: string;
  name?: string;
  title?: string;
  description?: string;
  mimeType?: string;
}

/** Everything needed to describe a server as a Thing. */
export interface DescribeInput {
  /** The `mcp+http(s)://` href, so generated forms route back to this binding. */
  href: string;
  serverName?: string;
  serverVersion?: string;
  instructions?: string;
  tools: McpToolDescriptor[];
  resources: McpResourceDescriptor[];
}

/**
 * Converts a server or tool name into a URN-safe segment.
 */
function slugify(value: string): string {
  const slug = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');

  return slug.length > 0 ? slug : 'server';
}

/**
 * Turns an MCP name into a valid affordance key.
 *
 * MCP tool names commonly contain hyphens (`get-tiny-image`), which are fine as WoT
 * affordance keys, so the name is preserved as-is wherever it is already usable.
 */
function affordanceName(name: string, taken: Set<string>): string {
  const base = name.trim().length > 0 ? name.trim() : 'unnamed';

  if (!taken.has(base)) {
    taken.add(base);
    return base;
  }

  let suffix = 2;
  while (taken.has(`${base}-${suffix}`)) {
    suffix += 1;
  }

  const unique = `${base}-${suffix}`;
  taken.add(unique);
  return unique;
}

/**
 * Drops keys whose value is undefined, so generated documents stay free of empty fields.
 */
function compact<T extends Record<string, unknown>>(value: T): T {
  return Object.fromEntries(Object.entries(value).filter(([, entry]) => entry !== undefined)) as T;
}

/**
 * Builds the action for one MCP tool.
 */
function toolToAction(tool: McpToolDescriptor, href: string): Record<string, unknown> {
  const input = toDataSchema(tool.inputSchema);
  const output = toDataSchema(tool.outputSchema);

  return compact({
    title: tool.title ?? tool.name,
    description: tool.description,
    // MCP has no notion of a side-effect-free tool, so no action is marked `safe`
    // and none becomes cacheable by default.
    idempotent: false,
    input: Object.keys(input).length > 0 ? input : undefined,
    output: Object.keys(output).length > 0 ? output : undefined,
    forms: [
      compact({
        op: ['invokeaction'],
        href,
        contentType: JSON_CONTENT_TYPE,
        [MCP_TOOL_FIELD]: tool.name,
        // The untranslated schema, since DataSchema cannot hold $ref/anyOf/additionalProperties.
        [MCP_INPUT_SCHEMA_FIELD]: tool.inputSchema,
      }),
    ],
  });
}

/**
 * Builds the read-only property for one MCP resource.
 */
function resourceToProperty(resource: McpResourceDescriptor, href: string): Record<string, unknown> {
  return compact({
    title: resource.title ?? resource.name ?? resource.uri,
    description: resource.description,
    readOnly: true,
    forms: [
      compact({
        op: ['readproperty'],
        href,
        contentType: resource.mimeType ?? JSON_CONTENT_TYPE,
        [MCP_RESOURCE_FIELD]: resource.uri,
      }),
    ],
  });
}

/**
 * Builds a draft Thing Description for an MCP server.
 *
 * The id is derived from the server's self-reported name rather than its address, so it
 * survives the endpoint moving — ToolHive assigns a fresh proxy port on every restart.
 * Two servers reporting the same name would collide, which is one of the things a caller
 * is expected to resolve before storing the draft.
 */
export function buildThingDescription(details: DescribeInput): Record<string, unknown> {
  const name = details.serverName?.trim() || 'MCP Server';
  const usedActionNames = new Set<string>();
  const usedPropertyNames = new Set<string>();

  const actions: Record<string, unknown> = {};
  for (const tool of details.tools) {
    actions[affordanceName(tool.name, usedActionNames)] = toolToAction(tool, details.href);
  }

  const properties: Record<string, unknown> = {};
  for (const resource of details.resources) {
    const key = resource.name ?? resource.uri;
    properties[affordanceName(key, usedPropertyNames)] = resourceToProperty(resource, details.href);
  }

  return compact({
    '@context': [TD_CONTEXT, { mcp: MCP_VOCAB }],
    id: `urn:mcp:${slugify(name)}`,
    title: name,
    description: details.instructions?.trim() || `MCP server '${name}' described from tools/list.`,
    version: details.serverVersion ? { instance: details.serverVersion } : undefined,
    security: ['nosec_sc'],
    securityDefinitions: { nosec_sc: { scheme: 'nosec' } },
    actions: Object.keys(actions).length > 0 ? actions : undefined,
    properties: Object.keys(properties).length > 0 ? properties : undefined,
  });
}
