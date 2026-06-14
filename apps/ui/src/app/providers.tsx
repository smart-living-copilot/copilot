'use client';

import '@copilotkit/react-core/v2/styles.css';
import { Suspense } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import { Toaster } from 'sonner';
import { ThemeProvider } from '@/components/theme-provider';
import { JobDetailProvider } from '@/components/jobs/job-detail-context';
import { JobNotificationsProvider } from '@/components/jobs/job-notifications-context';
import { JobTriggerToasts } from '@/components/jobs/job-trigger-toasts';
import { TooltipProvider } from '@/components/ui/tooltip';
import { isEmbedDisabledValue } from '@/lib/embed-chat';

function isEmbedChatPath(pathname: string | null): boolean {
  return (
    pathname === '/embed/chat' || pathname?.startsWith('/embed/chat/') === true
  );
}

function JobTriggerToastsGate() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const embedJobEventsDisabled =
    isEmbedChatPath(pathname) &&
    isEmbedDisabledValue(searchParams?.get('jobEvents') ?? null);

  return <JobTriggerToasts enabled={!embedJobEventsDisabled} />;
}

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider defaultTheme="system">
      <JobDetailProvider>
        <JobNotificationsProvider>
          <Suspense fallback={null}>
            <JobTriggerToastsGate />
          </Suspense>
          <TooltipProvider>{children}</TooltipProvider>
          <Toaster
            closeButton
            richColors
            expand
            toastOptions={{ style: { width: '24rem' } }}
          />
        </JobNotificationsProvider>
      </JobDetailProvider>
    </ThemeProvider>
  );
}
