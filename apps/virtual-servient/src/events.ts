import { config } from "./config.js";
import log from "./logger.js";
import { emitVirtualThingEvent, reconcileThingId } from "./manager.js";
import { getRedisClient } from "./redis.js";

let stopped = false;

async function ensureGroup(): Promise<void> {
  const client = await getRedisClient();
  await client
    .xgroup(
      "CREATE",
      config.thingEventsStream,
      config.thingEventsGroup,
      "$",
      "MKSTREAM",
    )
    .catch((error: any) => {
      if (!String(error?.message || error).includes("BUSYGROUP")) {
        throw error;
      }
    });
}

function fieldsToObject(fields: string[]): Record<string, string> {
  const result: Record<string, string> = {};
  for (let index = 0; index < fields.length; index += 2) {
    result[fields[index] || ""] = fields[index + 1] || "";
  }
  return result;
}

/** Handles one published catalog or virtual event stream message. */
export async function handleEvent(
  fields: Record<string, string>,
): Promise<void> {
  const raw = fields.event_json;
  if (!raw) {
    return;
  }
  const event = JSON.parse(raw);
  if (event.eventType === "virtualThingEventEmissionRequested") {
    const emitted = emitVirtualThingEvent(
      String(event.id || ""),
      String(event.eventName || ""),
      event.payload,
    );
    if (!emitted) {
      log.warn(
        `Received emission request for inactive virtual Thing ${String(event.id || "")}`,
      );
    }
    return;
  }
  if (event.eventType !== "virtualThingDefinitionChanged") {
    return;
  }
  await reconcileThingId(
    String(event.id || ""),
    String(event.action || "update"),
  );
}

/** Starts the Redis stream loop that reconciles virtual Thing changes. */
export async function startDefinitionEventLoop(): Promise<void> {
  stopped = false;
  void (async () => {
    while (!stopped) {
      try {
        await ensureGroup();
        const client = await getRedisClient();
        const response = await client.xreadgroup(
          "GROUP",
          config.thingEventsGroup,
          config.thingEventsConsumer,
          "COUNT",
          10,
          "BLOCK",
          5000,
          "STREAMS",
          config.thingEventsStream,
          ">",
        );
        for (const stream of (response || []) as [
          string,
          [string, string[]][],
        ][]) {
          for (const [id, fields] of stream[1] as [string, string[]][]) {
            await handleEvent(fieldsToObject(fields));
            await client.xack(
              config.thingEventsStream,
              config.thingEventsGroup,
              id,
            );
          }
        }
      } catch (error) {
        if (!stopped) {
          log.warn(`Definition event loop failed: ${error}`);
          await new Promise((resolve) => setTimeout(resolve, 2000));
        }
      }
    }
  })();
}

/** Requests shutdown of the Redis stream loop. */
export function stopDefinitionEventLoop(): void {
  stopped = true;
}
