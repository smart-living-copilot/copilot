/** The slice of a node-wot ExposedThing the servient actually drives. */
export interface ExposedThing {
  emitEvent(eventName: string, payload: unknown): void;
  setPropertyReadHandler(name: string, handler: () => Promise<unknown>): void;
  setActionHandler(
    name: string,
    handler: (input: unknown) => Promise<unknown>,
  ): void;
  expose(): Promise<void>;
  destroy?(): Promise<void> | void;
  unexpose?(): Promise<void> | void;
  getThingDescription?(): unknown;
}

/** A subscription handle returned by node-wot's subscribeEvent. */
export interface EventSubscription {
  stop?: () => Promise<void>;
}

/**
 * node-wot hands interaction inputs/outputs as InteractionOutput objects whose
 * payload is read through a ``value()`` method; unwrap to the raw JSON value.
 */
export async function decodeInteractionValue(value: unknown): Promise<unknown> {
  if (
    value &&
    typeof value === "object" &&
    typeof (value as { value?: unknown }).value === "function"
  ) {
    return (value as { value: () => unknown }).value();
  }
  return value;
}

/** Formats an error, appending any structured HTTP response body. */
export function errorDetail(error: unknown): string {
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
