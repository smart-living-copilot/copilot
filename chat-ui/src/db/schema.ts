import { sqliteTable, text, integer } from 'drizzle-orm/sqlite-core';

export const chats = sqliteTable('chats', {
  id: text('id').primaryKey(),
  title: text('title').notNull().default('New Chat'),
  createdAt: integer('createdAt', { mode: 'timestamp' }).notNull(),
  updatedAt: integer('updatedAt', { mode: 'timestamp' }).notNull(),
});

export const chatSnapshots = sqliteTable('chat_snapshots', {
  chatId: text('chatId').primaryKey(),
  messagesJson: text('messagesJson').notNull().default('[]'),
  updatedAt: integer('updatedAt', { mode: 'timestamp' }).notNull(),
});
