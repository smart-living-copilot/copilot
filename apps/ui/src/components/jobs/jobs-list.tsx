'use client';

import {
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import Link from 'next/link';
import {
  Eye,
  Loader2,
  MessagesSquare,
  Plus,
  Play,
  RefreshCw,
  Search,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  formatDateTime,
  getJobStatus,
  getStatusBadgeVariant,
  supportsJobThread,
  supportsTimeFields,
} from '@/lib/job-formatters';
import {
  type JobRecord,
  deleteJob,
  fetchJobs,
  runJobNow,
} from '@/lib/jobs-api';

function getSearchableText(job: JobRecord): string {
  return [
    job.name,
    job.id,
    job.created_from_thread_id,
    job.job_thread_id,
    job.action_kind,
    job.trigger_kind,
    job.schedule_kind,
    job.thing_id,
    job.event_name,
    job.last_error,
    job.last_response,
    job.last_run_status,
    job.waiting_question,
    job.prompt,
    job.analysis_code,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
}

function renderDate(value: string | null, hydrated: boolean): string {
  return hydrated ? formatDateTime(value) : (value ?? 'Not available');
}

function actionLabel(job: JobRecord): string {
  return job.action_kind === 'analysis' ? 'Analysis' : 'Prompt';
}

function triggerLabel(job: JobRecord): string {
  if (job.trigger_kind === 'event') return job.event_name || 'Event';
  if (job.schedule_kind === 'once') return 'Once';
  if (job.interval_seconds) return `${job.interval_seconds}s interval`;
  return 'Time';
}

function targetLabel(job: JobRecord): string {
  if (job.trigger_kind === 'event') {
    return job.thing_id || 'Unbound event target';
  }
  return 'Time trigger';
}

type JobTabValue =
  | 'all'
  | 'active'
  | 'waiting'
  | 'failed'
  | 'time'
  | 'event'
  | 'disabled';

const JOB_TABS_TRIGGER_CLASSNAME =
  'flex-none rounded-none border-b-2 border-transparent px-4 py-2.5 font-medium text-muted-foreground data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none data-active:border-primary data-active:bg-transparent data-active:text-foreground data-active:shadow-none';

const JOB_TABS: { value: JobTabValue; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'active', label: 'Active' },
  { value: 'waiting', label: 'Needs input' },
  { value: 'failed', label: 'Failed' },
  { value: 'time', label: 'Time' },
  { value: 'event', label: 'Events' },
  { value: 'disabled', label: 'Disabled' },
];

function jobMatchesTab(
  tab: JobTabValue,
  job: JobRecord,
  status: ReturnType<typeof getJobStatus>,
): boolean {
  if (tab === 'all') return true;
  if (tab === 'active') return status === 'running' || status === 'queued';
  if (tab === 'waiting') return status === 'waiting_for_input';
  if (tab === 'failed') return status === 'failed';
  if (tab === 'time') return job.trigger_kind === 'time';
  if (tab === 'event') return job.trigger_kind === 'event';
  return status === 'disabled';
}

interface IconActionProps {
  label: string;
  disabled?: boolean;
  children: ReactNode;
  onClick?: () => void;
  href?: string;
  destructive?: boolean;
}

function IconAction({
  label,
  disabled,
  children,
  onClick,
  href,
  destructive,
}: IconActionProps) {
  const button = (
    <Button
      aria-label={label}
      title={label}
      size="icon-sm"
      variant={destructive ? 'destructive' : 'outline'}
      disabled={disabled}
      onClick={onClick}
      asChild={Boolean(href)}
    >
      {href ? <Link href={href}>{children}</Link> : children}
    </Button>
  );

  return (
    <Tooltip>
      <TooltipTrigger asChild>{button}</TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

export function JobsList() {
  const [isHydrated, setIsHydrated] = useState(false);
  const [search, setSearch] = useState('');
  const deferredSearch = useDeferredValue(search);
  const [threadFilter, setThreadFilter] = useState('');
  const deferredThreadFilter = useDeferredValue(threadFilter);
  const [activeTab, setActiveTab] = useState<JobTabValue>('all');
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [isPending, setIsPending] = useState(true);
  const [runningJobId, setRunningJobId] = useState<string | null>(null);
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null);

  const loadJobs = useCallback(async () => {
    setIsPending(true);
    try {
      setJobs(await fetchJobs(deferredThreadFilter));
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to load jobs',
      );
    } finally {
      setIsPending(false);
    }
  }, [deferredThreadFilter]);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  useEffect(() => {
    setIsHydrated(true);
  }, []);

  const now = useMemo(
    () => (isHydrated ? new Date() : new Date(0)),
    [isHydrated],
  );

  const searchedJobs = useMemo(() => {
    const query = deferredSearch.trim().toLowerCase();
    if (!query) return jobs;
    return jobs.filter((job) => getSearchableText(job).includes(query));
  }, [deferredSearch, jobs]);

  const visibleJobs = useMemo(
    () =>
      searchedJobs.filter((job) =>
        jobMatchesTab(activeTab, job, getJobStatus(job, now)),
      ),
    [activeTab, now, searchedJobs],
  );

  const stats = useMemo(() => {
    return searchedJobs.reduce(
      (acc, job) => {
        const status = getJobStatus(job, now);
        acc.total += 1;
        if (status === 'running' || status === 'queued') acc.active += 1;
        if (status === 'waiting_for_input') acc.waiting += 1;
        if (status === 'failed') acc.failed += 1;
        if (job.trigger_kind === 'time') acc.time += 1;
        if (job.trigger_kind === 'event') acc.event += 1;
        if (status === 'disabled') acc.disabled += 1;
        return acc;
      },
      {
        total: 0,
        active: 0,
        waiting: 0,
        failed: 0,
        time: 0,
        event: 0,
        disabled: 0,
      },
    );
  }, [now, searchedJobs]);

  const tabCounts: Record<JobTabValue, number> = {
    all: stats.total,
    active: stats.active,
    waiting: stats.waiting,
    failed: stats.failed,
    time: stats.time,
    event: stats.event,
    disabled: stats.disabled,
  };

  const activeTabLabel =
    JOB_TABS.find((tab) => tab.value === activeTab)?.label ?? 'All';

  const handleRun = useCallback(
    async (jobId: string) => {
      setRunningJobId(jobId);
      try {
        await runJobNow(jobId);
        toast.success('Job run queued.');
        await loadJobs();
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : 'Failed to run job',
        );
      } finally {
        setRunningJobId((current) => (current === jobId ? null : current));
      }
    },
    [loadJobs],
  );

  const handleDelete = useCallback(
    async (job: JobRecord) => {
      if (!window.confirm(`Delete job "${job.name}"?`)) return;

      setDeletingJobId(job.id);
      try {
        await deleteJob(job.id);
        toast.success('Job deleted.');
        await loadJobs();
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : 'Failed to delete job',
        );
      } finally {
        setDeletingJobId((current) => (current === job.id ? null : current));
      }
    },
    [loadJobs],
  );

  return (
    <TooltipProvider>
      <div className="space-y-5">
        <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-1">
            <h1 className="text-3xl font-semibold tracking-tight">Jobs</h1>
            <p className="max-w-3xl text-sm text-muted-foreground">
              Monitor background automations, review recent results, and manage
              hidden job threads.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button asChild>
              <Link href="/jobs/new">
                <Plus className="h-4 w-4" />
                Create
              </Link>
            </Button>
            <Button
              variant="outline"
              onClick={() => void loadJobs()}
              disabled={isHydrated ? isPending : false}
            >
              <RefreshCw
                className={isPending ? 'h-4 w-4 animate-spin' : 'h-4 w-4'}
              />
              Refresh
            </Button>
          </div>
        </section>

        <section className="grid gap-2 sm:grid-cols-2 xl:grid-cols-7">
          {[
            ['Total', stats.total],
            ['Active', stats.active],
            ['Needs input', stats.waiting],
            ['Failed', stats.failed],
            ['Time', stats.time],
            ['Events', stats.event],
            ['Disabled', stats.disabled],
          ].map(([label, value]) => (
            <Card
              key={label}
              size="sm"
              className="rounded-md border-border/70 shadow-sm shadow-black/5"
            >
              <CardContent className="flex min-h-14 items-center justify-between">
                <span className="text-sm text-muted-foreground">{label}</span>
                <span className="text-2xl font-semibold tabular-nums">
                  {value}
                </span>
              </CardContent>
            </Card>
          ))}
        </section>

        <section>
          <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
            <CardContent className="space-y-4 p-4 md:p-5">
              <Tabs
                value={activeTab}
                onValueChange={(value) => setActiveTab(value as JobTabValue)}
                className="space-y-4"
              >
                <div className="overflow-x-auto">
                  <TabsList
                    variant="line"
                    className="h-auto min-w-max gap-0 rounded-none border-b border-border/80 bg-transparent p-0"
                  >
                    {JOB_TABS.map((tab) => (
                      <TabsTrigger
                        key={tab.value}
                        value={tab.value}
                        className={JOB_TABS_TRIGGER_CLASSNAME}
                      >
                        {tab.label}
                        <Badge
                          variant={
                            activeTab === tab.value ? 'secondary' : 'outline'
                          }
                          className="ml-1 h-5 px-1.5 text-[11px]"
                        >
                          {tabCounts[tab.value]}
                        </Badge>
                      </TabsTrigger>
                    ))}
                  </TabsList>
                </div>
              </Tabs>

              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="flex w-full flex-col gap-2 sm:flex-row">
                  <div className="relative w-full lg:max-w-xl">
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                      placeholder="Search jobs"
                      className="pl-9"
                    />
                  </div>
                  <Input
                    value={threadFilter}
                    onChange={(event) => setThreadFilter(event.target.value)}
                    placeholder="Created-from thread id"
                    className="w-full sm:max-w-72"
                  />
                </div>
                <div className="flex min-h-8 items-center gap-2 text-sm text-muted-foreground">
                  <Badge variant="secondary">
                    {visibleJobs.length} visible
                  </Badge>
                  <Badge variant="outline">{activeTabLabel}</Badge>
                  {deferredThreadFilter.trim() ? (
                    <Badge variant="outline">Thread filter active</Badge>
                  ) : null}
                </div>
              </div>

              {isPending ? (
                <div className="flex min-h-48 items-center justify-center rounded-md border">
                  <Loader2 className="h-6 w-6 animate-spin text-primary" />
                </div>
              ) : visibleJobs.length > 0 ? (
                <div className="overflow-x-auto rounded-md border">
                  <Table className="min-w-[920px] table-fixed">
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-[34%]">Job</TableHead>
                        <TableHead className="w-[17%]">State</TableHead>
                        <TableHead className="w-[22%]">Trigger</TableHead>
                        <TableHead className="w-[15%]">Last run</TableHead>
                        <TableHead className="w-[12%] text-right">
                          Actions
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {visibleJobs.map((job) => {
                        const status = getJobStatus(job, now);
                        const busy =
                          runningJobId === job.id || deletingJobId === job.id;

                        return (
                          <TableRow key={job.id}>
                            <TableCell className="align-middle">
                              <div className="min-w-0 space-y-1.5">
                                <Link
                                  href={`/jobs/${job.id}`}
                                  className="block max-w-full truncate font-medium transition-colors hover:text-primary"
                                >
                                  {job.name}
                                </Link>
                                <div className="flex flex-wrap gap-1.5">
                                  <Badge variant="outline">
                                    {actionLabel(job)}
                                  </Badge>
                                </div>
                              </div>
                            </TableCell>
                            <TableCell className="align-middle">
                              <div className="flex flex-wrap gap-1.5">
                                <Badge variant={getStatusBadgeVariant(status)}>
                                  {status}
                                </Badge>
                                {supportsJobThread(job) &&
                                job.waiting_question ? (
                                  <Badge variant="outline">Needs input</Badge>
                                ) : null}
                                {job.last_error && status !== 'failed' ? (
                                  <Badge variant="destructive">Error</Badge>
                                ) : null}
                              </div>
                            </TableCell>
                            <TableCell className="align-middle">
                              <div className="space-y-1 text-sm">
                                <div className="font-medium">
                                  {triggerLabel(job)}
                                </div>
                                <div className="line-clamp-1 text-muted-foreground">
                                  {targetLabel(job)}
                                </div>
                                {supportsTimeFields(job) ? (
                                  <div className="text-xs text-muted-foreground">
                                    Next{' '}
                                    {renderDate(job.next_run_at, isHydrated)}
                                  </div>
                                ) : null}
                              </div>
                            </TableCell>
                            <TableCell className="align-middle text-sm">
                              <div className="space-y-1">
                                <div>{job.last_run_status || 'No runs'}</div>
                                <div className="text-xs text-muted-foreground">
                                  {renderDate(job.last_run_at, isHydrated)}
                                </div>
                              </div>
                            </TableCell>
                            <TableCell className="align-middle">
                              <div className="flex justify-end gap-1.5">
                                <IconAction
                                  label="Details"
                                  disabled={busy}
                                  href={`/jobs/${job.id}`}
                                >
                                  <Eye className="h-3.5 w-3.5" />
                                </IconAction>
                                {supportsJobThread(job) ? (
                                  <IconAction
                                    label="Thread"
                                    href={`/jobs/${job.id}/thread`}
                                  >
                                    <MessagesSquare className="h-3.5 w-3.5" />
                                  </IconAction>
                                ) : null}
                                <IconAction
                                  label="Run now"
                                  disabled={busy}
                                  onClick={() => void handleRun(job.id)}
                                >
                                  {runningJobId === job.id ? (
                                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                  ) : (
                                    <Play className="h-3.5 w-3.5" />
                                  )}
                                </IconAction>
                                <IconAction
                                  label="Delete"
                                  destructive
                                  disabled={busy}
                                  onClick={() => void handleDelete(job)}
                                >
                                  {deletingJobId === job.id ? (
                                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                  ) : (
                                    <Trash2 className="h-3.5 w-3.5" />
                                  )}
                                </IconAction>
                              </div>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
              ) : (
                <div className="rounded-md border border-dashed px-6 py-12 text-center">
                  <h2 className="text-xl font-semibold tracking-tight">
                    No jobs found
                  </h2>
                  <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
                    {deferredSearch.trim()
                      ? `No jobs match "${deferredSearch.trim()}".`
                      : deferredThreadFilter.trim()
                        ? `No jobs were found for thread "${deferredThreadFilter.trim()}".`
                        : activeTab !== 'all'
                          ? `No jobs are currently in ${activeTabLabel.toLowerCase()}.`
                          : 'No automation jobs have been created yet.'}
                  </p>
                  {deferredSearch.trim() ||
                  deferredThreadFilter.trim() ||
                  activeTab !== 'all' ? (
                    <div className="mt-5 flex flex-wrap justify-center gap-2">
                      {deferredSearch.trim() ? (
                        <Button variant="outline" onClick={() => setSearch('')}>
                          Clear search
                        </Button>
                      ) : null}
                      {deferredThreadFilter.trim() ? (
                        <Button
                          variant="outline"
                          onClick={() => setThreadFilter('')}
                        >
                          Clear thread
                        </Button>
                      ) : null}
                      {activeTab !== 'all' ? (
                        <Button
                          variant="outline"
                          onClick={() => setActiveTab('all')}
                        >
                          Show all
                        </Button>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              )}
            </CardContent>
          </Card>
        </section>
      </div>
    </TooltipProvider>
  );
}
