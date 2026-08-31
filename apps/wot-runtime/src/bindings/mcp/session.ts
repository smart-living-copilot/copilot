import { createHash } from 'node:crypto';

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';

import { config } from '../../config/env.js';
import log from '../../logger/index.js';
import { createRuntimeError, formatError } from '../../services/errors.js';

const CLIENT_INFO = { name: 'wot-runtime', version: '1.0.0' };

interface SessionEntry {
  client: Client;
  transport: StreamableHTTPClientTransport;
  lastUsedAt: number;
}

/**
 * Live MCP sessions keyed by endpoint plus credential identity.
 *
 * Two Things pointing at the same endpoint with different credentials must not share a
 * session, so the key covers both. Entries are evicted on error and by least-recent use
 * once `mcpMaxSessions` is reached.
 */
const sessions = new Map<string, SessionEntry>();

/** In-flight connects, so concurrent calls to one endpoint share a single handshake. */
const pending = new Map<string, Promise<Client>>();

/**
 * Derives a stable, non-reversible identity for a set of request headers.
 *
 * Credential values must never appear in a cache key that could be logged, so the
 * headers are hashed rather than embedded.
 */
function credentialIdentity(headers: Record<string, string>): string {
  const entries = Object.entries(headers).sort(([a], [b]) => a.localeCompare(b));
  if (entries.length === 0) {
    return 'anonymous';
  }

  return createHash('sha256').update(JSON.stringify(entries)).digest('hex').slice(0, 16);
}

/**
 * Builds the map key identifying a session.
 *
 * Exported so the pooling invariant — same endpoint and credentials share a connection,
 * different credentials do not — can be checked without opening one.
 */
export function sessionKey(endpoint: string, headers: Record<string, string>): string {
  return `${endpoint}#${credentialIdentity(headers)}`;
}

/**
 * Closes a session and forgets it, tolerating a transport that is already gone.
 */
async function disposeEntry(key: string, entry: SessionEntry): Promise<void> {
  sessions.delete(key);
  try {
    await entry.client.close();
  } catch (error) {
    log.debug(`Closing MCP session ${key.split('#')[0]} failed: ${formatError(error)}`);
  }
}

/**
 * Evicts least-recently-used sessions until the pool is within its configured bound.
 */
async function enforceSessionLimit(): Promise<void> {
  const limit = config.mcpMaxSessions;
  if (limit <= 0 || sessions.size <= limit) {
    return;
  }

  const byAge = [...sessions.entries()].sort(([, a], [, b]) => a.lastUsedAt - b.lastUsedAt);
  const excess = byAge.slice(0, sessions.size - limit);

  for (const [key, entry] of excess) {
    log.debug(`Evicting least-recently-used MCP session for ${key.split('#')[0]}`);
    await disposeEntry(key, entry);
  }
}

/**
 * Opens a new MCP session against an endpoint.
 *
 * The SDK owns the `initialize` / `notifications/initialized` handshake, session-id
 * tracking and SSE framing; this only supplies the transport and its headers.
 */
async function connect(endpoint: string, headers: Record<string, string>): Promise<SessionEntry> {
  const transport = new StreamableHTTPClientTransport(new URL(endpoint), {
    requestInit: Object.keys(headers).length > 0 ? { headers } : undefined,
  });

  const client = new Client(CLIENT_INFO, { capabilities: {} });

  await client.connect(transport);
  log.info(`MCP session established with ${endpoint}`);

  return { client, transport, lastUsedAt: Date.now() };
}

/**
 * Reuses a live session when one exists; otherwise runs on an isolated session
 * and closes only that session. Endpoint description therefore cannot tear
 * down live interactions or leave a temporary connection in the pool.
 */
export async function withDescriptionSession<T>(
  endpoint: string,
  headers: Record<string, string>,
  operation: (client: Client) => Promise<T>,
): Promise<T> {
  const key = sessionKey(endpoint, headers);
  const existing = sessions.get(key);
  if (existing) {
    existing.lastUsedAt = Date.now();
    return operation(existing.client);
  }
  const inFlight = pending.get(key);
  if (inFlight) {
    return operation(await inFlight);
  }
  let entry: SessionEntry;
  try {
    entry = await connect(endpoint, headers);
  } catch (error) {
    throw createRuntimeError('unknown', `MCP connection to ${endpoint} failed: ${formatError(error)}`);
  }
  try {
    return await operation(entry.client);
  } finally {
    try {
      await entry.client.close();
    } catch (error) {
      log.debug(`Closing temporary MCP session for ${endpoint} failed: ${formatError(error)}`);
    }
  }
}

/**
 * Returns a connected MCP client for an endpoint, reusing a live session when one exists.
 */
export async function getSession(endpoint: string, headers: Record<string, string>): Promise<Client> {
  const key = sessionKey(endpoint, headers);

  const existing = sessions.get(key);
  if (existing) {
    existing.lastUsedAt = Date.now();
    return existing.client;
  }

  const inFlight = pending.get(key);
  if (inFlight) {
    return inFlight;
  }

  const connecting = connect(endpoint, headers)
    .then(async (entry) => {
      sessions.set(key, entry);
      await enforceSessionLimit();
      return entry.client;
    })
    .catch((error) => {
      throw createRuntimeError('unknown', `MCP connection to ${endpoint} failed: ${formatError(error)}`);
    })
    .finally(() => {
      pending.delete(key);
    });

  pending.set(key, connecting);
  return connecting;
}

/**
 * Drops a session so the next call reconnects.
 *
 * Called when a request fails, since the common cause is a server-expired session and
 * the previous implementation's never-invalidated cache made that unrecoverable.
 */
export async function dropSession(endpoint: string, headers: Record<string, string>): Promise<void> {
  const key = sessionKey(endpoint, headers);
  const entry = sessions.get(key);
  if (entry) {
    await disposeEntry(key, entry);
  }
}

/**
 * Closes every open MCP session.
 */
export async function closeAllSessions(): Promise<void> {
  const entries = [...sessions.entries()];
  await Promise.all(entries.map(([key, entry]) => disposeEntry(key, entry)));
}

/**
 * Returns the number of live sessions. Intended for tests and health reporting.
 */
export function activeSessionCount(): number {
  return sessions.size;
}
