import crypto from 'node:crypto';

import axios, { AxiosError } from 'axios';

import { config } from '../config/env.js';

/**
 * Represents a W3C Web of Things (WoT) Thing Description (TD) as a plain object.
 */
export type ThingDescription = Record<string, unknown>;

/**
 * Generates the full URL for the registry's Thing Catalog API.
 */
function thingsUrl(path: string): string {
  const trimmed = path.replace(/^\/+/, '');
  if (!trimmed) {
    return `${config.registryUrl}/api/things`;
  }
  return `${config.registryUrl}/api/things/${trimmed}`;
}

/**
 * Generates headers for service-to-service authentication with the central registry.
 */
export function registryServiceHeaders(): Record<string, string> | undefined {
  if (!config.registryServiceToken) {
    return undefined;
  }

  return {
    'X-Registry-Service': config.registryServiceName,
    'X-Registry-Service-Token': config.registryServiceToken,
  };
}

/**
 * Extracts the actual TD document from a potentially wrapped registry response.
 * Some registry endpoints return the TD embedded in a metadata object.
 */
function extractThingDocument(payload: ThingDescription): ThingDescription {
  const embedded = payload.document;
  if (embedded && typeof embedded === 'object' && !Array.isArray(embedded)) {
    return embedded as ThingDescription;
  }
  return payload;
}

/**
 * Extracts a human-readable error message from a registry response or an Axios error.
 *
 * @param error The caught error object.
 * @param fallback A fallback message if no specific error can be extracted.
 * @returns The extracted error message.
 */
export function extractRegistryErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof AxiosError) {
    const payload = error.response?.data;
    if (payload && typeof payload === 'object') {
      const detail = (payload as Record<string, unknown>).detail;
      if (typeof detail === 'string' && detail.trim().length > 0) {
        return detail;
      }
    }
  }

  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }

  return fallback;
}

/**
 * Fetches a Thing Description from the central registry by its unique ID.
 * Calculates a SHA-256 hash of the document for identification and caching purposes.
 *
 * @param thingId The unique identifier of the Thing.
 * @returns A promise resolving to the TD document and its hash.
 * @throws {Error} if the TD cannot be fetched.
 */
export async function fetchThingDescription(thingId: string): Promise<{
  document: ThingDescription;
  hash: string;
}> {
  const encodedId = encodeURIComponent(thingId);

  try {
    const response = await axios.get<ThingDescription>(thingsUrl(encodedId), {
      headers: registryServiceHeaders(),
      timeout: config.requestTimeoutMs,
    });

    const document = extractThingDocument(response.data);
    const serialized = JSON.stringify(document);
    const hash = crypto.createHash('sha256').update(serialized).digest('hex');

    return { document, hash };
  } catch (error) {
    throw new Error(extractRegistryErrorMessage(error, `Failed to fetch Thing Description '${thingId}'`), {
      cause: error,
    });
  }
}

/**
 * Pings the registry's health endpoint to check for reachability.
 *
 * @returns A promise resolving to true if reachable, false otherwise.
 */
export async function pingThingCatalog(): Promise<boolean> {
  try {
    await axios.get(`${config.registryUrl}/health`, {
      timeout: Math.min(config.requestTimeoutMs, 3000),
    });
    return true;
  } catch {
    return false;
  }
}
