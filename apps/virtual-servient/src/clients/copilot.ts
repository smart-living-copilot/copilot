import axios from "axios";

import { config } from "../config.js";
import type { ThingDescription, VirtualThingDefinition } from "../types.js";

function headers(): Record<string, string> {
  return {
    "X-Registry-Service": config.registryServiceName,
    "X-Registry-Service-Token": config.registryServiceToken,
  };
}

const VIRTUAL_THING_PREFIX = "virtual:things:";

function apiUrl(path: string): string {
  return `${config.registryUrl}${path}`;
}

function unwrapValue(payload: unknown): unknown {
  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    return (payload as Record<string, unknown>).value;
  }
  return payload;
}

/** Fetches active virtual Thing definitions from copilot. */
export async function fetchDefinitions(): Promise<VirtualThingDefinition[]> {
  const response = await axios.get(apiUrl("/api/virtual-things/definitions"), {
    headers: headers(),
    timeout: config.requestTimeoutMs,
  });
  const definitions = response.data?.definitions;
  return Array.isArray(definitions)
    ? (definitions as VirtualThingDefinition[])
    : [];
}

/** Fetches one virtual Thing definition, returning null when it is absent. */
export async function fetchDefinition(
  thingId: string,
): Promise<VirtualThingDefinition | null> {
  try {
    const response = await axios.get(
      apiUrl(`/api/virtual-things/definitions/${encodeURIComponent(thingId)}`),
      {
        headers: headers(),
        timeout: config.requestTimeoutMs,
      },
    );
    return response.data as VirtualThingDefinition;
  } catch (error: any) {
    if (error?.response?.status === 404) {
      return null;
    }
    throw error;
  }
}

/** Reads a virtual Thing property through copilot's dispatcher. */
export async function readVirtualProperty(
  thingId: string,
  propertyName: string,
): Promise<unknown> {
  const response = await axios.get(
    apiUrl(
      `/api/virtual-things/${encodeURIComponent(thingId)}/properties/${encodeURIComponent(propertyName)}`,
    ),
    { headers: headers(), timeout: config.requestTimeoutMs },
  );
  return unwrapValue(response.data);
}

/** Invokes a virtual Thing action through copilot's dispatcher. */
export async function invokeVirtualAction(
  thingId: string,
  actionName: string,
  input: unknown,
): Promise<unknown> {
  const response = await axios.post(
    apiUrl(
      `/api/virtual-things/${encodeURIComponent(thingId)}/actions/${encodeURIComponent(actionName)}`,
    ),
    { input },
    { headers: headers(), timeout: config.requestTimeoutMs },
  );
  return unwrapValue(response.data);
}

/** Evaluates an emitted-event binding and returns the payload to emit. */
export async function evaluateVirtualEvent(
  thingId: string,
  eventName: string,
  input: unknown,
  options: { dryRun?: boolean } = {},
): Promise<unknown | null> {
  const response = await axios.post(
    apiUrl(
      `/api/virtual-things/${encodeURIComponent(thingId)}/events/${encodeURIComponent(eventName)}/evaluate`,
    ),
    { input, dry_run: options.dryRun === true },
    { headers: headers(), timeout: config.requestTimeoutMs },
  );
  return response.data ?? null;
}

/** Registers the concrete produced TD in copilot's catalog. */
export async function upsertCatalogThing(
  document: ThingDescription,
): Promise<void> {
  const thingId = String(document.id || "");
  await axios.put(
    apiUrl(`/api/things/${encodeURIComponent(thingId)}`),
    document,
    {
      headers: headers(),
      timeout: config.requestTimeoutMs,
    },
  );
}

/** Fetches a concrete catalog TD for source-event subscriptions. */
export async function fetchCatalogThing(
  thingId: string,
): Promise<ThingDescription> {
  const response = await axios.get(
    apiUrl(`/api/things/${encodeURIComponent(thingId)}`),
    {
      headers: headers(),
      timeout: config.requestTimeoutMs,
    },
  );
  const payload = response.data;
  if (
    payload?.document &&
    typeof payload.document === "object" &&
    !Array.isArray(payload.document)
  ) {
    return payload.document as ThingDescription;
  }
  return payload as ThingDescription;
}

/** Lists catalog TD ids produced by the virtual servient (virtual:things:). */
export async function listVirtualCatalogThingIds(): Promise<string[]> {
  const perPage = 200;
  const ids: string[] = [];
  for (let page = 1; ; page += 1) {
    const response = await axios.get(apiUrl("/api/things"), {
      headers: headers(),
      params: { page, per_page: perPage },
      timeout: config.requestTimeoutMs,
    });
    const items = response.data?.items;
    const rows: Array<{ id?: unknown }> = Array.isArray(items) ? items : [];
    for (const row of rows) {
      if (
        typeof row.id === "string" &&
        row.id.startsWith(VIRTUAL_THING_PREFIX)
      ) {
        ids.push(row.id);
      }
    }
    const total = Number(response.data?.total ?? 0);
    if (rows.length === 0 || page * perPage >= total) {
      break;
    }
  }
  return ids;
}

/** Deletes the concrete catalog TD for a stopped virtual Thing. */
export async function deleteCatalogThing(thingId: string): Promise<void> {
  await axios
    .delete(apiUrl(`/api/things/${encodeURIComponent(thingId)}`), {
      headers: headers(),
      timeout: config.requestTimeoutMs,
    })
    .catch((error) => {
      if (error?.response?.status !== 404) {
        throw error;
      }
    });
}
