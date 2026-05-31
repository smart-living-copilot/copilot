import { proxyCopilotJson } from '@/lib/copilot-backend';

export async function GET() {
  return proxyCopilotJson('/threads');
}

export async function POST() {
  return proxyCopilotJson('/threads', { method: 'POST' });
}
