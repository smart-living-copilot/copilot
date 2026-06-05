import { httpClient, httpJson } from '@/lib/http-client';
import { type WotCapability } from '@/components/copilot/chat-tool-calls/web-interface-model';

export interface PanelRecord {
  id: string;
  title: string;
  capabilities: WotCapability[];
  source_thread_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface PanelDetail extends PanelRecord {
  html?: string;
}

interface PanelListResponse {
  items: PanelRecord[];
}

export async function fetchPanels(): Promise<PanelRecord[]> {
  const json = await httpJson<PanelListResponse>('/panels');
  return json.items;
}

export async function pinPanel(input: {
  title: string;
  html: string;
  capabilities: WotCapability[];
  sourceThreadId?: string | null;
}): Promise<PanelRecord> {
  return httpJson<PanelRecord>('/panels', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: input.title,
      html: input.html,
      capabilities: input.capabilities,
      source_thread_id: input.sourceThreadId ?? null,
    }),
  });
}

export async function fetchPanelSource(id: string): Promise<PanelDetail> {
  return httpJson<PanelDetail>(
    `/panels/${encodeURIComponent(id)}?include_html=true`,
  );
}

export async function updatePanel(
  id: string,
  patch: {
    title?: string;
    html?: string;
    capabilities?: WotCapability[];
  },
): Promise<PanelRecord> {
  return httpJson<PanelRecord>(`/panels/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
}

export async function editPanel(
  id: string,
  instruction: string,
): Promise<PanelRecord> {
  return httpJson<PanelRecord>(`/panels/${encodeURIComponent(id)}/edit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ instruction }),
  });
}

export async function deletePanel(id: string): Promise<void> {
  await httpClient(`/panels/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
}
