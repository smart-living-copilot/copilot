import { fetchWotbot } from '@/lib/wotbot-backend';
import { proxyDiscoveryDownload } from '@/lib/discovery-download';

export async function GET(
  request: Request,
  { params }: { params: Promise<{ handle: string }> },
) {
  const { handle } = await params;
  const range = request.headers.get('range');
  const response = await fetchWotbot(
    `/api/discovery/downloads/${encodeURIComponent(handle)}`,
    { headers: range ? { Range: range } : undefined },
  );
  return proxyDiscoveryDownload(response);
}
