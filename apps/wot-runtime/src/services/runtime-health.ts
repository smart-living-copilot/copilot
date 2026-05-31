import { config } from '../config/env.js';
import { pingThingCatalog } from './thing-catalog-client.js';
import { getRuntimeSnapshot } from '../runtime/servient.js';
import { pingValkey } from './valkey-client.js';

/**
 * Snapshot of the runtime health status.
 */
export type RuntimeHealth = {
  status: 'ok' | 'degraded';
  servientReady: boolean;
  backendReachable: boolean;
  valkeyConfigured: boolean;
  protocols: string[];
  startedAt: string | null;
  streamName: string;
};

/**
 * Checks the connectivity and readiness of the runtime's core components.
 * Checks the node-wot servient, the central registry (backend), and the Valkey event stream.
 *
 * @returns A promise resolving to a snapshot of the runtime health.
 */
export async function getRuntimeHealth(): Promise<RuntimeHealth> {
  const runtime = getRuntimeSnapshot();
  const backendReachable = await pingThingCatalog();
  const valkeyConfigured = config.redisUrl.trim().length > 0 && (await pingValkey());
  const status = runtime.servientReady && backendReachable && valkeyConfigured ? 'ok' : 'degraded';

  return {
    status,
    servientReady: runtime.servientReady,
    backendReachable,
    valkeyConfigured,
    protocols: runtime.protocols,
    startedAt: runtime.startedAt,
    streamName: config.streamName,
  };
}
