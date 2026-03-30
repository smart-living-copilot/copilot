import { db } from '@/db';
import { chatSnapshots, chats } from '@/db/schema';
import { cleanupChatResources } from '@/lib/chat-deletion';
import { eq } from 'drizzle-orm';

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

  db.delete(chatSnapshots).where(eq(chatSnapshots.chatId, chatId)).run();
  db.delete(chats).where(eq(chats.id, chatId)).run();

  return Response.json({ ok: true });
}

export async function PATCH(
  req: Request,
  { params }: { params: Promise<{ chatId: string }> },
) {
  const { chatId } = await params;
  const body = (await req.json()) as {
    force?: boolean;
    title?: string;
  };
  const title = body.title?.trim().slice(0, 50);

  if (!title) {
    return Response.json({ detail: 'Title is required' }, { status: 400 });
  }

  const now = new Date();
  const existingChat = db
    .select()
    .from(chats)
    .where(eq(chats.id, chatId))
    .get();

  if (!existingChat) {
    db.insert(chats)
      .values({
        id: chatId,
        title,
        createdAt: now,
        updatedAt: now,
      })
      .run();

    return Response.json({ ok: true, title });
  }

  const nextTitle =
    body.force || existingChat.title === 'New Chat'
      ? title
      : existingChat.title;

  if (nextTitle !== existingChat.title) {
    db.update(chats)
      .set({ title: nextTitle, updatedAt: now })
      .where(eq(chats.id, chatId))
      .run();
  }

  return Response.json({ ok: true, title: nextTitle });
}
