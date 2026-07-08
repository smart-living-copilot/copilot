import { proxyWotbotJson } from '@/lib/wotbot-backend';
import { cleanupChatResources } from '@/lib/chat-deletion';
import { getCodeExecutorUrl, getWotbotUrl } from '@/lib/backend-env';

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ chatId: string }> },
) {
  const { chatId } = await params;
  return proxyWotbotJson(`/threads/${encodeURIComponent(chatId)}`);
}

export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ chatId: string }> },
) {
  const { chatId } = await params;
  const failures = await cleanupChatResources({
    chatId,
    wotbotUrl: getWotbotUrl(),
    executorUrl: getCodeExecutorUrl(),
    internalApiKey: process.env.INTERNAL_API_KEY,
  });

  if (failures.length) {
    return Response.json(
      {
        detail: 'Failed to fully delete chat state',
        failures,
      },
      { status: 502 },
    );
  }

  return Response.json({ ok: true });
}

export async function PATCH(
  req: Request,
  { params }: { params: Promise<{ chatId: string }> },
) {
  const { chatId } = await params;
  return proxyWotbotJson(`/threads/${encodeURIComponent(chatId)}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': req.headers.get('content-type') || 'application/json',
    },
    body: await req.text(),
  });
}
