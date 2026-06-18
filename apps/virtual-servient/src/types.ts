import type {
  VirtualThingBindingView,
  VirtualThingServientView,
  VirtualThingTrigger,
} from "./types.generated.js";

/** Open Thing Description document; intentionally untyped beyond an object. */
export type ThingDescription = Record<string, unknown>;

/**
 * The copilot <-> servient contract types are generated from copilot's Pydantic
 * models (see ``types.generated.ts`` / ``schema/servient-view.schema.json``).
 * These aliases keep the names the servient code already uses.
 */
export type VirtualThingDefinition = VirtualThingServientView;
export type VirtualThingBinding = VirtualThingBindingView;
export type { VirtualThingTrigger };
