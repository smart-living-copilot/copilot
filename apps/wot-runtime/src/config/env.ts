/**
 * Parses an environment variable as an integer.
 *
 * @param name The name of the environment variable.
 * @param fallback The fallback value if not set or invalid.
 * @returns The parsed integer or the fallback.
 */
function parseIntEnv(name: string, fallback: number): number {
  const rawValue = process.env[name];
  if (!rawValue) {
    return fallback;
  }

  const parsed = Number.parseInt(rawValue, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

/**
 * Parses an environment variable as a non-negative integer.
 */
function parseNonNegativeIntEnv(name: string, fallback: number): number {
  return Math.max(0, parseIntEnv(name, fallback));
}

/**
 * Ensures an environment variable is set and returns its value.
 *
 * @param name The name of the environment variable.
 * @returns The trimmed string value.
 * @throws {Error} if the variable is missing or empty.
 */
function requiredStringEnv(name: string): string {
  const value = process.env[name]?.trim();
  if (value) {
    return value;
  }

  throw new Error(`Missing required environment variable: ${name}`);
}

/**
 * Central configuration object for the wot_runtime.
 * Values are loaded from environment variables with sensible defaults.
 */
export const config = {
  host: process.env.HOST || '127.0.0.1',
  port: parseIntEnv('PORT', 3003),
  registryUrl: process.env.REGISTRY_URL || 'http://localhost:8000',
  registryServiceName: process.env.REGISTRY_SERVICE_NAME || 'wot_runtime',
  registryServiceToken: requiredStringEnv('WOT_RUNTIME_REGISTRY_TOKEN'),
  runtimeApiToken: requiredStringEnv('WOT_RUNTIME_API_TOKEN'),
  secretsPath: process.env.SECRETS_PATH || './secrets.json',
  redisUrl: process.env.REDIS_URL || 'redis://localhost:6379',
  streamName: process.env.WOT_RUNTIME_STREAM || 'wot_runtime_events',
  requestTimeoutMs: parseIntEnv('HTTP_REQUEST_TIMEOUT_MS', 10000),
  subscriptionSetupTimeoutMs: parseIntEnv('WOT_SUBSCRIPTION_SETUP_TIMEOUT_MS', 0),
  secretsRefreshIntervalMs: parseIntEnv('SECRETS_REFRESH_INTERVAL_MS', 60000),
  requestBodyLimit: process.env.REQUEST_BODY_LIMIT || '50mb',
  cacheEnabled: (process.env.WOT_CACHE_ENABLED || 'true').toLowerCase() === 'true',
  cacheTtlSeconds: parseNonNegativeIntEnv('WOT_CACHE_TTL_SECONDS', 300),
  cacheMaxBytes: parseNonNegativeIntEnv('WOT_CACHE_MAX_BYTES', 10 * 1024 * 1024),
} as const;

/**
 * Type definition for the application configuration.
 */
export type AppConfig = typeof config;
