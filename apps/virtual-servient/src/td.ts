import type { ThingDescription } from "./types.js";
import { config } from "./config.js";

async function concreteTd(
  exposedThing: { getThingDescription?: () => unknown },
  fallback: ThingDescription,
): Promise<ThingDescription> {
  const document =
    typeof exposedThing.getThingDescription === "function"
      ? exposedThing.getThingDescription()
      : undefined;
  if (document && typeof document === "object") {
    return document as ThingDescription;
  }
  return fallback;
}

function concreteBaseForThing(thingId: string): string {
  const base =
    config.publicBaseUrl ||
    `http://${config.wotHost === "0.0.0.0" ? "localhost" : config.wotHost}:${config.wotPort}`;
  return `${base.replace(/\/+$/, "")}/${encodeURIComponent(thingId)}`;
}

function form(
  href: string,
  op: string,
  extra: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    href,
    op: [op],
    contentType: "application/json",
    ...extra,
  };
}

function hasConcreteForm(
  definition: Record<string, unknown>,
  op: string,
): boolean {
  const forms = definition.forms;
  if (!Array.isArray(forms)) {
    return false;
  }
  return forms.some((candidate) => {
    if (!candidate || typeof candidate !== "object") {
      return false;
    }
    const href = String((candidate as Record<string, unknown>).href || "");
    const rawOp = (candidate as Record<string, unknown>).op;
    const ops = Array.isArray(rawOp)
      ? rawOp.map(String)
      : [String(rawOp || "")];
    return href.startsWith("http://") || href.startsWith("https://")
      ? ops.includes(op)
      : false;
  });
}

function affordanceMap(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function withFallbackAffordances(
  document: ThingDescription,
  fallback: ThingDescription,
): ThingDescription {
  const td = JSON.parse(JSON.stringify(document)) as ThingDescription;
  for (const section of ["properties", "actions", "events"]) {
    const fallbackAffordances = affordanceMap(fallback[section]);
    if (!fallbackAffordances) {
      continue;
    }
    td[section] = {
      ...fallbackAffordances,
      ...(affordanceMap(td[section]) || {}),
    };
  }
  return td;
}

function normalizeConcreteForms(
  document: ThingDescription,
  thingId: string,
): ThingDescription {
  const td = JSON.parse(JSON.stringify(document)) as ThingDescription;
  const base = concreteBaseForThing(thingId);
  for (const [section, op] of [
    ["properties", "readproperty"],
    ["actions", "invokeaction"],
    ["events", "subscribeevent"],
  ] as const) {
    const affordances = td[section];
    if (
      !affordances ||
      typeof affordances !== "object" ||
      Array.isArray(affordances)
    ) {
      continue;
    }
    for (const [name, rawDefinition] of Object.entries(
      affordances as Record<string, unknown>,
    )) {
      if (
        !rawDefinition ||
        typeof rawDefinition !== "object" ||
        Array.isArray(rawDefinition)
      ) {
        continue;
      }
      const definition = rawDefinition as Record<string, unknown>;
      const existing = Array.isArray(definition.forms)
        ? definition.forms.filter((candidate) => {
            const href =
              candidate && typeof candidate === "object"
                ? String((candidate as Record<string, unknown>).href || "")
                : "";
            return href && !href.startsWith("urn:");
          })
        : [];
      definition.forms = existing;
      if (hasConcreteForm(definition, op)) {
        continue;
      }
      if (section === "properties") {
        existing.push(
          form(`${base}/properties/${encodeURIComponent(name)}`, op, {
            "htv:methodName": "GET",
          }),
        );
      } else if (section === "actions") {
        existing.push(
          form(`${base}/actions/${encodeURIComponent(name)}`, op, {
            "htv:methodName": "POST",
          }),
        );
      } else {
        existing.push(
          form(`${base}/events/${encodeURIComponent(name)}`, op, {
            subprotocol: "longpoll",
          }),
        );
      }
    }
  }
  return td;
}

/** Builds the concrete TD that should be registered in the catalog. */
export async function concreteCatalogTd(
  exposedThing: { getThingDescription?: () => unknown },
  fallback: ThingDescription,
  thingId: string,
): Promise<ThingDescription> {
  return normalizeConcreteForms(
    withFallbackAffordances(await concreteTd(exposedThing, fallback), fallback),
    thingId,
  );
}

/** Removes abstract forms before passing a TD to node-wot produce. */
export function tdForProduce(document: ThingDescription): ThingDescription {
  const copy = JSON.parse(JSON.stringify(document)) as ThingDescription;
  for (const section of ["properties", "actions", "events"]) {
    const affordances = copy[section];
    if (
      !affordances ||
      typeof affordances !== "object" ||
      Array.isArray(affordances)
    ) {
      continue;
    }
    for (const definition of Object.values(
      affordances as Record<string, unknown>,
    )) {
      if (
        definition &&
        typeof definition === "object" &&
        !Array.isArray(definition)
      ) {
        delete (definition as Record<string, unknown>).forms;
      }
    }
  }
  return copy;
}
