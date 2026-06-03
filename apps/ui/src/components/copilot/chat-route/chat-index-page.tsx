import { LoaderCircle, MessageSquarePlus } from 'lucide-react';
import { useCallback, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';

import { AppSidebar } from '@/components/chat-sidebar';
import { createChat } from '@/components/copilot/chat-route/chat-api';
import { SiteHeader } from '@/components/site-header';
import { Button } from '@/components/ui/button';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';

export function ChatIndexPage() {
  const router = useRouter();
  const [isCreatingChat, setIsCreatingChat] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const breadcrumbs = useMemo(() => [{ label: 'Chat' }], []);

  const handleNewChat = useCallback(async () => {
    if (isCreatingChat) {
      return null;
    }

    setIsCreatingChat(true);
    setError(null);

    try {
      const chat = await createChat();
      router.push(`/chat/${chat.id}`);
      return chat;
    } catch (createError) {
      console.error('Failed to create chat', createError);
      setError('Could not create a new chat. Please try again.');
      return null;
    } finally {
      setIsCreatingChat(false);
    }
  }, [isCreatingChat, router]);

  return (
    <SidebarProvider className="relative h-dvh overflow-hidden text-foreground">
      <AppSidebar onNewChat={handleNewChat} />

      <SidebarInset>
        <SiteHeader breadcrumbs={breadcrumbs}>
          <Button
            className="md:hidden"
            onClick={() => void handleNewChat()}
            size="sm"
            type="button"
            variant="outline"
          >
            <MessageSquarePlus className="size-4" />
            <span>New chat</span>
          </Button>
        </SiteHeader>

        <div className="flex min-h-0 flex-1 items-center justify-center p-6 md:p-8">
          <div className="mx-auto max-w-lg space-y-4 text-center">
            <div className="space-y-2">
              <h1 className="text-3xl font-semibold tracking-tight text-foreground">
                No chat selected
              </h1>
              <p className="text-sm leading-6 text-muted-foreground md:text-base">
                Start a new conversation or pick an existing thread from the
                history in the sidebar.
              </p>
            </div>

            <div className="flex justify-center">
              <Button
                onClick={() => void handleNewChat()}
                disabled={isCreatingChat}
                size="lg"
                type="button"
              >
                {isCreatingChat ? (
                  <LoaderCircle className="size-4 animate-spin" />
                ) : (
                  <MessageSquarePlus className="size-4" />
                )}
                {isCreatingChat ? 'Creating chat...' : 'Start a new chat'}
              </Button>
            </div>

            {error ? <p className="text-sm text-destructive">{error}</p> : null}
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
