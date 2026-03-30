import Database from 'better-sqlite3';
import { drizzle } from 'drizzle-orm/better-sqlite3';
import * as schema from './schema';
import path from 'path';

const dbPath =
  process.env.DATABASE_PATH || path.join(process.cwd(), 'data', 'sqlite.db');
const sqlite = new Database(dbPath);

export const db = drizzle(sqlite, { schema });
