import assert from "node:assert/strict";
import test from "node:test";

import { concreteCatalogTd } from "./td.js";

test("concreteCatalogTd keeps fallback affordances missing from exposed TD", async () => {
  const td = await concreteCatalogTd(
    {
      getThingDescription: () => ({
        id: "virtual:things:multi",
        title: "Multi",
        properties: {
          temperature: { type: "number" },
        },
      }),
    },
    {
      id: "virtual:things:multi",
      title: "Multi",
      properties: {
        temperature: { type: "number" },
        humidity: { type: "number" },
      },
      actions: {
        refresh: { output: { type: "object" } },
        reset: { input: { type: "object" }, output: { type: "object" } },
      },
      events: {
        tick: { data: { type: "object" } },
        alarm: { data: { type: "object" } },
      },
    },
    "virtual:things:multi",
  );

  assert.deepEqual(Object.keys(td.properties as object).sort(), [
    "humidity",
    "temperature",
  ]);
  assert.deepEqual(Object.keys(td.actions as object).sort(), [
    "refresh",
    "reset",
  ]);
  assert.deepEqual(Object.keys(td.events as object).sort(), ["alarm", "tick"]);
});
