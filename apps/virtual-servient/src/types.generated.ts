/* eslint-disable */
/**
 * AUTO-GENERATED — do not edit by hand.
 * Source of truth: apps/copilot/src/copilot/virtual_things/schemas.py
 *   (VirtualThingServientView). Regenerate with `npm run gen:types`,
 *   which requires copilot's Python venv to export the JSON Schema.
 */

export type AffordanceName = string;
export type AffordanceType = "property" | "action" | "event";
export type Kind = "record" | "computed" | "emitted";
export type EventName = string | null;
export type IntervalSeconds = number | null;
export type Kind1 = "interval" | "source_event" | "explicit";
export type ThingId = string | null;
export type Bindings = VirtualThingBindingView[];
export type Description = string;
export type Id = string;
export type Status = "active" | "disabled";
export type Title = string;
export type Version = number;

/**
 * Wire shape served to virtual-servient and the single source of truth for
 * the copilot <-> servient contract.
 *
 * ``apps/virtual-servient/src/types.generated.ts`` is generated from this
 * model's JSON schema (see ``contract_export``); never hand-edit that file.
 */
export interface VirtualThingServientView {
  bindings: Bindings;
  description: Description;
  id: Id;
  status: Status;
  td: Td;
  title: Title;
  version: Version;
}
/**
 * The slice of a binding that virtual-servient needs to expose a Thing.
 *
 * Deliberately omits ``handler_code``, ``capabilities``, ``config``, and
 * ``state``: the servient never runs handlers (it delegates every interaction
 * back to copilot's dispatcher), so shipping handler source or capability
 * grants to it would be needless exposure and wire weight.
 */
export interface VirtualThingBindingView {
  affordance_name: AffordanceName;
  affordance_type: AffordanceType;
  kind: Kind;
  trigger?: VirtualThingTrigger | null;
}
export interface VirtualThingTrigger {
  event_name?: EventName;
  interval_seconds?: IntervalSeconds;
  kind: Kind1;
  subscription_input?: unknown;
  thing_id?: ThingId;
}
export interface Td {
  [k: string]: unknown;
}
