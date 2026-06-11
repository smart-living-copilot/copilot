import { evaluateVirtualEvent, fetchCatalogThing } from "./clients/copilot.js";
import log from "./logger.js";
import { getWot } from "./servient.js";
import type { VirtualThingBinding, VirtualThingDefinition } from "./types.js";

export type TriggerActiveThing = {
  thing: { emitEvent: (eventName: string, payload: unknown) => void };
  timers: NodeJS.Timeout[];
  subscriptions: { stop?: () => Promise<void> }[];
};

function eventInput(binding: VirtualThingBinding): Record<string, unknown> {
  if (binding.trigger?.kind === "source_event") {
    return {
      trigger: "source_event",
      source_thing_id: binding.trigger.thing_id,
      source_event_name: binding.trigger.event_name,
      payload: null,
    };
  }
  if (binding.trigger?.kind === "explicit") {
    return {
      trigger: "explicit",
      input: null,
      requested_at: new Date().toISOString(),
    };
  }
  return {
    trigger: "interval",
    fired_at: new Date().toISOString(),
  };
}

async function decodeInteractionValue(value: unknown): Promise<unknown> {
  if (
    value &&
    typeof value === "object" &&
    typeof (value as { value?: unknown }).value === "function"
  ) {
    return (value as { value: () => unknown }).value();
  }
  return value;
}

function errorDetail(error: unknown): string {
  const response = (error as { response?: { data?: unknown } })?.response;
  if (response?.data !== undefined) {
    const data =
      typeof response.data === "string"
        ? response.data
        : JSON.stringify(response.data);
    return `${error} response=${data}`;
  }
  return String(error);
}

async function startIntervalTrigger(
  definition: VirtualThingDefinition,
  binding: VirtualThingBinding,
  active: TriggerActiveThing,
): Promise<void> {
  const seconds = Math.max(1, Number(binding.trigger?.interval_seconds || 0));
  const fire = async () => {
    try {
      const payload = await evaluateVirtualEvent(
        definition.id,
        binding.affordance_name,
        eventInput(binding),
      );
      if (payload !== null && payload !== undefined) {
        active.thing.emitEvent(binding.affordance_name, payload);
      }
    } catch (error) {
      log.warn(
        `Failed to evaluate interval event ${definition.id}/${binding.affordance_name}: ${errorDetail(error)}`,
      );
    }
  };
  const timer = setInterval(() => void fire(), seconds * 1000);
  active.timers.push(timer);
}

async function startSourceEventTrigger(
  definition: VirtualThingDefinition,
  binding: VirtualThingBinding,
  active: TriggerActiveThing,
): Promise<void> {
  const sourceThingId = binding.trigger?.thing_id;
  const sourceEventName = binding.trigger?.event_name;
  if (!sourceThingId || !sourceEventName) {
    return;
  }
  const wot = await getWot();
  const sourceTd = await fetchCatalogThing(sourceThingId);
  const sourceThing = await wot.consume(sourceTd);
  const subscription = await sourceThing.subscribeEvent(
    sourceEventName,
    async (output: unknown) => {
      try {
        const payload = await evaluateVirtualEvent(
          definition.id,
          binding.affordance_name,
          {
            trigger: "source_event",
            source_thing_id: sourceThingId,
            source_event_name: sourceEventName,
            payload: await decodeInteractionValue(output),
          },
        );
        if (payload !== null && payload !== undefined) {
          active.thing.emitEvent(binding.affordance_name, payload);
        }
      } catch (error) {
        log.warn(
          `Failed to evaluate source event ${definition.id}/${binding.affordance_name}: ${errorDetail(error)}`,
        );
      }
    },
  );
  active.subscriptions.push(subscription);
}

/** Dry-runs emitted-event handlers before exposing a virtual Thing. */
export async function canaryEventBindings(
  definition: VirtualThingDefinition,
  evaluate: typeof evaluateVirtualEvent = evaluateVirtualEvent,
): Promise<void> {
  for (const binding of definition.bindings) {
    if (binding.affordance_type !== "event" || binding.kind !== "emitted") {
      continue;
    }
    await evaluate(definition.id, binding.affordance_name, eventInput(binding), {
      dryRun: true,
    });
  }
}

/** Starts runtime triggers for a produced virtual Thing. */
export async function startEventTriggers(
  definition: VirtualThingDefinition,
  active: TriggerActiveThing,
): Promise<void> {
  for (const binding of definition.bindings) {
    if (binding.affordance_type !== "event" || binding.kind !== "emitted") {
      continue;
    }
    if (binding.trigger?.kind === "interval") {
      await startIntervalTrigger(definition, binding, active);
    } else if (binding.trigger?.kind === "source_event") {
      await startSourceEventTrigger(definition, binding, active);
    }
  }
}
