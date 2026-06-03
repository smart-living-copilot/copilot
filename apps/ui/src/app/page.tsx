'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { LoaderCircle } from 'lucide-react';

async function readErrorMessage(res: Response, fallback: string) {
  try {
    const contentType = res.headers.get('content-type') ?? '';
    if (contentType.includes('application/json')) {
      const body = (await res.json()) as {
        detail?: unknown;
        error?: unknown;
        message?: unknown;
      };
      const detail = body.detail ?? body.error ?? body.message;
      if (typeof detail === 'string' && detail.trim()) {
        return `${fallback} (${res.status}: ${detail.trim()})`;
      }
    } else {
      const text = (await res.text()).trim();
      if (text) {
        return `${fallback} (${res.status}: ${text.slice(0, 180)})`;
      }
    }
  } catch {
    // Keep the page calm if an upstream error body cannot be parsed.
  }

  return `${fallback} (${res.status})`;
}

export default function RootPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const resolve = async () => {
      try {
        // Try to find the most recent chat
        const listRes = await fetch('/api/chats');
        if (!listRes.ok) {
          throw new Error(
            await readErrorMessage(listRes, 'Could not load chats'),
          );
        }

        const chats: { id: string }[] = await listRes.json();
        if (chats.length > 0 && !cancelled) {
          router.replace(`/chat/${chats[0].id}`);
          return;
        }

        // No chats exist — create one
        const createRes = await fetch('/api/chats', { method: 'POST' });
        if (!createRes.ok) {
          throw new Error(
            await readErrorMessage(createRes, 'Could not create chat'),
          );
        }
        const chat: { id: string } = await createRes.json();

        if (!cancelled) {
          router.replace(`/chat/${chat.id}`);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : 'Could not load or create a chat. Please try again.',
          );
        }
      }
    };

    void resolve();
    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <div className="flex h-dvh items-center justify-center text-muted-foreground">
      {error ? (
        <p className="text-sm text-destructive">{error}</p>
      ) : (
        <LoaderCircle className="size-6 animate-spin" />
      )}
    </div>
  );
}
