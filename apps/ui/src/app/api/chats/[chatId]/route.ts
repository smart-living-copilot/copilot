import { proxyCopilotJson } from '@/lib/copilot-backend';
import { cleanupChatResources } from '@/lib/chat-deletion';

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ chatId: string }> },
) {
  const { chatId } = await params;
  return proxyCopilotJson(`/threads/${encodeURIComponent(chatId)}`);
}

export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ chatId: string }> },
) {
  const { chatId } = await params;
  const failures = await cleanupChatResources({
    chatId,
    copilotUrl: process.env.COPILOT_URL,
    executorUrl: process.env.CODE_EXECUTOR_URL,
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
  return proxyCopilotJson(`/threads/${encodeURIComponent(chatId)}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': req.headers.get('content-type') || 'application/json',
    },
    body: await req.text(),
  });
}
