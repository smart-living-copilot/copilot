import { type LiveKitTokenResponse } from '@/hooks/media-ingress/types';

export async function requestLiveKitToken(
  chatId: string,
): Promise<LiveKitTokenResponse> {
  const response = await fetch('/api/media/livekit/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ threadId: chatId }),
  });

  const body = (await response.json().catch(() => null)) as
    | (LiveKitTokenResponse & { detail?: string })
    | null;

  if (!response.ok) {
    throw new Error(
      body?.detail || 'Could not load LiveKit connection settings',
    );
  }

  if (!body?.enabled) {
    throw new Error('LiveKit is not configured');
  }

  if (!body.url || !body.token) {
    throw new Error('LiveKit connection settings are incomplete');
  }

  return body;
}

export async function requestLiveKitAgentDispatch(
  connection: LiveKitTokenResponse,
  chatId: string,
) {
  if (!connection.room) {
    throw new Error('LiveKit room is missing');
  }

  const response = await fetch('/api/media/livekit/dispatch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      room: connection.room,
      threadId: chatId,
      participantIdentity: connection.participantIdentity || '',
    }),
  });

  const body = (await response.json().catch(() => null)) as {
    enabled?: boolean;
    dispatched?: boolean;
    detail?: string;
  } | null;

  if (!response.ok) {
    throw new Error(body?.detail || 'Could not start the LiveKit agent');
  }

  if (!body?.enabled || !body.dispatched) {
    throw new Error('LiveKit agent dispatch is not available');
  }
}
