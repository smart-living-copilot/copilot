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
  Ban,
  Eye,
  Loader2,
  MessagesSquare,
  MoreHorizontal,
  Pause,
  Pencil,
  Play,
  Plus,
  Power,
  RefreshCw,
  Search,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';

import { ConfirmDialog } from '@/components/jobs/confirm-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
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
import { useJobEvents } from '@/hooks/use-job-events';
import {
  formatInterval,
  formatRelativeTime,
  getJobStatus,
  getStatusBadgeVariant,
  getStatusLabel,
  supportsJobReply,
  supportsJobThread,
  supportsTimeFields,
} from '@/lib/job-formatters';
import {
  type JobRecord,
  cancelJobRun,
  deleteJob,
  fetchJobs,
  runJobNow,
  setJobEnabled,
} from '@/lib/jobs-api';

function getSearchableText(job: JobRecord): string {
  return [
    job.name,
    job.id,
    job.job_thread_id,
    job.action_kind,
    job.interaction_mode,
    job.output_kind,
    job.trigger_kind,
    job.schedule_kind,
    job.cron_expression,
    job.cron_timezone,
    job.thing_id,
    job.event_name,
    job.last_error,
    job.last_response,
    job.last_run_status,
    job.waiting_question,
    job.virtual_thing_id,
    job.prompt,
    job.analysis_code,
    job.record_schema ? JSON.stringify(job.record_schema) : null,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
}

function renderRelative(
  value: string | null,
  hydrated: boolean,
  now: Date,
): string {
  return hydrated ? formatRelativeTime(value, now) : (value ?? 'Not available');
}

function actionLabel(job: JobRecord): string {
  if (job.output_kind === 'structured_record') return 'Record prompt';
  return job.action_kind === 'analysis' ? 'Analysis' : 'Prompt';
}

function triggerLabel(job: JobRecord): string {
  if (job.trigger_kind === 'event') return job.event_name || 'Event';
  if (job.schedule_kind === 'once') return 'Once';
  if (job.schedule_kind === 'cron' && job.cron_expression)
    return `Cron ${job.cron_expression}`;
  if (job.interval_seconds)
    return `Every ${formatInterval(job.interval_seconds)}`;
  return 'Time';
}

function targetLabel(job: JobRecord): string {
  if (job.trigger_kind === 'event') {
    return job.thing_id || 'Unbound event target';
  }
  return 'Time trigger';
}

function hasActiveRun(job: JobRecord): boolean {
  return Boolean(job.active_run_id);
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
  { value: 'disabled', label: 'Paused' },
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

interface JobRowActionsProps {
  job: JobRecord;
  busy: boolean;
  running: boolean;
  onRun: () => void;
  onToggleEnabled: () => void;
  onCancel: () => void;
  onDelete: () => void;
}

function JobRowActions({
  job,
  busy,
  running,
  onRun,
  onToggleEnabled,
  onCancel,
  onDelete,
}: JobRowActionsProps) {
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);

  return (
    <div className="flex justify-end gap-1.5">
      <ConfirmDialog
        open={confirmDeleteOpen}
        onOpenChange={setConfirmDeleteOpen}
        title={`Delete "${job.name}"?`}
        description="This permanently removes the job, its schedule, and its run history. This cannot be undone."
        confirmLabel="Delete"
        destructive
        onConfirm={onDelete}
      />
      <IconAction label="Run now" disabled={busy} onClick={onRun}>
        {running ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Play className="h-3.5 w-3.5" />
        )}
      </IconAction>
      <IconAction
        label={job.enabled ? 'Pause' : 'Resume'}
        disabled={busy}
        onClick={onToggleEnabled}
      >
        {job.enabled ? (
          <Pause className="h-3.5 w-3.5" />
        ) : (
          <Power className="h-3.5 w-3.5" />
        )}
      </IconAction>
      <DropdownMenu>
        <Tooltip>
          <TooltipTrigger asChild>
            <DropdownMenuTrigger asChild>
              <Button
                aria-label="More actions"
                size="icon-sm"
                variant="outline"
                disabled={busy}
              >
                <MoreHorizontal className="h-3.5 w-3.5" />
              </Button>
            </DropdownMenuTrigger>
          </TooltipTrigger>
          <TooltipContent>More actions</TooltipContent>
        </Tooltip>
        <DropdownMenuContent align="end">
          {supportsJobReply(job) ? (
            <DropdownMenuItem asChild>
              <Link href={`/jobs/${job.id}`}>
                <MessagesSquare className="h-4 w-4" />
                Answer question
              </Link>
            </DropdownMenuItem>
          ) : null}
          <DropdownMenuItem asChild>
            <Link href={`/jobs/${job.id}`}>
              <Eye className="h-4 w-4" />
              View details
            </Link>
          </DropdownMenuItem>
          {supportsJobThread(job) ? (
            <DropdownMenuItem asChild>
              <Link href={`/jobs/${job.id}/thread`}>
                <MessagesSquare className="h-4 w-4" />
                View transcript
              </Link>
            </DropdownMenuItem>
          ) : null}
          <DropdownMenuItem asChild>
            <Link href={`/jobs/${job.id}/edit`}>
              <Pencil className="h-4 w-4" />
              Edit
            </Link>
          </DropdownMenuItem>
          {hasActiveRun(job) ? (
            <DropdownMenuItem onSelect={() => onCancel()}>
              <Ban className="h-4 w-4" />
              Cancel run
            </DropdownMenuItem>
          ) : null}
          <DropdownMenuSeparator />
          <DropdownMenuItem
            variant="destructive"
            onSelect={(event) => {
              event.preventDefault();
              setConfirmDeleteOpen(true);
            }}
          >
            <Trash2 className="h-4 w-4" />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

export function JobsList() {
  const [isHydrated, setIsHydrated] = useState(false);
  const [search, setSearch] = useState('');
  const deferredSearch = useDeferredValue(search);
  const [activeTab, setActiveTab] = useState<JobTabValue>('all');
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [isPending, setIsPending] = useState(true);
  const [busyJobId, setBusyJobId] = useState<string | null>(null);
  const [runningJobId, setRunningJobId] = useState<string | null>(null);

  const upsertJob = useCallback((updated: JobRecord) => {
    setJobs((current) => {
      const index = current.findIndex((job) => job.id === updated.id);
      if (index === -1) {
        return [updated, ...current];
      }
      const next = current.slice();
      next[index] = updated;
      return next;
    });
  }, []);

  const loadJobs = useCallback(async () => {
    setIsPending(true);
    try {
      setJobs(await fetchJobs());
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to load jobs',
      );
    } finally {
      setIsPending(false);
    }
  }, []);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  useEffect(() => {
    setIsHydrated(true);
  }, []);

  // Live status updates from the job run event stream.
  useJobEvents(upsertJob);

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

  const handleRun = useCallback(async (jobId: string) => {
    setRunningJobId(jobId);
    setBusyJobId(jobId);
    try {
      await runJobNow(jobId);
      toast.success('Job run queued.');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to run job');
    } finally {
      setRunningJobId((current) => (current === jobId ? null : current));
      setBusyJobId((current) => (current === jobId ? null : current));
    }
  }, []);

  const handleToggleEnabled = useCallback(
    async (job: JobRecord) => {
      setBusyJobId(job.id);
      try {
        const updated = await setJobEnabled(job.id, !job.enabled);
        upsertJob(updated);
        toast.success(updated.enabled ? 'Job resumed.' : 'Job paused.');
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : 'Failed to update job',
        );
      } finally {
        setBusyJobId((current) => (current === job.id ? null : current));
      }
    },
    [upsertJob],
  );

  const handleCancel = useCallback(
    async (jobId: string) => {
      setBusyJobId(jobId);
      try {
        const updated = await cancelJobRun(jobId);
        upsertJob(updated);
        toast.success('Run cancelled.');
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : 'Failed to cancel run',
        );
      } finally {
        setBusyJobId((current) => (current === jobId ? null : current));
      }
    },
    [upsertJob],
  );

  const handleDelete = useCallback(async (job: JobRecord) => {
    setBusyJobId(job.id);
    try {
      await deleteJob(job.id);
      setJobs((current) => current.filter((item) => item.id !== job.id));
      toast.success('Job deleted.');
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to delete job',
      );
    } finally {
      setBusyJobId((current) => (current === job.id ? null : current));
    }
  }, []);

  return (
    <TooltipProvider>
      <div className="space-y-5">
        <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-1">
            <h1 className="text-3xl font-semibold tracking-tight">Jobs</h1>
            <p className="max-w-3xl text-sm text-muted-foreground">
              Monitor background automations, review recent results, and manage
              scheduled work.
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
                <div className="relative w-full lg:max-w-xl">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Search jobs"
                    className="pl-9"
                  />
                </div>
                <div className="flex min-h-8 items-center gap-2 text-sm text-muted-foreground">
                  <Badge variant="secondary">
                    {visibleJobs.length} visible
                  </Badge>
                  <Badge variant="outline">{activeTabLabel}</Badge>
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
                        const busy = busyJobId === job.id;

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
                                  {getStatusLabel(status)}
                                </Badge>
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
                                {supportsTimeFields(job) && job.next_run_at ? (
                                  <div className="text-xs text-muted-foreground">
                                    Next{' '}
                                    {renderRelative(
                                      job.next_run_at,
                                      isHydrated,
                                      now,
                                    )}
                                  </div>
                                ) : null}
                              </div>
                            </TableCell>
                            <TableCell className="align-middle text-sm">
                              <div className="space-y-1">
                                <div>
                                  {job.last_run_status
                                    ? getStatusLabel(job.last_run_status)
                                    : 'No runs'}
                                </div>
                                <div className="text-xs text-muted-foreground">
                                  {renderRelative(
                                    job.last_run_at,
                                    isHydrated,
                                    now,
                                  )}
                                </div>
                              </div>
                            </TableCell>
                            <TableCell className="align-middle">
                              <JobRowActions
                                job={job}
                                busy={busy}
                                running={runningJobId === job.id}
                                onRun={() => void handleRun(job.id)}
                                onToggleEnabled={() =>
                                  void handleToggleEnabled(job)
                                }
                                onCancel={() => void handleCancel(job.id)}
                                onDelete={() => void handleDelete(job)}
                              />
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
                      : activeTab !== 'all'
                        ? `No jobs are currently in ${activeTabLabel.toLowerCase()}.`
                        : 'No automation jobs have been created yet.'}
                  </p>
                  {deferredSearch.trim() || activeTab !== 'all' ? (
                    <div className="mt-5 flex flex-wrap justify-center gap-2">
                      {deferredSearch.trim() ? (
                        <Button variant="outline" onClick={() => setSearch('')}>
                          Clear search
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
