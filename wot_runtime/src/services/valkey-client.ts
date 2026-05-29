import { Redis as RedisClient } from 'ioredis';

import { config } from '../config/env.js';
import log from '../logger/index.js';
import { formatError } from './errors.js';

let clientPromise: Promise<RedisClient> | null = null;

/**
 * Creates and initializes a new Redis/Valkey client.
 */
async function createClient(): Promise<RedisClient> {
  const client = new RedisClient(config.redisUrl, {
    lazyConnect: true,
    maxRetriesPerRequest: 1,
  });

  client.on('error', (error: unknown) => {
    log.error(`Valkey error: ${formatError(error)}`);
  });

  await client.connect();
  return client;
}

/**
 * Returns a promise that resolves to the singleton Valkey client instance.
 * Initializes the client on first call.
 */
export async function getValkeyClient(): Promise<RedisClient> {
  if (!clientPromise) {
    clientPromise = createClient().catch((error) => {
      clientPromise = null;
      throw error;
    });
  }

  return clientPromise;
}

/**
 * Pings the Valkey server to check for reachability.
 */
export async function pingValkey(): Promise<boolean> {
  try {
    const client = await getValkeyClient();
    return (await client.ping()) === 'PONG';
  } catch {
    return false;
  }
}

/**
 * Closes the Valkey client connection and resets the singleton instance.
 */
export async function closeValkeyClient(): Promise<void> {
  if (!clientPromise) {
    return;
  }

  const client = await clientPromise.catch(() => null);
  clientPromise = null;
  await client?.quit().catch(() => undefined);
}
