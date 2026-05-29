'use client';

import '@copilotkit/react-core/v2/styles.css';
import { ThemeProvider } from 'next-themes';
import { Toaster } from 'sonner';
import { JobDetailProvider } from '@/components/jobs/job-detail-context';
import { JobTriggerToasts } from '@/components/jobs/job-trigger-toasts';
import { TooltipProvider } from '@/components/ui/tooltip';

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <JobDetailProvider>
        <JobTriggerToasts />
        <TooltipProvider>{children}</TooltipProvider>
        <Toaster />
      </JobDetailProvider>
    </ThemeProvider>
  );
}
