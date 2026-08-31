import type { ProtocolClient, ProtocolClientFactory } from '@node-wot/core';

import log from '../../logger/index.js';
import { McpClient } from './client.js';
import { closeAllSessions } from './session.js';

/** URI schemes routed to the MCP binding. */
export const MCP_SCHEMES = ['mcp+http', 'mcp+https'] as const;

/** A scheme the MCP binding serves. */
export type McpScheme = (typeof MCP_SCHEMES)[number];

/**
 * Produces MCP protocol clients for one URI scheme.
 *
 * node-wot picks a client factory by the scheme of a form's href, which is why MCP
 * endpoints are addressed as `mcp+https://host/mcp` rather than by their bare HTTPS
 * URL: the scheme is what says "speak MCP here" instead of plain HTTP. Sessions are
 * shared across clients, so instances are cheap.
 */
export class McpClientFactory implements ProtocolClientFactory {
  public readonly scheme: McpScheme;

  /**
   * Creates a factory serving one MCP scheme.
   */
  public constructor(scheme: McpScheme) {
    this.scheme = scheme;
  }

  /**
   * Returns a client for a single consumed Thing.
   */
  public getClient(): ProtocolClient {
    return new McpClient();
  }

  /**
   * Prepares the factory. Sessions connect lazily, so there is nothing to set up.
   */
  public init(): boolean {
    return true;
  }

  /**
   * Tears the factory down, closing any sessions its clients opened.
   */
  public destroy(): boolean {
    void closeAllSessions().catch((error) => {
      log.debug(`Closing MCP sessions during shutdown failed: ${String(error)}`);
    });
    return true;
  }
}

/**
 * Builds one factory per MCP scheme, for registration with the servient.
 */
export function createMcpClientFactories(): McpClientFactory[] {
  return MCP_SCHEMES.map((scheme) => new McpClientFactory(scheme));
}
