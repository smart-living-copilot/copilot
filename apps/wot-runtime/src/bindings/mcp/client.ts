import { ResourceUpdatedNotificationSchema } from '@modelcontextprotocol/sdk/types.js';
import type { Client } from '@modelcontextprotocol/sdk/client/index.js';
import type { Content, Form, ProtocolClient, SecurityScheme } from '@node-wot/core';
import { Subscription } from 'rxjs/Subscription.js';

import { config } from '../../config/env.js';
import log from '../../logger/index.js';
import { createRuntimeError, formatError, isRuntimeError } from '../../services/errors.js';
import { contentFromBuffer, resourceResultToContent, toolResultToContent } from './content.js';
import type { McpToolResult } from './content.js';
import { buildThingDescription } from './describe.js';
import type { McpResourceDescriptor, McpToolDescriptor } from './describe.js';
import { requireMcpResourceUri, requireMcpToolName, resolveMcpEndpoint } from './form.js';
import { closeAllSessions, dropSession, getSession, withDescriptionSession } from './session.js';

const TD_CONTENT_TYPE = 'application/td+json';

/**
 * Decodes an action input into the arguments object an MCP tool call expects.
 *
 * Whatever arrives is forwarded unmodified: the MCP server validates against its own
 * schema and reports violations far better than a translated copy could.
 */
export async function readArguments(content: Content | undefined): Promise<Record<string, unknown>> {
  if (!content) {
    return {};
  }

  const buffer = await content.toBuffer();
  if (buffer.length === 0) {
    return {};
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(buffer.toString('utf-8'));
  } catch {
    throw createRuntimeError('invalid_argument', 'MCP tool arguments must be a JSON object');
  }

  if (parsed === null || parsed === undefined) {
    return {};
  }

  if (typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw createRuntimeError(
      'invalid_argument',
      `MCP tool arguments must be a JSON object, received ${Array.isArray(parsed) ? 'an array' : typeof parsed}`,
    );
  }

  return parsed as Record<string, unknown>;
}

/** Collects every page returned by MCP tools/list. */
export async function listAllMcpTools(client: Client): Promise<McpToolDescriptor[]> {
  const tools: McpToolDescriptor[] = [];
  let cursor: string | undefined;
  const seen = new Set<string>();
  do {
    const page = await client.listTools(cursor ? { cursor } : undefined);
    tools.push(...(page.tools as McpToolDescriptor[]));
    cursor = page.nextCursor;
    if (cursor && seen.has(cursor)) {
      throw createRuntimeError('unknown', 'MCP tools/list repeated a pagination cursor');
    }
    if (cursor) seen.add(cursor);
  } while (cursor);
  return tools;
}

/** Collects every page returned by MCP resources/list. */
export async function listAllMcpResources(client: Client): Promise<McpResourceDescriptor[]> {
  const resources: McpResourceDescriptor[] = [];
  let cursor: string | undefined;
  const seen = new Set<string>();
  do {
    const page = await client.listResources(cursor ? { cursor } : undefined);
    resources.push(...(page.resources as McpResourceDescriptor[]));
    cursor = page.nextCursor;
    if (cursor && seen.has(cursor)) {
      throw createRuntimeError('unknown', 'MCP resources/list repeated a pagination cursor');
    }
    if (cursor) seen.add(cursor);
  } while (cursor);
  return resources;
}

/**
 * A node-wot protocol client that speaks the Model Context Protocol.
 *
 * Registered for the `mcp+http` and `mcp+https` schemes, so a form whose href carries
 * one of them routes here instead of to the HTTP binding, and every interaction — not
 * just action invocation — goes through the servient like any other protocol.
 */
export class McpClient implements ProtocolClient {
  private headers: Record<string, string> = {};

  /**
   * Runs an operation against a session, retrying once on a fresh session.
   *
   * A failed request most often means the server expired the session, which the
   * previous implementation could not recover from because it never invalidated its cache.
   */
  private async withSession<T>(endpoint: string, operation: (client: Client) => Promise<T>): Promise<T> {
    const client = await getSession(endpoint, this.headers);

    try {
      return await operation(client);
    } catch (error) {
      if (isRuntimeError(error)) {
        throw error;
      }

      log.debug(`MCP request to ${endpoint} failed, reconnecting: ${formatError(error)}`);
      await dropSession(endpoint, this.headers);

      const retryClient = await getSession(endpoint, this.headers);
      return operation(retryClient);
    }
  }

  /**
   * Reads an MCP resource named by the form's `mcp:resource`.
   */
  public async readResource(form: Form): Promise<Content> {
    const endpoint = resolveMcpEndpoint(form.href);
    const uri = requireMcpResourceUri(form);

    const result = await this.withSession(endpoint, (client) =>
      client.readResource({ uri }, { timeout: config.mcpRequestTimeoutMs }),
    );

    return resourceResultToContent(uri, result as { contents?: Array<Record<string, unknown>> });
  }

  /**
   * Not supported: MCP has no write-resource operation.
   */
  public async writeResource(form: Form): Promise<void> {
    throw createRuntimeError(
      'unimplemented',
      `MCP does not support writing resources, so form '${String(form.href)}' cannot be written. ` +
        'Model the operation as an action bound to an MCP tool instead.',
    );
  }

  /**
   * Invokes the MCP tool named by the form's `mcp:tool`.
   */
  public async invokeResource(form: Form, content?: Content): Promise<Content> {
    const endpoint = resolveMcpEndpoint(form.href);
    const toolName = requireMcpToolName(form);
    const args = await readArguments(content);

    log.info(`MCP call: ${toolName} on ${endpoint}`);

    const result = await this.withSession(endpoint, (client) =>
      client.callTool({ name: toolName, arguments: args }, undefined, { timeout: config.mcpRequestTimeoutMs }),
    );

    return toolResultToContent(toolName, result as McpToolResult);
  }

  /**
   * Releases a form's resource subscription.
   */
  public async unlinkResource(form: Form): Promise<void> {
    const endpoint = resolveMcpEndpoint(form.href);
    const uri = requireMcpResourceUri(form);

    await this.withSession(endpoint, (client) => client.unsubscribeResource({ uri })).catch((error) => {
      log.debug(`MCP unsubscribe from ${uri} failed: ${formatError(error)}`);
    });
  }

  /**
   * Subscribes to updates for the MCP resource named by the form.
   *
   * MCP notifies that a resource changed without carrying the new value, so each
   * notification triggers a read and the resulting content is handed to `next`.
   */
  public async subscribeResource(
    form: Form,
    next: (content: Content) => void,
    error?: (error: Error) => void,
    complete?: () => void,
  ): Promise<Subscription> {
    const endpoint = resolveMcpEndpoint(form.href);
    const uri = requireMcpResourceUri(form);
    const client = await getSession(endpoint, this.headers);

    client.setNotificationHandler(ResourceUpdatedNotificationSchema, async (notification) => {
      if (notification.params?.uri !== uri) {
        return;
      }

      try {
        const result = await client.readResource({ uri }, { timeout: config.mcpRequestTimeoutMs });
        next(resourceResultToContent(uri, result as { contents?: Array<Record<string, unknown>> }));
      } catch (readError) {
        error?.(readError instanceof Error ? readError : new Error(formatError(readError)));
      }
    });

    await client.subscribeResource({ uri });
    log.info(`MCP subscription active for ${uri} on ${endpoint}`);

    return new Subscription(() => {
      void client.unsubscribeResource({ uri }).catch((unsubError) => {
        log.debug(`MCP unsubscribe from ${uri} failed: ${formatError(unsubError)}`);
      });
      complete?.();
    });
  }

  /**
   * Builds a draft Thing Description for an MCP endpoint from what it says about itself.
   *
   * MCP servers are self-describing, so node-wot's standard "describe this endpoint"
   * method is where that belongs: nothing outside this binding needs to know what MCP
   * is to obtain a Thing Description for one.
   */
  public async requestThingDescription(uri: string): Promise<Content> {
    const endpoint = resolveMcpEndpoint(uri);

    const document = await withDescriptionSession(endpoint, this.headers, async (client) => {
      const capabilities = client.getServerCapabilities();
      const serverInfo = client.getServerVersion();

      const tools = capabilities?.tools ? await listAllMcpTools(client) : [];

      // A server that advertises no resource capability answers resources/list with
      // "method not found", so the capability is checked rather than the error caught.
      const resources = capabilities?.resources ? await listAllMcpResources(client) : [];

      return buildThingDescription({
        href: uri,
        serverName: serverInfo?.name,
        serverVersion: serverInfo?.version,
        instructions: client.getInstructions(),
        tools,
        resources,
      });
    });

    log.info(`Described MCP endpoint ${endpoint} as '${String(document.id)}'`);

    return contentFromBuffer(TD_CONTENT_TYPE, Buffer.from(JSON.stringify(document), 'utf-8'));
  }

  /**
   * No connection is opened until a form is actually used.
   */
  public async start(): Promise<void> {
    return undefined;
  }

  /**
   * Closes every MCP session this runtime holds.
   */
  public async stop(): Promise<void> {
    await closeAllSessions();
  }

  /**
   * Turns resolved credentials into the headers sent on every request to the endpoint.
   *
   * The credential patch installed in `servient.ts` resolves the right stored entry for
   * the Thing before this runs, so `credentials` is already the single matching secret.
   */
  public setSecurity(metadata: SecurityScheme[], credentials?: unknown): boolean {
    const scheme = metadata?.[0]?.scheme?.toLowerCase();

    if (!scheme || scheme === 'nosec') {
      this.headers = {};
      return true;
    }

    if (typeof credentials !== 'object' || credentials === null) {
      log.warn(`MCP client received no credentials for security scheme '${scheme}'`);
      return false;
    }

    const secret = credentials as Record<string, unknown>;

    if (scheme === 'bearer' && typeof secret.token === 'string') {
      this.headers = { Authorization: `Bearer ${secret.token}` };
      return true;
    }

    if (scheme === 'basic' && typeof secret.username === 'string' && typeof secret.password === 'string') {
      const encoded = Buffer.from(`${secret.username}:${secret.password}`, 'utf-8').toString('base64');
      this.headers = { Authorization: `Basic ${encoded}` };
      return true;
    }

    if (scheme === 'apikey' && typeof secret.apikey === 'string') {
      const headerName = typeof metadata[0]?.name === 'string' ? metadata[0].name : 'X-API-Key';
      this.headers = { [headerName]: secret.apikey };
      return true;
    }

    log.warn(`MCP client cannot apply security scheme '${scheme}'`);
    return false;
  }
}
