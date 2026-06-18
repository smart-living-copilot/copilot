import assert from "node:assert/strict";
import test from "node:test";

import { handleEvent } from "./events.js";
import {
  __clearActiveThingsForTest,
  __setActiveThingForTest,
  bindingsShapeEqual,
  errorDetail,
} from "./manager.js";
import { canaryEventBindings } from "./triggers.js";
import type { VirtualThingBinding, VirtualThingDefinition } from "./types.js";

test("canaryEventBindings dry-runs emitted events without requiring real emission", async () => {
  const calls: unknown[][] = [];
  const definition: VirtualThingDefinition = {
    id: "virtual:things:counter",
    title: "Counter",
    description: "",
    td: {},
    version: 1,
    status: "active",
    bindings: [
      {
        affordance_type: "event",
        affordance_name: "tick",
        kind: "emitted",
        trigger: { kind: "interval", interval_seconds: 10 },
      },
      {
        affordance_type: "property",
        affordance_name: "ignored",
        kind: "computed",
      },
    ],
  };

  await canaryEventBindings(definition, async (...args: unknown[]) => {
    calls.push(args);
    return null;
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "virtual:things:counter");
  assert.equal(calls[0][1], "tick");
  assert.deepEqual(calls[0][3], { dryRun: true });
});

test("canaryEventBindings uses explicit input for explicit events", async () => {
  const calls: unknown[][] = [];
  const definition: VirtualThingDefinition = {
    id: "virtual:things:manual",
    title: "Manual",
    description: "",
    td: {},
    version: 1,
    status: "active",
    bindings: [
      {
        affordance_type: "event",
        affordance_name: "signal",
        kind: "emitted",
        trigger: { kind: "explicit" },
      },
    ],
  };

  await canaryEventBindings(definition, async (...args: unknown[]) => {
    calls.push(args);
    return null;
  });

  assert.equal(calls.length, 1);
  assert.equal((calls[0][2] as Record<string, unknown>).trigger, "explicit");
  assert.deepEqual(calls[0][3], { dryRun: true });
});

test("errorDetail includes axios response body", () => {
  const error = Object.assign(new Error("Request failed"), {
    response: { data: { detail: "handler failed" } },
  });

  assert.match(errorDetail(error), /handler failed/);
});

test("bindingsShapeEqual ignores ordering but tracks affordances and triggers", () => {
  const a: VirtualThingBinding[] = [
    { affordance_type: "property", affordance_name: "temp", kind: "computed" },
    {
      affordance_type: "event",
      affordance_name: "tick",
      kind: "emitted",
      trigger: { kind: "interval", interval_seconds: 10 },
    },
  ];
  const reordered: VirtualThingBinding[] = [a[1], a[0]];
  assert.equal(bindingsShapeEqual(a, reordered), true);

  const triggerChanged: VirtualThingBinding[] = [
    a[0],
    {
      affordance_type: "event",
      affordance_name: "tick",
      kind: "emitted",
      trigger: { kind: "interval", interval_seconds: 30 },
    },
  ];
  assert.equal(bindingsShapeEqual(a, triggerChanged), false);

  const affordanceAdded: VirtualThingBinding[] = [
    ...a,
    { affordance_type: "action", affordance_name: "reset", kind: "computed" },
  ];
  assert.equal(bindingsShapeEqual(a, affordanceAdded), false);
});

test("handleEvent emits requested virtual Thing events on active things", async () => {
  const emitted: unknown[][] = [];
  __setActiveThingForTest("virtual:things:manual", {
    emitEvent: (...args: unknown[]) => emitted.push(args),
  });

  try {
    await handleEvent({
      event_json: JSON.stringify({
        eventType: "virtualThingEventEmissionRequested",
        id: "virtual:things:manual",
        eventName: "signal",
        payload: { ok: true },
      }),
    });
  } finally {
    __clearActiveThingsForTest();
  }

  assert.deepEqual(emitted, [["signal", { ok: true }]]);
});
