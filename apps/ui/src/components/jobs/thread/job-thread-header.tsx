import { useMemo } from 'react';
import Link from 'next/link';
import { Eye, RefreshCw } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  getJobStatus,
  getScheduleLabel,
  getStatusBadgeVariant,
  getStatusLabel,
} from '@/lib/job-formatters';
import { type JobRecord } from '@/lib/jobs-api';

interface JobThreadHeaderProps {
  jobId: string;
  threadId: string;
  job: JobRecord | null;
  runsCount: number;
  eventsCount: number;
  messagesCount: number;
  hasJobThread: boolean;
  isLoading: boolean;
  isReplying: boolean;
  onRefresh: () => void;
}

export function JobThreadHeader({
  jobId,
  threadId,
  job,
  runsCount,
  eventsCount,
  messagesCount,
  hasJobThread,
  isLoading,
  isReplying,
  onRefresh,
}: JobThreadHeaderProps) {
  const status = useMemo(
    () => (job ? getJobStatus(job, new Date()) : null),
    [job],
  );

  return (
    <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div className="space-y-2">
        <div className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight">
            {job?.name || 'Job thread'}
          </h1>
          <p className="break-all font-mono text-xs text-muted-foreground">
            {threadId}
          </p>
        </div>
        {job ? (
          <div className="flex flex-wrap items-center gap-2">
            {status ? (
              <Badge variant={getStatusBadgeVariant(status)}>
                {getStatusLabel(status)}
              </Badge>
            ) : null}
            <Badge variant="outline">{getScheduleLabel(job)}</Badge>
            <Badge variant="outline">{runsCount} runs</Badge>
            {hasJobThread ? (
              <Badge variant="outline">
                {eventsCount || messagesCount}{' '}
                {eventsCount ? 'events' : 'messages'}
              </Badge>
            ) : null}
          </div>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" asChild>
          <Link href={`/jobs/${jobId}`}>
            <Eye className="h-4 w-4" />
            Details
          </Link>
        </Button>
        <Button
          variant="outline"
          onClick={onRefresh}
          disabled={isLoading || isReplying}
        >
          <RefreshCw
            className={isLoading ? 'h-4 w-4 animate-spin' : 'h-4 w-4'}
          />
          Refresh
        </Button>
      </div>
    </section>
  );
}
