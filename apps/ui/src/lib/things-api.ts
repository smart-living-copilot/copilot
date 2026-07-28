import { httpClient, httpJson } from '@/lib/http-client';

export interface ThingRecord {
  id: string;
  title: string;
  description: string;
  tags: string[];
  source?: string;
  document?: Record<string, unknown>;
  json?: string;
}

export interface EnrichmentDiffItem {
  kind: 'prefix' | 'type' | 'unit';
  path: string;
  value: unknown;
  label: string;
  rationale?: string;
}

export interface ShaclFinding {
  severity: string;
  message: string;
  focus_node?: string;
  focus_label?: string;
  result_path?: string;
  source_shape?: string;
}

export interface EnrichmentValidation {
  ok: boolean;
  attempts: number;
  unknown_iris?: string[];
  warnings?: string[];
  shacl_conforms?: boolean;
  shacl_findings?: ShaclFinding[];
}

export interface EnrichmentResult {
  enriched: Record<string, unknown>;
  diff: EnrichmentDiffItem[];
  validation: EnrichmentValidation;
}

interface ThingListResponse {
  items: ThingRecord[];
  total: number;
}

function parseThingRecord(value: unknown): ThingRecord {
  const v = value as ThingRecord;
  return {
    ...v,
    json: v.document ? JSON.stringify(v.document, null, 2) : undefined,
  };
}

export async function fetchThings(
  page: number,
  perPage: number,
  search: string,
  source?: string,
): Promise<{ data: ThingRecord[]; total: number }> {
  const query = new URLSearchParams({
    page: String(page),
    per_page: String(perPage),
  });
  if (search.trim()) query.set('q', search.trim());
  if (source) query.set('source', source);

  const json = await httpJson<ThingListResponse>(`/things?${query.toString()}`);
  return {
    data: json.items.map(parseThingRecord),
    total: json.total,
  };
}

export async function fetchThing(id: string): Promise<ThingRecord> {
  const json = await httpJson(`/things/${encodeURIComponent(id)}`);
  return parseThingRecord(json);
}

export async function createThing(
  document: Record<string, unknown>,
): Promise<ThingRecord> {
  const json = await httpJson('/things', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(document),
  });
  return parseThingRecord(json);
}

export async function updateThing(
  id: string,
  document: Record<string, unknown>,
): Promise<ThingRecord> {
  const json = await httpJson(`/things/${encodeURIComponent(id)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(document),
  });
  return parseThingRecord(json);
}

export async function enrichThing(
  id: string,
  document: Record<string, unknown>,
): Promise<EnrichmentResult> {
  return httpJson<EnrichmentResult>(
    `/things/${encodeURIComponent(id)}/enrich`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document }),
    },
  );
}

export async function deleteThing(id: string): Promise<void> {
  await httpClient(`/things/${encodeURIComponent(id)}`, { method: 'DELETE' });
}
