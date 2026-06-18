import {
  deleteCatalogThing,
  fetchDefinition,
  fetchDefinitions,
  invokeVirtualAction,
  listVirtualCatalogThingIds,
  readVirtualProperty,
  upsertCatalogThing,
} from "./clients/copilot.js";
import log from "./logger.js";
import { getWot } from "./servient.js";
import {
  catalogTdWithMetadata,
  concreteCatalogTd,
  tdForProduce,
} from "./td.js";
import { canaryEventBindings, startEventTriggers } from "./triggers.js";
import type {
  ThingDescription,
  VirtualThingBinding,
  VirtualThingDefinition,
} from "./types.js";
import {
  decodeInteractionValue,
  errorDetail,
  type EventSubscription,
  type ExposedThing,
} from "./wot.js";

type ActiveThing = {
  thing: ExposedThing;
  timers: NodeJS.Timeout[];
  subscriptions: EventSubscription[];
  version: number;
  definition: VirtualThingDefinition;
  catalogTd: ThingDescription;
};

const activeThings = new Map<string, ActiveThing>();

export { errorDetail };

/** A stable key for a binding's exposed shape (ignores handler internals). */
function bindingShapeKey(binding: VirtualThingBinding): string {
  return JSON.stringify([
    binding.affordance_type,
    binding.affordance_name,
    binding.kind,
    binding.trigger ?? null,
  ]);
}

/**
 * Whether two binding sets expose the same affordances and triggers. When this
 * holds, a definition change is metadata-only (e.g. semantic enrichment) and the
 * produced Thing, its timers, and its subscriptions can be kept as-is.
 */
export function bindingsShapeEqual(
  a: VirtualThingBinding[],
  b: VirtualThingBinding[],
): boolean {
  if (a.length !== b.length) {
    return false;
  }
  const left = a.map(bindingShapeKey).sort();
  const right = b.map(bindingShapeKey).sort();
  return left.every((key, index) => key === right[index]);
}

async function stopActiveThing(
  thingId: string,
  { keepCatalog = false }: { keepCatalog?: boolean } = {},
): Promise<void> {
  const active = activeThings.get(thingId);
  if (active) {
    activeThings.delete(thingId);
    for (const timer of active.timers) {
      clearInterval(timer);
    }
    await Promise.all(
      active.subscriptions.map((subscription) =>
        Promise.resolve(subscription?.stop?.()).catch(() => undefined),
      ),
    );
    await Promise.resolve(active.thing?.destroy?.()).catch(() => undefined);
    await Promise.resolve(active.thing?.unexpose?.()).catch(() => undefined);
  }
  // Removing the catalog TD is skipped when the caller is about to re-produce the
  // Thing (keepCatalog): leaving the old TD in place until the new one is
  // upserted avoids a window where consumers see no Thing at all.
  if (keepCatalog) {
    return;
  }
  // Otherwise always remove the catalog TD, even when this instance is not
  // tracking the produced Thing (e.g. after a restart). A deleted definition
  // would otherwise leave an orphan TD in the catalog that keeps reappearing.
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
  if (
    current &&
    bindingsShapeEqual(current.definition.bindings, definition.bindings)
  ) {
    await applyMetadataOnlyChange(current, definition);
    return;
  }
  await reproduceThing(definition);
}

/**
 * Applies a metadata-only definition change in place: the affordances and
 * triggers are unchanged, so the produced Thing, timers, and subscriptions stay
 * live and only the catalog TD is re-registered with the new metadata.
 */
async function applyMetadataOnlyChange(
  active: ActiveThing,
  definition: VirtualThingDefinition,
): Promise<void> {
  const catalogTd = catalogTdWithMetadata(
    active.catalogTd,
    { ...definition.td, id: definition.id, title: definition.title },
    definition.id,
  );
  await upsertCatalogThing(catalogTd);
  active.version = definition.version;
  active.definition = definition;
  active.catalogTd = catalogTd;
  log.info(
    `Updated virtual Thing ${definition.id} metadata to v${definition.version}`,
  );
}

/** Stops any current produced Thing and re-produces it from the definition. */
async function reproduceThing(
  definition: VirtualThingDefinition,
): Promise<void> {
  await stopActiveThing(definition.id, { keepCatalog: true });

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
  const catalogTd = await concreteCatalogTd(exposedThing, td, definition.id);
  const active: ActiveThing = {
    thing: exposedThing,
    timers: [],
    subscriptions: [],
    version: definition.version,
    definition,
    catalogTd,
  };
  activeThings.set(definition.id, active);

  await startEventTriggers(definition, active);

  await upsertCatalogThing(catalogTd);
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
  await sweepOrphanCatalogThings(new Set(definitions.map((d) => d.id)));
  for (const definition of definitions) {
    await reconcileDefinition(definition);
  }
}

/**
 * Removes catalog TDs whose virtual Thing definition no longer exists. Each
 * candidate is re-checked against copilot (404) before deletion so a malformed
 * or partial definitions response can never wipe live Things.
 */
async function sweepOrphanCatalogThings(
  definedIds: Set<string>,
): Promise<void> {
  let catalogIds: string[];
  try {
    catalogIds = await listVirtualCatalogThingIds();
  } catch (error) {
    log.warn(`Orphan catalog sweep skipped: ${errorDetail(error)}`);
    return;
  }
  for (const catalogId of catalogIds) {
    if (definedIds.has(catalogId)) {
      continue;
    }
    if ((await fetchDefinition(catalogId)) !== null) {
      continue;
    }
    await deleteCatalogThing(catalogId)
      .then(() => log.info(`Removed orphan catalog TD ${catalogId}`))
      .catch((error) =>
        log.warn(`Failed to remove orphan catalog TD ${catalogId}: ${error}`),
      );
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
export function __setActiveThingForTest(
  thingId: string,
  thing: any,
  overrides: Partial<ActiveThing> = {},
): void {
  activeThings.set(thingId, {
    thing,
    timers: [],
    subscriptions: [],
    version: 0,
    definition: {
      id: thingId,
      title: "",
      description: "",
      td: {},
      version: 0,
      status: "active",
      bindings: [],
    },
    catalogTd: {},
    ...overrides,
  });
}

/** Clears active Thing test doubles after unit tests. */
export function __clearActiveThingsForTest(): void {
  activeThings.clear();
}
