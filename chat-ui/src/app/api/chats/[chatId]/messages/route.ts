const copilotUrl = process.env.COPILOT_URL || 'http://copilot:8123';
const internalApiKey = process.env.INTERNAL_API_KEY || '';

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ chatId: string }> },
) {
  const { chatId } = await params;

  const response = await fetch(
    `${copilotUrl}/threads/${encodeURIComponent(chatId)}/messages`,
    {
      headers: internalApiKey
        ? { Authorization: `Bearer ${internalApiKey}` }
        : {},
    },
  );

  if (!response.ok) {
    return Response.json({ messages: [] });
  }

  const data = (await response.json()) as { messages: unknown[] };
  return Response.json({ messages: data.messages ?? [] });
}
