import { httpClient, httpJson } from '@/lib/http-client';

export interface ThingRecord {
  id: string;
  title: string;
  description: string;
  tags: string[];
  document?: Record<string, unknown>;
  json?: string;
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
): Promise<{ data: ThingRecord[]; total: number }> {
  const query = new URLSearchParams({
    page: String(page),
    per_page: String(perPage),
  });
  if (search.trim()) query.set('q', search.trim());

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

export async function deleteThing(id: string): Promise<void> {
  await httpClient(`/things/${encodeURIComponent(id)}`, { method: 'DELETE' });
}
