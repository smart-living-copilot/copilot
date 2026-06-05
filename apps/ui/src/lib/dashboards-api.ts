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

interface PanelListResponse {
  items: PanelRecord[];
}

export async function fetchPanels(): Promise<PanelRecord[]> {
  const json = await httpJson<PanelListResponse>('/dashboards');
  return json.items;
}

export async function pinPanel(input: {
  title: string;
  html: string;
  capabilities: WotCapability[];
  sourceThreadId?: string | null;
}): Promise<PanelRecord> {
  return httpJson<PanelRecord>('/dashboards', {
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

export async function renamePanel(
  id: string,
  title: string,
): Promise<PanelRecord> {
  return httpJson<PanelRecord>(`/dashboards/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
}

export async function deletePanel(id: string): Promise<void> {
  await httpClient(`/dashboards/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
}
