import { httpClient, httpJson } from '@/lib/http-client';

export type VirtualAffordanceType = 'property' | 'action' | 'event';
export type VirtualBindingKind = 'record' | 'computed' | 'emitted';
export type VirtualThingStatus = 'active' | 'disabled';

export interface VirtualThingCapability {
  thing_id: string;
  affordances: string[];
  ops: string[];
}

export interface VirtualThingTrigger {
  kind: 'interval' | 'source_event' | 'explicit';
  interval_seconds?: number | null;
  thing_id?: string | null;
  event_name?: string | null;
  subscription_input?: unknown;
}

export interface VirtualThingBinding {
  affordance_type: VirtualAffordanceType;
  affordance_name: string;
  kind: VirtualBindingKind;
  handler_code: string | null;
  config?: Record<string, unknown>;
  capabilities: VirtualThingCapability[];
  trigger?: VirtualThingTrigger | null;
  state?: unknown;
  timeout_seconds?: number;
  cache_ttl_seconds?: number;
}

export interface VirtualThingDefinition {
  id: string;
  title: string;
  description: string;
  owner_thread_id?: string | null;
  td: Record<string, unknown>;
  version: number;
  status: VirtualThingStatus;
  bindings: VirtualThingBinding[];
}

export interface VirtualValidationIssue {
  affordance_type?: VirtualAffordanceType | null;
  affordance_name?: string | null;
  phase: string;
  message: string;
}

export interface VirtualValidationReport {
  ok: boolean;
  smoke_tested: boolean;
  issues: VirtualValidationIssue[];
}

export type DefineVirtualThingRequest = Pick<
  VirtualThingDefinition,
  | 'id'
  | 'title'
  | 'description'
  | 'td'
  | 'status'
  | 'bindings'
  | 'owner_thread_id'
>;

export type DefineVirtualThingResult =
  | { definition: VirtualThingDefinition; validationReport?: never }
  | { definition?: never; validationReport: VirtualValidationReport };

interface VirtualThingListResponse {
  definitions: VirtualThingDefinition[];
}

function definitionPath(id: string) {
  return `/virtual-things/definitions/${encodeURIComponent(id)}`;
}

function mapBindingForRequest(
  binding: VirtualThingBinding,
): VirtualThingBinding {
  return {
    affordance_type: binding.affordance_type,
    affordance_name: binding.affordance_name,
    kind: binding.kind,
    handler_code: binding.handler_code,
    config: binding.config ?? {},
    capabilities: binding.capabilities ?? [],
    trigger: binding.trigger ?? null,
    state: binding.state ?? null,
    timeout_seconds: binding.timeout_seconds ?? 30,
    cache_ttl_seconds: binding.cache_ttl_seconds ?? 30,
  };
}

export function buildDefineVirtualThingRequest(
  definition: VirtualThingDefinition,
  overrides: Partial<DefineVirtualThingRequest> = {},
): DefineVirtualThingRequest {
  return {
    id: overrides.id ?? definition.id,
    title: overrides.title ?? definition.title,
    description: overrides.description ?? definition.description,
    td: overrides.td ?? definition.td,
    status: overrides.status ?? definition.status,
    bindings: (overrides.bindings ?? definition.bindings).map(
      mapBindingForRequest,
    ),
    owner_thread_id:
      overrides.owner_thread_id ?? definition.owner_thread_id ?? null,
  };
}

function errorMessageFromDetail(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail;
  if (
    detail &&
    typeof detail === 'object' &&
    'error' in detail &&
    typeof detail.error === 'string'
  ) {
    return detail.error;
  }
  if (
    detail &&
    typeof detail === 'object' &&
    'message' in detail &&
    typeof detail.message === 'string'
  ) {
    return detail.message;
  }
  return fallback;
}

export async function fetchVirtualThingDefinitions(
  includeDisabled = true,
): Promise<VirtualThingDefinition[]> {
  const query = new URLSearchParams({
    include_disabled: String(includeDisabled),
  });
  const json = await httpJson<VirtualThingListResponse>(
    `/virtual-things/definitions?${query.toString()}`,
  );
  return json.definitions;
}

export async function fetchVirtualThingDefinition(
  id: string,
  includeDisabled = true,
): Promise<VirtualThingDefinition> {
  const query = new URLSearchParams({
    include_disabled: String(includeDisabled),
  });
  return httpJson<VirtualThingDefinition>(
    `${definitionPath(id)}?${query.toString()}`,
  );
}

export async function deleteVirtualThing(id: string): Promise<void> {
  await httpClient(definitionPath(id), { method: 'DELETE' });
}

export async function defineVirtualThing(
  id: string,
  request: DefineVirtualThingRequest,
): Promise<DefineVirtualThingResult> {
  const res = await fetch(`/api${definitionPath(id)}`, {
    method: 'PUT',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });
  const body = await res.json().catch(() => ({}));

  if (res.ok) {
    return { definition: body as VirtualThingDefinition };
  }

  const detail = (body as { detail?: unknown }).detail;
  if (
    res.status === 400 &&
    detail &&
    typeof detail === 'object' &&
    'validation_report' in detail
  ) {
    return {
      validationReport: detail.validation_report as VirtualValidationReport,
    };
  }

  throw new Error(
    errorMessageFromDetail(detail, `Request failed (${res.status})`),
  );
}

export async function setVirtualThingStatus(
  id: string,
  status: VirtualThingStatus,
): Promise<DefineVirtualThingResult> {
  const definition = await fetchVirtualThingDefinition(id, true);
  return defineVirtualThing(
    id,
    buildDefineVirtualThingRequest(definition, { status }),
  );
}

export async function readVirtualProperty(
  id: string,
  name: string,
): Promise<unknown> {
  return httpJson(
    `/virtual-things/${encodeURIComponent(id)}/properties/${encodeURIComponent(name)}`,
  );
}

export async function invokeVirtualAction(
  id: string,
  name: string,
  input: unknown,
): Promise<unknown> {
  return httpJson(
    `/virtual-things/${encodeURIComponent(id)}/actions/${encodeURIComponent(name)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input }),
    },
  );
}

export async function evaluateVirtualEvent(
  id: string,
  name: string,
  input: unknown,
  dryRun: boolean,
): Promise<unknown> {
  return httpJson(
    `/virtual-things/${encodeURIComponent(id)}/events/${encodeURIComponent(name)}/evaluate`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input, dry_run: dryRun }),
    },
  );
}

export async function emitVirtualEvent(
  id: string,
  name: string,
  input: unknown,
): Promise<unknown> {
  return httpJson(
    `/virtual-things/${encodeURIComponent(id)}/events/${encodeURIComponent(name)}/emit`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input }),
    },
  );
}
