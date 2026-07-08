// Generates src/types.generated.ts from the committed JSON Schema that wotbot
// exports for the servient-facing definition view. Run via `npm run gen:types`.
import { writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { compileFromFile } from "json-schema-to-typescript";

const here = dirname(fileURLToPath(import.meta.url));
const schemaPath = resolve(here, "../schema/servient-view.schema.json");
const outPath = resolve(here, "../src/types.generated.ts");

const bannerComment = `/* eslint-disable */
/**
 * AUTO-GENERATED — do not edit by hand.
 * Source of truth: apps/wotbot/src/wotbot/virtual_things/schemas.py
 *   (VirtualThingServientView). Regenerate with \`npm run gen:types\`,
 *   which requires wotbot's Python venv to export the JSON Schema.
 */`;

const ts = await compileFromFile(schemaPath, {
  bannerComment,
  additionalProperties: false,
});
writeFileSync(outPath, ts, "utf8");
console.log(`Wrote ${outPath}`);
