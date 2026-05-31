export interface ThingIndexStatus {
  thing_id: string;
  indexed: boolean;
  stale?: boolean;
  indexed_at?: string;
  summary_source?: string;
  summary_model?: string;
  prompt_version?: string;
  td_hash_match?: boolean;
  summary?: string | null;
  property_names?: string[];
  action_names?: string[];
  event_names?: string[];
}

export interface SecurityDefinition {
  name: string;
  scheme: string;
  [key: string]: unknown;
}

export interface StoredCredential {
  id: string;
  thing_id: string;
  security_name: string;
  scheme: string;
  credentials: Record<string, string>;
  created_at: string | null;
  updated_at: string | null;
}

export interface PropertyDef {
  name: string;
  type?: string;
  readOnly?: boolean;
  observable?: boolean;
  unit?: string;
  description?: string;
}

export interface ActionDef {
  name: string;
  inputSchema?: string;
  outputSchema?: string;
  description?: string;
}

export interface EventDef {
  name: string;
  dataSchema?: string;
  description?: string;
}

export const CREDENTIAL_FIELDS: Record<
  string,
  { label: string; type: string }[]
> = {
  basic: [
    { label: 'Username', type: 'text' },
    { label: 'Password', type: 'password' },
  ],
  bearer: [{ label: 'Token', type: 'password' }],
  apikey: [{ label: 'API Key', type: 'password' }],
  oauth2: [{ label: 'Token', type: 'password' }],
};

export const CREDENTIAL_KEYS: Record<string, string[]> = {
  basic: ['username', 'password'],
  bearer: ['token'],
  apikey: ['apiKey'],
  oauth2: ['token'],
};

export function summarizeSchema(schema: unknown): string {
  if (!schema || typeof schema !== 'object') return '-';

  const parsed = schema as Record<string, unknown>;

  if (parsed.type === 'object' && parsed.properties) {
    const keys = Object.keys(parsed.properties as object);
    return `object { ${keys.join(', ')} }`;
  }

  if (typeof parsed.type === 'string') {
    return parsed.type;
  }

  return 'complex';
}

export function parseProperties(doc: Record<string, unknown>): PropertyDef[] {
  const properties = doc.properties;

  if (
    !properties ||
    typeof properties !== 'object' ||
    Array.isArray(properties)
  ) {
    return [];
  }

  return Object.entries(
    properties as Record<string, Record<string, unknown>>,
  ).map(([name, definition]) => ({
    name,
    type: typeof definition.type === 'string' ? definition.type : undefined,
    readOnly:
      typeof definition.readOnly === 'boolean'
        ? definition.readOnly
        : undefined,
    observable:
      typeof definition.observable === 'boolean'
        ? definition.observable
        : undefined,
    unit: typeof definition.unit === 'string' ? definition.unit : undefined,
    description:
      typeof definition.description === 'string'
        ? definition.description
        : undefined,
  }));
}

export function parseActions(doc: Record<string, unknown>): ActionDef[] {
  const actions = doc.actions;

  if (!actions || typeof actions !== 'object' || Array.isArray(actions)) {
    return [];
  }

  return Object.entries(actions as Record<string, Record<string, unknown>>).map(
    ([name, definition]) => ({
      name,
      inputSchema: summarizeSchema(definition.input),
      outputSchema: summarizeSchema(definition.output),
      description:
        typeof definition.description === 'string'
          ? definition.description
          : undefined,
    }),
  );
}

export function parseEvents(doc: Record<string, unknown>): EventDef[] {
  const events = doc.events;

  if (!events || typeof events !== 'object' || Array.isArray(events)) {
    return [];
  }

  return Object.entries(events as Record<string, Record<string, unknown>>).map(
    ([name, definition]) => ({
      name,
      dataSchema: summarizeSchema(definition.data),
      description:
        typeof definition.description === 'string'
          ? definition.description
          : undefined,
    }),
  );
}

export function parseSecurityDefinitions(
  doc: Record<string, unknown>,
): SecurityDefinition[] {
  const definitions = doc.securityDefinitions;

  if (
    !definitions ||
    typeof definitions !== 'object' ||
    Array.isArray(definitions)
  ) {
    return [];
  }

  return Object.entries(
    definitions as Record<string, Record<string, unknown>>,
  ).map(([name, definition]) => ({
    name,
    scheme:
      typeof definition.scheme === 'string' ? definition.scheme : 'unknown',
    ...definition,
  }));
}

export function formatDateTime(value?: string): string {
  if (!value) return '-';

  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

export function formatIndexerLabel(value?: string): string {
  if (!value) return '-';

  return value
    .split(/[_-]/)
    .filter(Boolean)
    .map((part) =>
      part.length <= 1
        ? part.toUpperCase()
        : part[0].toUpperCase() + part.slice(1),
    )
    .join(' ');
}

export function stringifyThingSecurity(security: unknown): string {
  if (Array.isArray(security)) {
    return security.join(', ');
  }

  if (typeof security === 'string') {
    return security;
  }

  return '-';
}
