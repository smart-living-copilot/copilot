'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { LoaderCircle } from 'lucide-react';

export default function RootPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const resolve = async () => {
      try {
        // Try to find the most recent chat
        const listRes = await fetch('/api/chats');
        if (listRes.ok) {
          const chats: { id: string }[] = await listRes.json();
          if (chats.length > 0 && !cancelled) {
            router.replace(`/chat/${chats[0].id}`);
            return;
          }
        }

        // No chats exist — create one
        const createRes = await fetch('/api/chats', { method: 'POST' });
        if (!createRes.ok) throw new Error('Failed to create chat');
        const chat: { id: string } = await createRes.json();

        if (!cancelled) {
          router.replace(`/chat/${chat.id}`);
        }
      } catch (err) {
        console.error('Failed to resolve chat', err);
        if (!cancelled)
          setError('Could not load or create a chat. Please try again.');
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
