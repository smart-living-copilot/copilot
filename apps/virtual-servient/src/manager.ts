import {
  deleteCatalogThing,
  evaluateVirtualEvent,
  fetchCatalogThing,
  fetchDefinition,
  fetchDefinitions,
  invokeVirtualAction,
  readVirtualProperty,
  upsertCatalogThing,
} from './clients/copilot.js';
import { config } from './config.js';
import log from './logger.js';
import { getWot } from './servient.js';
import type { ThingDescription, VirtualThingBinding, VirtualThingDefinition } from './types.js';

type ActiveThing = {
  thing: any;
  timers: NodeJS.Timeout[];
  subscriptions: any[];
  version: number;
};

const activeThings = new Map<string, ActiveThing>();

function affordanceBindings(
  definition: VirtualThingDefinition,
  type: 'property' | 'action' | 'event',
): VirtualThingBinding[] {
  return definition.bindings.filter((binding) => binding.affordance_type === type);
}

async function concreteTd(exposedThing: any, fallback: ThingDescription): Promise<ThingDescription> {
  const document =
    typeof exposedThing.getThingDescription === 'function'
      ? exposedThing.getThingDescription()
      : undefined;
  if (document && typeof document === 'object') {
    return document as ThingDescription;
  }
  return fallback;
}

function concreteBaseForThing(thingId: string): string {
  const base =
    config.publicBaseUrl ||
    `http://${config.wotHost === '0.0.0.0' ? 'localhost' : config.wotHost}:${config.wotPort}`;
  return `${base.replace(/\/+$/, '')}/${encodeURIComponent(thingId)}`;
}

function form(href: string, op: string, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    href,
    op: [op],
    contentType: 'application/json',
    ...extra,
  };
}

function hasConcreteForm(definition: Record<string, unknown>, op: string): boolean {
  const forms = definition.forms;
  if (!Array.isArray(forms)) {
    return false;
  }
  return forms.some((candidate) => {
    if (!candidate || typeof candidate !== 'object') {
      return false;
    }
    const href = String((candidate as Record<string, unknown>).href || '');
    const rawOp = (candidate as Record<string, unknown>).op;
    const ops = Array.isArray(rawOp) ? rawOp.map(String) : [String(rawOp || '')];
    return href.startsWith('http://') || href.startsWith('https://') ? ops.includes(op) : false;
  });
}

function normalizeConcreteForms(document: ThingDescription, thingId: string): ThingDescription {
  const td = JSON.parse(JSON.stringify(document)) as ThingDescription;
  const base = concreteBaseForThing(thingId);
  for (const [section, op] of [
    ['properties', 'readproperty'],
    ['actions', 'invokeaction'],
    ['events', 'subscribeevent'],
  ] as const) {
    const affordances = td[section];
    if (!affordances || typeof affordances !== 'object' || Array.isArray(affordances)) {
      continue;
    }
    for (const [name, rawDefinition] of Object.entries(affordances as Record<string, unknown>)) {
      if (!rawDefinition || typeof rawDefinition !== 'object' || Array.isArray(rawDefinition)) {
        continue;
      }
      const definition = rawDefinition as Record<string, unknown>;
      const existing = Array.isArray(definition.forms)
        ? definition.forms.filter((candidate) => {
            const href =
              candidate && typeof candidate === 'object'
                ? String((candidate as Record<string, unknown>).href || '')
                : '';
            return href && !href.startsWith('urn:');
          })
        : [];
      definition.forms = existing;
      if (hasConcreteForm(definition, op)) {
        continue;
      }
      if (section === 'properties') {
        existing.push(form(`${base}/properties/${encodeURIComponent(name)}`, op, { 'htv:methodName': 'GET' }));
      } else if (section === 'actions') {
        existing.push(form(`${base}/actions/${encodeURIComponent(name)}`, op, { 'htv:methodName': 'POST' }));
      } else {
        existing.push(
          form(`${base}/events/${encodeURIComponent(name)}`, op, {
            subprotocol: 'longpoll',
          }),
        );
      }
    }
  }
  return td;
}

async function decodeInteractionValue(value: unknown): Promise<unknown> {
  if (value && typeof value === 'object' && typeof (value as any).value === 'function') {
    return (value as any).value();
  }
  return value;
}

function tdForProduce(document: ThingDescription): ThingDescription {
  const copy = JSON.parse(JSON.stringify(document)) as ThingDescription;
  for (const section of ['properties', 'actions', 'events']) {
    const affordances = copy[section];
    if (!affordances || typeof affordances !== 'object' || Array.isArray(affordances)) {
      continue;
    }
    for (const definition of Object.values(affordances as Record<string, unknown>)) {
      if (definition && typeof definition === 'object' && !Array.isArray(definition)) {
        delete (definition as Record<string, unknown>).forms;
      }
    }
  }
  return copy;
}

export function errorDetail(error: unknown): string {
  const response = (error as any)?.response;
  if (response?.data !== undefined) {
    const data = typeof response.data === 'string' ? response.data : JSON.stringify(response.data);
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
  await Promise.all(active.subscriptions.map((subscription) => subscription?.stop?.().catch(() => undefined)));
  await Promise.resolve(active.thing?.destroy?.()).catch(() => undefined);
  await Promise.resolve(active.thing?.unexpose?.()).catch(() => undefined);
  await deleteCatalogThing(thingId).catch((error) => log.warn(`Failed to delete catalog TD for ${thingId}: ${error}`));
}

async function startIntervalTrigger(
  definition: VirtualThingDefinition,
  binding: VirtualThingBinding,
  active: ActiveThing,
): Promise<void> {
  const seconds = Math.max(1, Number(binding.trigger?.interval_seconds || 0));
  const fire = async () => {
    try {
      const payload = await evaluateVirtualEvent(definition.id, binding.affordance_name, {
        trigger: 'interval',
        fired_at: new Date().toISOString(),
      });
      if (payload !== null && payload !== undefined) {
        active.thing.emitEvent(binding.affordance_name, payload);
      }
    } catch (error) {
      log.warn(`Failed to evaluate interval event ${definition.id}/${binding.affordance_name}: ${errorDetail(error)}`);
    }
  };
  const timer = setInterval(() => void fire(), seconds * 1000);
  active.timers.push(timer);
}

async function startSourceEventTrigger(
  definition: VirtualThingDefinition,
  binding: VirtualThingBinding,
  active: ActiveThing,
): Promise<void> {
  const sourceThingId = binding.trigger?.thing_id;
  const sourceEventName = binding.trigger?.event_name;
  if (!sourceThingId || !sourceEventName) {
    return;
  }
  const wot = await getWot();
  const sourceTd = await fetchCatalogThing(sourceThingId);
  const sourceThing = await wot.consume(sourceTd);
  const subscription = await sourceThing.subscribeEvent(sourceEventName, async (output: unknown) => {
    try {
      const payload = await evaluateVirtualEvent(definition.id, binding.affordance_name, {
        trigger: 'source_event',
        source_thing_id: sourceThingId,
        source_event_name: sourceEventName,
        payload: await decodeInteractionValue(output),
      });
      if (payload !== null && payload !== undefined) {
        active.thing.emitEvent(binding.affordance_name, payload);
      }
    } catch (error) {
      log.warn(`Failed to evaluate source event ${definition.id}/${binding.affordance_name}: ${errorDetail(error)}`);
    }
  });
  active.subscriptions.push(subscription);
}

export async function canaryEventBindings(
  definition: VirtualThingDefinition,
  evaluate: typeof evaluateVirtualEvent = evaluateVirtualEvent,
): Promise<void> {
  for (const binding of affordanceBindings(definition, 'event')) {
    if (binding.kind !== 'emitted') {
      continue;
    }
    const input =
      binding.trigger?.kind === 'source_event'
        ? {
            trigger: 'source_event',
            source_thing_id: binding.trigger.thing_id,
            source_event_name: binding.trigger.event_name,
            payload: null,
          }
        : {
            trigger: 'interval',
            fired_at: new Date().toISOString(),
          };
    await evaluate(definition.id, binding.affordance_name, input, {
      dryRun: true,
    });
  }
}

export async function reconcileDefinition(definition: VirtualThingDefinition | null, thingId?: string): Promise<void> {
  if (!definition) {
    if (thingId) {
      await stopActiveThing(thingId);
    }
    return;
  }
  const current = activeThings.get(definition.id);
  if (definition.status !== 'active') {
    await stopActiveThing(definition.id);
    return;
  }
  if (current?.version === definition.version) {
    return;
  }
  await stopActiveThing(definition.id);

  const wot = await getWot();
  const td = tdForProduce({ ...definition.td, id: definition.id, title: definition.title });
  const exposedThing = await wot.produce(td);

  for (const binding of affordanceBindings(definition, 'property')) {
    exposedThing.setPropertyReadHandler(binding.affordance_name, async () =>
      readVirtualProperty(definition.id, binding.affordance_name),
    );
  }
  for (const binding of affordanceBindings(definition, 'action')) {
    exposedThing.setActionHandler(binding.affordance_name, async (input: unknown) =>
      invokeVirtualAction(definition.id, binding.affordance_name, await decodeInteractionValue(input)),
    );
  }

  try {
    await canaryEventBindings(definition);
  } catch (error) {
    await Promise.resolve(exposedThing?.destroy?.()).catch(() => undefined);
    await Promise.resolve(exposedThing?.unexpose?.()).catch(() => undefined);
    await deleteCatalogThing(definition.id).catch(() => undefined);
    log.warn(`Virtual Thing canary failed for ${definition.id}; not exposing: ${errorDetail(error)}`);
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

  for (const binding of affordanceBindings(definition, 'event')) {
    if (binding.kind !== 'emitted') {
      continue;
    }
    if (binding.trigger?.kind === 'interval') {
      await startIntervalTrigger(definition, binding, active);
    } else if (binding.trigger?.kind === 'source_event') {
      await startSourceEventTrigger(definition, binding, active);
    }
  }

  await upsertCatalogThing(normalizeConcreteForms(await concreteTd(exposedThing, td), definition.id));
  log.info(`Produced virtual Thing ${definition.id} v${definition.version}`);
}

export async function reconcileAll(): Promise<void> {
  const definitions = await fetchDefinitions();
  const activeIds = new Set(definitions.filter((definition) => definition.status === 'active').map((definition) => definition.id));
  for (const existingId of [...activeThings.keys()]) {
    if (!activeIds.has(existingId)) {
      await stopActiveThing(existingId);
    }
  }
  for (const definition of definitions) {
    await reconcileDefinition(definition);
  }
}

export async function reconcileThingId(thingId: string, action: string): Promise<void> {
  if (action === 'delete') {
    await reconcileDefinition(null, thingId);
    return;
  }
  await reconcileDefinition(await fetchDefinition(thingId), thingId);
}

export function emitVirtualThingEvent(thingId: string, eventName: string, payload: unknown): boolean {
  const active = activeThings.get(thingId);
  if (!active) {
    return false;
  }
  active.thing.emitEvent(eventName, payload);
  return true;
}

export async function stopAll(): Promise<void> {
  await Promise.all([...activeThings.keys()].map((thingId) => stopActiveThing(thingId)));
}

export function activeCount(): number {
  return activeThings.size;
}

export function __setActiveThingForTest(thingId: string, thing: any): void {
  activeThings.set(thingId, {
    thing,
    timers: [],
    subscriptions: [],
    version: 0,
  });
}

export function __clearActiveThingsForTest(): void {
  activeThings.clear();
}
