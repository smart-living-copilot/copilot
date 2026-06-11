function parseIntEnv(name: string, fallback: number): number {
  const rawValue = process.env[name];
  if (!rawValue) {
    return fallback;
  }
  const parsed = Number.parseInt(rawValue, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function registryTokenEnv(): string {
  const value =
    process.env.VIRTUAL_SERVIENT_REGISTRY_TOKEN?.trim() ||
    process.env.WOT_RUNTIME_REGISTRY_TOKEN?.trim();
  if (value) {
    return value;
  }
  throw new Error('Missing required environment variable: VIRTUAL_SERVIENT_REGISTRY_TOKEN');
}

export const config = {
  host: process.env.HOST || '127.0.0.1',
  port: parseIntEnv('PORT', 3013),
  wotPort: parseIntEnv('WOT_PORT', 3014),
  wotHost: process.env.WOT_HOST || process.env.HOST || '127.0.0.1',
  publicBaseUrl: process.env.VIRTUAL_SERVIENT_PUBLIC_URL || '',
  registryUrl: process.env.REGISTRY_URL || 'http://localhost:8000',
  registryServiceName: process.env.REGISTRY_SERVICE_NAME || 'virtual_servient',
  registryServiceToken: registryTokenEnv(),
  redisUrl: process.env.REDIS_URL || 'redis://localhost:6379',
  thingEventsStream: process.env.THING_EVENTS_STREAM || 'thing_events',
  thingEventsGroup: process.env.VIRTUAL_SERVIENT_EVENTS_GROUP || 'virtual_servient',
  thingEventsConsumer:
    process.env.VIRTUAL_SERVIENT_EVENTS_CONSUMER || `virtual-servient-${process.pid}`,
  requestTimeoutMs: parseIntEnv('HTTP_REQUEST_TIMEOUT_MS', 10000),
  reconcileIntervalMs: parseIntEnv('VIRTUAL_SERVIENT_RECONCILE_INTERVAL_MS', 30000),
} as const;
