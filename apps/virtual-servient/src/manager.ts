import {
  deleteCatalogThing,
  fetchDefinition,
  fetchDefinitions,
  invokeVirtualAction,
  readVirtualProperty,
  upsertCatalogThing,
} from "./clients/copilot.js";
import log from "./logger.js";
import { getWot } from "./servient.js";
import { concreteCatalogTd, tdForProduce } from "./td.js";
import { canaryEventBindings, startEventTriggers } from "./triggers.js";
import type { VirtualThingDefinition } from "./types.js";

type ActiveThing = {
  thing: any;
  timers: NodeJS.Timeout[];
  subscriptions: any[];
  version: number;
};

const activeThings = new Map<string, ActiveThing>();

async function decodeInteractionValue(value: unknown): Promise<unknown> {
  if (
    value &&
    typeof value === "object" &&
    typeof (value as any).value === "function"
  ) {
    return (value as any).value();
  }
  return value;
}

/** Formats an error with any structured HTTP response body. */
export function errorDetail(error: unknown): string {
  const response = (error as any)?.response;
  if (response?.data !== undefined) {
    const data =
      typeof response.data === "string"
        ? response.data
        : JSON.stringify(response.data);
    return `${error} response=${data}`;
  }
  return String(error);
}

async function stopActiveThing(thingId: string): Promise<void> {
  const active = activeThings.get(thingId);
  if (!active) {
    return;
  }
  activeThings.delete(thingId);
  for (const timer of active.timers) {
    clearInterval(timer);
  }
  await Promise.all(
    active.subscriptions.map((subscription) =>
      subscription?.stop?.().catch(() => undefined),
    ),
  );
  await Promise.resolve(active.thing?.destroy?.()).catch(() => undefined);
  await Promise.resolve(active.thing?.unexpose?.()).catch(() => undefined);
  await deleteCatalogThing(thingId).catch((error) =>
    log.warn(`Failed to delete catalog TD for ${thingId}: ${error}`),
  );
}

/** Reconciles one stored definition with the active produced Thing. */
export async function reconcileDefinition(
  definition: VirtualThingDefinition | null,
  thingId?: string,
): Promise<void> {
  if (!definition) {
    if (thingId) {
      await stopActiveThing(thingId);
    }
    return;
  }
  const current = activeThings.get(definition.id);
  if (definition.status !== "active") {
    await stopActiveThing(definition.id);
    return;
  }
  if (current?.version === definition.version) {
    return;
  }
  await stopActiveThing(definition.id);

  const wot = await getWot();
  const td = tdForProduce({
    ...definition.td,
    id: definition.id,
    title: definition.title,
  });
  const exposedThing = await wot.produce(td);

  for (const binding of definition.bindings.filter(
    (binding) => binding.affordance_type === "property",
  )) {
    exposedThing.setPropertyReadHandler(binding.affordance_name, async () =>
      readVirtualProperty(definition.id, binding.affordance_name),
    );
  }
  for (const binding of definition.bindings.filter(
    (binding) => binding.affordance_type === "action",
  )) {
    exposedThing.setActionHandler(
      binding.affordance_name,
      async (input: unknown) =>
        invokeVirtualAction(
          definition.id,
          binding.affordance_name,
          await decodeInteractionValue(input),
        ),
    );
  }

  try {
    await canaryEventBindings(definition);
  } catch (error) {
    await Promise.resolve(exposedThing?.destroy?.()).catch(() => undefined);
    await Promise.resolve(exposedThing?.unexpose?.()).catch(() => undefined);
    await deleteCatalogThing(definition.id).catch(() => undefined);
    log.warn(
      `Virtual Thing canary failed for ${definition.id}; not exposing: ${errorDetail(error)}`,
    );
    return;
  }

  await exposedThing.expose();
  const active: ActiveThing = {
    thing: exposedThing,
    timers: [],
    subscriptions: [],
    version: definition.version,
  };
  activeThings.set(definition.id, active);

  await startEventTriggers(definition, active);

  await upsertCatalogThing(
    await concreteCatalogTd(exposedThing, td, definition.id),
  );
  log.info(`Produced virtual Thing ${definition.id} v${definition.version}`);
}

/** Reconciles all stored definitions and stops stale active Things. */
export async function reconcileAll(): Promise<void> {
  const definitions = await fetchDefinitions();
  const activeIds = new Set(
    definitions
      .filter((definition) => definition.status === "active")
      .map((definition) => definition.id),
  );
  for (const existingId of [...activeThings.keys()]) {
    if (!activeIds.has(existingId)) {
      await stopActiveThing(existingId);
    }
  }
  for (const definition of definitions) {
    await reconcileDefinition(definition);
  }
}

/** Reconciles one virtual Thing after a definition-change event. */
export async function reconcileThingId(
  thingId: string,
  action: string,
): Promise<void> {
  if (action === "delete") {
    await reconcileDefinition(null, thingId);
    return;
  }
  await reconcileDefinition(await fetchDefinition(thingId), thingId);
}

/** Emits an event on an active produced virtual Thing. */
export function emitVirtualThingEvent(
  thingId: string,
  eventName: string,
  payload: unknown,
): boolean {
  const active = activeThings.get(thingId);
  if (!active) {
    return false;
  }
  active.thing.emitEvent(eventName, payload);
  return true;
}

/** Stops every active produced virtual Thing. */
export async function stopAll(): Promise<void> {
  await Promise.all(
    [...activeThings.keys()].map((thingId) => stopActiveThing(thingId)),
  );
}

/** Returns the number of active produced virtual Things. */
export function activeCount(): number {
  return activeThings.size;
}

/** Inserts an active Thing test double for unit tests. */
export function __setActiveThingForTest(thingId: string, thing: any): void {
  activeThings.set(thingId, {
    thing,
    timers: [],
    subscriptions: [],
    version: 0,
  });
}

/** Clears active Thing test doubles after unit tests. */
export function __clearActiveThingsForTest(): void {
  activeThings.clear();
}
