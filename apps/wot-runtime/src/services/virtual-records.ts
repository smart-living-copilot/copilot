import axios from 'axios';

import { config } from '../config/env.js';
import { registryServiceHeaders } from './thing-catalog-client.js';

const VIRTUAL_RECORD_PREFIX = 'virtual:records:';

/**
 * Checks whether a Thing ID belongs to copilot's virtual record backend.
 */
export function isVirtualRecordThingId(thingId: string): boolean {
  return thingId.startsWith(VIRTUAL_RECORD_PREFIX);
}

function virtualRecordUrl(thingId: string, suffix: string): string {
  return `${config.registryUrl}/api/virtual-records/${encodeURIComponent(thingId)}/${suffix}`;
}

function unwrapVirtualValue(payload: unknown): unknown {
  if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
    return (payload as Record<string, unknown>).value;
  }
  return payload;
}

/**
 * Reads a property from a virtual record thing through copilot's internal API.
 */
export async function readVirtualRecordProperty(
  thingId: string,
  propertyName: string,
): Promise<unknown> {
  const response = await axios.get(
    virtualRecordUrl(thingId, `properties/${encodeURIComponent(propertyName)}`),
    {
      headers: registryServiceHeaders(),
      timeout: config.requestTimeoutMs,
    },
  );
  return unwrapVirtualValue(response.data);
}

/**
 * Invokes a virtual record query action through copilot's internal API.
 */
export async function invokeVirtualRecordAction(
  thingId: string,
  actionName: string,
  input: unknown,
): Promise<unknown> {
  const response = await axios.post(
    virtualRecordUrl(thingId, `actions/${encodeURIComponent(actionName)}`),
    { input },
    {
      headers: registryServiceHeaders(),
      timeout: config.requestTimeoutMs,
    },
  );
  return unwrapVirtualValue(response.data);
}
