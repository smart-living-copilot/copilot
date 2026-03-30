import Database from 'better-sqlite3';
import fs from 'node:fs';
import path from 'node:path';

const dbPath =
  process.env.DATABASE_PATH || path.join(process.cwd(), 'data', 'sqlite.db');

fs.mkdirSync(path.dirname(dbPath), { recursive: true });

const sqlite = new Database(dbPath);

sqlite.exec(`
  CREATE TABLE IF NOT EXISTS chats (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'New Chat',
    createdAt INTEGER NOT NULL,
    updatedAt INTEGER NOT NULL
  );

  CREATE TABLE IF NOT EXISTS chat_snapshots (
    chatId TEXT PRIMARY KEY,
    messagesJson TEXT NOT NULL DEFAULT '[]',
    updatedAt INTEGER NOT NULL
  );
`);

sqlite.close();
