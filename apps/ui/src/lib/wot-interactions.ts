export const DEVICE_INTERACTION_SUMMARY_TYPE = 'wotbot_device_interactions';

export type WotInteraction = {
  affordanceName: string;
  input?: unknown;
  ok: boolean;
  thingId: string;
  type: string;
  uriVariables?: Record<string, unknown>;
  value?: unknown;
};

function parseJsonRecord(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }

  return value as Record<string, unknown>;
}

function parseOptionalRecord(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return undefined;
  }

  const record = value as Record<string, unknown>;
  return Object.keys(record).length ? record : undefined;
}

function normalizeWotInteraction(value: unknown): WotInteraction | null {
  const candidate = parseJsonRecord(value);
  const type = typeof candidate.type === 'string' ? candidate.type : '';
  const uriVariables = parseOptionalRecord(
    candidate.uri_variables ?? candidate.uriVariables,
  );
  const thingId =
    typeof candidate.thing_id === 'string'
      ? candidate.thing_id
      : typeof candidate.thingId === 'string'
        ? candidate.thingId
        : '';

  if (!type || !thingId) {
    return null;
  }

  const affordanceName =
    typeof candidate.name === 'string'
      ? candidate.name
      : typeof candidate.affordanceName === 'string'
        ? candidate.affordanceName
        : '';

  return {
    affordanceName,
    ok: candidate.ok !== false,
    thingId,
    type,
    ...(candidate.input !== undefined ? { input: candidate.input } : {}),
    ...(candidate.value !== undefined ? { value: candidate.value } : {}),
    ...(uriVariables ? { uriVariables } : {}),
  };
}

export function parseWotInteractionList(value: unknown): WotInteraction[] {
  let parsed = value;

  if (typeof parsed === 'string') {
    try {
      parsed = JSON.parse(parsed);
    } catch {
      return [];
    }
  }

  const rawList = Array.isArray(parsed)
    ? parsed
    : parseJsonRecord(parsed).wot_calls;

  if (!Array.isArray(rawList)) {
    return [];
  }

  return rawList.flatMap((entry) => {
    const interaction = normalizeWotInteraction(entry);
    return interaction ? [interaction] : [];
  });
}

export function parseDeviceInteractionSummaryContent(value: unknown) {
  if (typeof value !== 'string') {
    return [];
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    return [];
  }

  const candidate = parseJsonRecord(parsed);
  if (candidate.type !== DEVICE_INTERACTION_SUMMARY_TYPE) {
    return [];
  }

  return parseWotInteractionList(candidate.interactions);
}

export function looksLikeDeviceInteractionSummaryContent(value: unknown) {
  return (
    typeof value === 'string' &&
    value.trimStart().startsWith('{"type"') &&
    value.includes(DEVICE_INTERACTION_SUMMARY_TYPE)
  );
}
