export type ThingDescription = Record<string, unknown>;

export type VirtualThingBinding = {
  affordance_type: "property" | "action" | "event";
  affordance_name: string;
  kind: "record" | "computed" | "emitted";
  trigger?: {
    kind: "interval" | "source_event" | "explicit";
    interval_seconds?: number;
    thing_id?: string;
    event_name?: string;
    subscription_input?: unknown;
  } | null;
};

export type VirtualThingDefinition = {
  id: string;
  title: string;
  description: string;
  td: ThingDescription;
  version: number;
  status: "active" | "disabled";
  bindings: VirtualThingBinding[];
};
