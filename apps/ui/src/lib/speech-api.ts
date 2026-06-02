import { httpClient, httpJson } from '@/lib/http-client';

export async function synthesizeSpeech(text: string): Promise<Blob> {
  const response = await httpClient('/speech/tts', {
    method: 'POST',
    headers: {
      Accept: 'audio/mpeg',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ text }),
  });
  return response.blob();
}

export async function transcribeSpeech(audio: Blob): Promise<string> {
  const json = await httpJson<{ text?: string }>('/speech/transcriptions', {
    method: 'POST',
    headers: {
      'Content-Type': audio.type || 'audio/webm',
      'X-Filename': filenameForAudioType(audio.type),
    },
    body: audio,
  });
  return (json.text || '').trim();
}

function filenameForAudioType(contentType: string): string {
  if (contentType.includes('wav')) return 'answer.wav';
  if (contentType.includes('mpeg') || contentType.includes('mp3')) {
    return 'answer.mp3';
  }
  if (contentType.includes('ogg')) return 'answer.ogg';
  return 'answer.webm';
}
