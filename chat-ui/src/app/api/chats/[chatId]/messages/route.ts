import { db } from '@/db';
import { chatSnapshots, chats } from '@/db/schema';
import {
  isSnapshotRequestTooLarge,
  serializeSnapshotMessages,
} from '@/lib/chat-snapshots';
import { eq } from 'drizzle-orm';

function parseMessagesJson(value: string) {
  try {
    const parsed = JSON.parse(value);
    return serializeSnapshotMessages(parsed).messages;
  } catch {
    return [];
  }
}

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ chatId: string }> },
) {
  const { chatId } = await params;
  const snapshot = db
    .select()
    .from(chatSnapshots)
    .where(eq(chatSnapshots.chatId, chatId))
    .get();

  return Response.json({
    messages: snapshot ? parseMessagesJson(snapshot.messagesJson) : [],
  });
}

export async function PUT(
  req: Request,
  { params }: { params: Promise<{ chatId: string }> },
) {
  const { chatId } = await params;
  const rawBody = await req.text();
  if (isSnapshotRequestTooLarge(rawBody)) {
    return Response.json(
      { detail: 'Chat snapshot is too large' },
      { status: 413 },
    );
  }

  let body: { messages?: unknown };
  try {
    body = JSON.parse(rawBody) as { messages?: unknown };
  } catch {
    return Response.json({ detail: 'Invalid JSON payload' }, { status: 400 });
  }

  if (!Array.isArray(body.messages)) {
    return Response.json(
      { detail: 'messages must be an array' },
      { status: 400 },
    );
  }

  const now = new Date();
  const { json: messagesJson } = serializeSnapshotMessages(body.messages);
  const existingSnapshot = db
    .select()
    .from(chatSnapshots)
    .where(eq(chatSnapshots.chatId, chatId))
    .get();

  if (existingSnapshot) {
    db.update(chatSnapshots)
      .set({
        messagesJson,
        updatedAt: now,
      })
      .where(eq(chatSnapshots.chatId, chatId))
      .run();
  } else {
    db.insert(chatSnapshots)
      .values({
        chatId,
        messagesJson,
        updatedAt: now,
      })
      .run();
  }

  const existingChat = db
    .select()
    .from(chats)
    .where(eq(chats.id, chatId))
    .get();
  if (existingChat) {
    db.update(chats).set({ updatedAt: now }).where(eq(chats.id, chatId)).run();
  } else {
    db.insert(chats)
      .values({
        id: chatId,
        title: 'New Chat',
        createdAt: now,
        updatedAt: now,
      })
      .run();
  }

  return Response.json({ ok: true });
}
