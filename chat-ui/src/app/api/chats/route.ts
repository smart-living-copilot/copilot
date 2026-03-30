import { db } from '@/db';
import { chats } from '@/db/schema';
import { desc } from 'drizzle-orm';
import crypto from 'crypto';

export async function GET() {
  const allChats = db.select().from(chats).orderBy(desc(chats.updatedAt)).all();

  return Response.json(allChats);
}

export async function POST() {
  const now = new Date();
  const chat = {
    id: crypto.randomUUID(),
    title: 'New Chat',
    createdAt: now,
    updatedAt: now,
  };

  db.insert(chats).values(chat).run();

  return Response.json(chat);
}
