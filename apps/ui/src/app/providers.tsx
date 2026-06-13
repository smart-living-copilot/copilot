'use client';

import '@copilotkit/react-core/v2/styles.css';
import { Toaster } from 'sonner';
import { ThemeProvider } from '@/components/theme-provider';
import { JobDetailProvider } from '@/components/jobs/job-detail-context';
import { JobNotificationsProvider } from '@/components/jobs/job-notifications-context';
import { JobTriggerToasts } from '@/components/jobs/job-trigger-toasts';
import { TooltipProvider } from '@/components/ui/tooltip';

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider defaultTheme="system">
      <JobDetailProvider>
        <JobNotificationsProvider>
          <JobTriggerToasts />
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
