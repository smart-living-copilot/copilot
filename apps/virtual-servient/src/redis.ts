import { Redis as RedisClient } from 'ioredis';

import { config } from './config.js';
import log from './logger.js';

let clientPromise: Promise<RedisClient> | null = null;

export async function getRedisClient(): Promise<RedisClient> {
  if (!clientPromise) {
    clientPromise = (async () => {
      const client = new RedisClient(config.redisUrl, {
        lazyConnect: true,
        maxRetriesPerRequest: 1,
      });
      client.on('error', (error) => log.error('Redis error', String(error)));
      await client.connect();
      return client;
    })().catch((error) => {
      clientPromise = null;
      throw error;
    });
  }
  try {
    return await clientPromise;
  } catch (error) {
    clientPromise = null;
    throw error;
  }
}

export async function closeRedisClient(): Promise<void> {
  const client = await clientPromise?.catch(() => null);
  clientPromise = null;
  await client?.quit().catch(() => undefined);
}
