'use client';

import { useCallback, useDeferredValue, useEffect, useMemo, useState } from 'react';
import {
  Activity,
  Bot,
  CalendarClock,
  Eye,
  Loader2,
  Plus,
  Play,
  RefreshCw,
  Search,
  Trash2,
  Waves,
} from 'lucide-react';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Textarea } from '@/components/ui/textarea';
import {
  type CreateJobPayload,
  type JobRecord,
  createJob,
  deleteJob,
  fetchJobs,
  runJobNow,
} from '@/lib/jobs-api';

type CreateJobFormState = {
  name: string;
  threadId: string;
  jobType: 'prompt' | 'analysis';
  triggerType: 'time' | 'event';
  prompt: string;
  analysisCode: string;
  intervalSeconds: string;
  runAt: string;
  thingId: string;
  eventName: string;
  subscriptionInput: string;
};

const INITIAL_CREATE_FORM: CreateJobFormState = {
  name: '',
  threadId: '',
  jobType: 'prompt',
  triggerType: 'time',
  prompt: '',
  analysisCode: '',
  intervalSeconds: '',
  runAt: '',
  thingId: '',
  eventName: '',
  subscriptionInput: '',
};

function getJobStatus(job: JobRecord, now: Date): string {
  if (!job.enabled) {
    return 'disabled';
  }
  if (job.trigger_type === 'event') {
    return 'waiting-event';
  }
  if (!job.next_run_at) {
    return 'queued';
  }

  const nextRunAt = new Date(job.next_run_at);
  if (Number.isNaN(nextRunAt.getTime()) || nextRunAt <= now) {
    return 'queued';
  }
  return 'scheduled';
}

function formatDateTime(value: string | null): string {
  if (!value) {
    return 'Not available';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

function getScheduleLabel(job: JobRecord): string {
  if (job.trigger_type === 'event') {
    return job.event_name ? `On event: ${job.event_name}` : 'On subscribed event';
  }
  if (job.interval_seconds) {
    return `Every ${job.interval_seconds}s`;
  }
  if (job.run_at) {
    return `Once at ${formatDateTime(job.run_at)}`;
  }
  return 'Manual or pending schedule';
}

function getPurposePreview(job: JobRecord): { label: string; content: string } {
  if (job.job_type === 'analysis') {
    return {
      label: 'Analysis code',
      content: job.analysis_code?.trim() || '(empty analysis code)',
    };
  }

  return {
    label: 'Prompt',
    content: job.prompt?.trim() || '(empty prompt)',
  };
}

function getSearchableText(job: JobRecord): string {
  return [
    job.name,
    job.id,
    job.thread_id,
    job.job_type,
    job.trigger_type,
    job.thing_id,
    job.event_name,
    job.last_error,
    job.last_response,
    job.last_fetch_value,
    job.prompt,
    job.analysis_code,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
}

function getStatusBadgeVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (status === 'queued') return 'default';
  if (status === 'waiting-event' || status === 'scheduled') return 'secondary';
  if (status === 'disabled') return 'outline';
  return 'outline';
}

function formatJson(value: unknown): string {
  if (value == null) {
    return 'Not available';
  }
  if (typeof value === 'string') {
    return value;
  }

  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function toCreatePayload(form: CreateJobFormState): CreateJobPayload {
  const payload: CreateJobPayload = {
    name: form.name.trim(),
    thread_id: form.threadId.trim(),
    job_type: form.jobType,
    trigger_type: form.jobType === 'analysis' ? 'time' : form.triggerType,
  };

  if (form.jobType === 'analysis') {
    payload.analysis_code = form.analysisCode.trim();
  } else {
    payload.prompt = form.prompt.trim();
  }

  if (payload.trigger_type === 'time') {
    if (form.intervalSeconds.trim()) {
      payload.interval_seconds = Number(form.intervalSeconds);
    }
    if (form.runAt.trim()) {
      payload.run_at = new Date(form.runAt).toISOString();
    }
  } else {
    payload.thing_id = form.thingId.trim();
    payload.event_name = form.eventName.trim();
    if (form.subscriptionInput.trim()) {
      payload.subscription_input = JSON.parse(form.subscriptionInput);
    }
  }

  return payload;
}

export function JobsList() {
  const [search, setSearch] = useState('');
  const deferredSearch = useDeferredValue(search);
  const [threadFilter, setThreadFilter] = useState('');
  const deferredThreadFilter = useDeferredValue(threadFilter);
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [isPending, setIsPending] = useState(true);
  const [runningJobId, setRunningJobId] = useState<string | null>(null);
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null);
  const [selectedJob, setSelectedJob] = useState<JobRecord | null>(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [isCreatingJob, setIsCreatingJob] = useState(false);
  const [createForm, setCreateForm] = useState<CreateJobFormState>(
    INITIAL_CREATE_FORM,
  );

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
    setSelectedJob((current) => {
      if (!current) {
        return current;
      }
      return jobs.find((job) => job.id === current.id) ?? null;
    });
  }, [jobs]);

  const visibleJobs = useMemo(() => {
    const query = deferredSearch.trim().toLowerCase();
    if (!query) {
      return jobs;
    }

    return jobs.filter((job) => getSearchableText(job).includes(query));
  }, [deferredSearch, jobs]);

  const stats = useMemo(() => {
    const now = new Date();
    return visibleJobs.reduce(
      (acc, job) => {
        const status = getJobStatus(job, now);
        acc.total += 1;
        if (status === 'queued') acc.queued += 1;
        if (status === 'scheduled') acc.scheduled += 1;
        if (status === 'waiting-event') acc.waitingEvent += 1;
        if (status === 'disabled') acc.disabled += 1;
        return acc;
      },
      { total: 0, queued: 0, scheduled: 0, waitingEvent: 0, disabled: 0 },
    );
  }, [visibleJobs]);

  const handleRun = useCallback(
    async (jobId: string) => {
      setRunningJobId(jobId);
      try {
        await runJobNow(jobId);
        toast.success('Job run started.');
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
      if (!window.confirm(`Delete job "${job.name}"?`)) {
        return;
      }

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

  const handleCreateJob = useCallback(async () => {
    setIsCreatingJob(true);
    try {
      const payload = toCreatePayload(createForm);
      await createJob(payload);
      toast.success('Job created.');
      setCreateDialogOpen(false);
      setCreateForm(INITIAL_CREATE_FORM);
      await loadJobs();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to create job',
      );
    } finally {
      setIsCreatingJob(false);
    }
  }, [createForm, loadJobs]);

  const purposeLabel = selectedJob ? getPurposePreview(selectedJob) : null;

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-3">
          <div className="inline-flex items-center gap-2 rounded-full border bg-card/80 px-3 py-1 text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
            <Waves className="h-3.5 w-3.5" />
            Automation Monitor
          </div>
          <div className="space-y-1">
            <h1 className="text-3xl font-semibold tracking-tight">Jobs</h1>
            <p className="max-w-3xl text-sm text-muted-foreground">
              Review scheduled and event-driven jobs, inspect their prompts or analysis code,
              and trigger or remove them without leaving the copilot workspace.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={() => setCreateDialogOpen(true)}>
            <Plus className="h-4 w-4" />
            Create job
          </Button>
          <Button variant="outline" onClick={() => void loadJobs()} disabled={isPending}>
            <RefreshCw className={isPending ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
            Refresh
          </Button>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Card className="border-primary/20 bg-gradient-to-br from-primary/10 via-card to-card">
          <CardHeader className="pb-2">
            <CardDescription>Visible jobs</CardDescription>
            <CardTitle className="text-3xl">{stats.total}</CardTitle>
          </CardHeader>
          <CardContent className="flex items-center gap-2 text-sm text-muted-foreground">
            <Bot className="h-4 w-4" />
            Filtered by the current search query
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Queued now</CardDescription>
            <CardTitle className="text-3xl">{stats.queued}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Jobs ready to execute on the next polling cycle.
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Scheduled</CardDescription>
            <CardTitle className="text-3xl">{stats.scheduled}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Time-based jobs with a future next-run timestamp.
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Event-driven</CardDescription>
            <CardTitle className="text-3xl">{stats.waitingEvent}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Listening for subscribed WoT events before they fire.
          </CardContent>
        </Card>
      </section>

      <Card className="overflow-hidden">
        <CardContent className="space-y-4 p-6">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
            <div className="flex w-full max-w-4xl flex-col gap-3 xl:flex-row">
              <div className="relative w-full max-w-xl">
                <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search by name, thread, thing id, event, error, prompt, or result..."
                  className="pl-11"
                />
              </div>
              <Input
                value={threadFilter}
                onChange={(event) => setThreadFilter(event.target.value)}
                placeholder="Filter backend query by exact thread id"
                className="w-full xl:max-w-xs"
              />
            </div>
            <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              <Badge variant="secondary" className="font-medium">
                Manual refresh
              </Badge>
              {deferredThreadFilter.trim() ? (
                <Badge variant="outline" className="font-medium">
                  Thread {deferredThreadFilter.trim()}
                </Badge>
              ) : null}
              {stats.disabled > 0 ? (
                <Badge variant="outline" className="font-medium">
                  {stats.disabled} disabled
                </Badge>
              ) : null}
            </div>
          </div>

          {isPending ? (
            <div className="flex min-h-48 items-center justify-center rounded-md border">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
            </div>
          ) : visibleJobs.length > 0 ? (
            <div className="rounded-md border">
              <Table className="min-w-[1180px]">
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[22%]">Job</TableHead>
                    <TableHead className="w-[11%]">Status</TableHead>
                    <TableHead className="w-[16%]">Schedule</TableHead>
                    <TableHead className="w-[13%]">Target</TableHead>
                    <TableHead className="w-[11%]">Activity</TableHead>
                    <TableHead className="w-[12%]">Last result</TableHead>
                    <TableHead className="w-[18%] text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visibleJobs.map((job) => {
                    const status = getJobStatus(job, new Date());
                    const purpose = getPurposePreview(job);

                    return (
                      <TableRow key={job.id}>
                        <TableCell className="align-top">
                          <div className="space-y-2">
                            <div className="space-y-1">
                              <div className="font-medium">{job.name}</div>
                              <div className="font-mono text-xs text-muted-foreground">
                                {job.id}
                              </div>
                            </div>
                            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                              <Badge variant="outline">{job.job_type}</Badge>
                              <Badge variant="outline">thread {job.thread_id}</Badge>
                            </div>
                            <details className="rounded-lg border bg-muted/25 px-3 py-2">
                              <summary className="cursor-pointer text-sm font-medium">
                                {purpose.label}
                              </summary>
                              <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words text-xs text-muted-foreground">
                                {purpose.content}
                              </pre>
                            </details>
                          </div>
                        </TableCell>
                        <TableCell className="align-top">
                          <div className="space-y-2">
                            <Badge variant={getStatusBadgeVariant(status)}>
                              {status}
                            </Badge>
                            {job.last_error ? (
                              <p className="line-clamp-3 text-xs text-destructive">
                                {job.last_error}
                              </p>
                            ) : (
                              <p className="text-xs text-muted-foreground">
                                No recent error
                              </p>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="align-top text-sm text-muted-foreground">
                          <div className="space-y-2">
                            <div className="flex items-start gap-2">
                              <CalendarClock className="mt-0.5 h-4 w-4 text-primary" />
                              <div>
                                <div>{getScheduleLabel(job)}</div>
                                <div className="text-xs">Next: {formatDateTime(job.next_run_at)}</div>
                              </div>
                            </div>
                          </div>
                        </TableCell>
                        <TableCell className="align-top text-sm text-muted-foreground">
                          <div className="space-y-1">
                            <div>{job.thing_id || 'No thing binding'}</div>
                            <div className="text-xs">
                              {job.event_name || job.trigger_type === 'event'
                                ? job.event_name || 'Subscribed event'
                                : 'Time-based trigger'}
                            </div>
                          </div>
                        </TableCell>
                        <TableCell className="align-top text-sm text-muted-foreground">
                          <div className="space-y-2">
                            <div className="flex items-center gap-2">
                              <Activity className="h-4 w-4 text-primary" />
                              <span>{job.run_count} runs</span>
                            </div>
                            <div className="text-xs">Last run: {formatDateTime(job.last_run_at)}</div>
                            <div className="line-clamp-2 text-xs">
                              Last fetch: {job.last_fetch_value || 'No fetched value yet'}
                            </div>
                          </div>
                        </TableCell>
                        <TableCell className="align-top text-sm text-muted-foreground">
                          <p className="line-clamp-5 whitespace-pre-wrap break-words">
                            {job.last_response || 'No result captured yet.'}
                          </p>
                        </TableCell>
                        <TableCell className="align-top">
                          <div className="flex justify-end gap-2">
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={runningJobId === job.id || deletingJobId === job.id}
                              onClick={() => setSelectedJob(job)}
                            >
                              <Eye className="h-3.5 w-3.5" />
                              Details
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={runningJobId === job.id || deletingJobId === job.id}
                              onClick={() => void handleRun(job.id)}
                            >
                              {runningJobId === job.id ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <Play className="h-3.5 w-3.5" />
                              )}
                              Run now
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={deletingJobId === job.id || runningJobId === job.id}
                              onClick={() => void handleDelete(job)}
                            >
                              {deletingJobId === job.id ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <Trash2 className="h-3.5 w-3.5" />
                              )}
                              Delete
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          ) : (
            <div className="rounded-lg border border-dashed px-6 py-12 text-center">
              <h2 className="text-2xl font-semibold tracking-tight">No jobs found</h2>
              <p className="mx-auto mt-2 max-w-md text-base text-muted-foreground">
                {deferredSearch.trim()
                  ? `No jobs match "${deferredSearch.trim()}". Try another search or clear the filter.`
                  : deferredThreadFilter.trim()
                    ? `No jobs were found for thread "${deferredThreadFilter.trim()}".`
                    : 'The job runner has not created any jobs yet.'}
              </p>
              {deferredSearch.trim() || deferredThreadFilter.trim() ? (
                <div className="mt-6 flex justify-center gap-3">
                  <Button variant="outline" onClick={() => setSearch('')}>
                    Clear search
                  </Button>
                  <Button variant="outline" onClick={() => setThreadFilter('')}>
                    Clear thread filter
                  </Button>
                </div>
              ) : null}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent className="max-w-3xl p-0">
          <DialogHeader className="px-6 pt-6">
            <DialogTitle>Create Job</DialogTitle>
            <DialogDescription>
              Create a prompt or analysis job and attach either a time schedule or a WoT event trigger.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 px-6 pb-6 sm:grid-cols-2">
            <div className="space-y-2 sm:col-span-1">
              <label className="text-sm font-medium">Name</label>
              <Input
                value={createForm.name}
                onChange={(event) =>
                  setCreateForm((current) => ({ ...current, name: event.target.value }))
                }
                placeholder="Morning energy summary"
              />
            </div>
            <div className="space-y-2 sm:col-span-1">
              <label className="text-sm font-medium">Thread ID</label>
              <Input
                value={createForm.threadId}
                onChange={(event) =>
                  setCreateForm((current) => ({ ...current, threadId: event.target.value }))
                }
                placeholder="chat-thread-123"
              />
            </div>

            <div className="space-y-2 sm:col-span-1">
              <label className="text-sm font-medium">Job type</label>
              <Select
                value={createForm.jobType}
                onValueChange={(value: 'prompt' | 'analysis') =>
                  setCreateForm((current) => ({
                    ...current,
                    jobType: value,
                    triggerType: value === 'analysis' ? 'time' : current.triggerType,
                  }))
                }
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="prompt">Prompt</SelectItem>
                  <SelectItem value="analysis">Analysis</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2 sm:col-span-1">
              <label className="text-sm font-medium">Trigger type</label>
              <Select
                value={createForm.jobType === 'analysis' ? 'time' : createForm.triggerType}
                onValueChange={(value: 'time' | 'event') =>
                  setCreateForm((current) => ({ ...current, triggerType: value }))
                }
                disabled={createForm.jobType === 'analysis'}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="time">Time</SelectItem>
                  <SelectItem value="event">Event</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {createForm.jobType === 'analysis' ? (
              <div className="space-y-2 sm:col-span-2">
                <label className="text-sm font-medium">Analysis code</label>
                <Textarea
                  rows={10}
                  value={createForm.analysisCode}
                  onChange={(event) =>
                    setCreateForm((current) => ({
                      ...current,
                      analysisCode: event.target.value,
                    }))
                  }
                  placeholder="return {'summary': '...', 'score': 0.8}"
                />
              </div>
            ) : (
              <div className="space-y-2 sm:col-span-2">
                <label className="text-sm font-medium">Prompt</label>
                <Textarea
                  rows={8}
                  value={createForm.prompt}
                  onChange={(event) =>
                    setCreateForm((current) => ({ ...current, prompt: event.target.value }))
                  }
                  placeholder="Summarize the latest occupancy and temperature changes."
                />
              </div>
            )}

            {(createForm.jobType === 'analysis' || createForm.triggerType === 'time') ? (
              <>
                <div className="space-y-2 sm:col-span-1">
                  <label className="text-sm font-medium">Interval seconds</label>
                  <Input
                    type="number"
                    min="1"
                    value={createForm.intervalSeconds}
                    onChange={(event) =>
                      setCreateForm((current) => ({
                        ...current,
                        intervalSeconds: event.target.value,
                      }))
                    }
                    placeholder="300"
                  />
                </div>
                <div className="space-y-2 sm:col-span-1">
                  <label className="text-sm font-medium">Run once at</label>
                  <Input
                    type="datetime-local"
                    value={createForm.runAt}
                    onChange={(event) =>
                      setCreateForm((current) => ({ ...current, runAt: event.target.value }))
                    }
                  />
                </div>
              </>
            ) : (
              <>
                <div className="space-y-2 sm:col-span-1">
                  <label className="text-sm font-medium">Thing ID</label>
                  <Input
                    value={createForm.thingId}
                    onChange={(event) =>
                      setCreateForm((current) => ({ ...current, thingId: event.target.value }))
                    }
                    placeholder="urn:dev:ops:thermostat-1"
                  />
                </div>
                <div className="space-y-2 sm:col-span-1">
                  <label className="text-sm font-medium">Event name</label>
                  <Input
                    value={createForm.eventName}
                    onChange={(event) =>
                      setCreateForm((current) => ({ ...current, eventName: event.target.value }))
                    }
                    placeholder="overheat"
                  />
                </div>
                <div className="space-y-2 sm:col-span-2">
                  <label className="text-sm font-medium">Subscription input JSON</label>
                  <Textarea
                    rows={5}
                    value={createForm.subscriptionInput}
                    onChange={(event) =>
                      setCreateForm((current) => ({
                        ...current,
                        subscriptionInput: event.target.value,
                      }))
                    }
                    placeholder='{"threshold": 30}'
                  />
                </div>
              </>
            )}
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setCreateDialogOpen(false)}
              disabled={isCreatingJob}
            >
              Cancel
            </Button>
            <Button onClick={() => void handleCreateJob()} disabled={isCreatingJob}>
              {isCreatingJob ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              Create job
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Sheet open={selectedJob !== null} onOpenChange={(open) => (!open ? setSelectedJob(null) : null)}>
        <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-2xl">
          {selectedJob ? (
            <>
              <SheetHeader className="border-b">
                <SheetTitle>{selectedJob.name}</SheetTitle>
                <SheetDescription>
                  Full execution detail for {selectedJob.id}
                </SheetDescription>
              </SheetHeader>

              <div className="grid gap-6 p-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <Card>
                    <CardHeader className="pb-2">
                      <CardDescription>Identity</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-2 text-sm">
                      <div><span className="font-medium">Thread:</span> {selectedJob.thread_id}</div>
                      <div><span className="font-medium">Job type:</span> {selectedJob.job_type}</div>
                      <div><span className="font-medium">Trigger:</span> {selectedJob.trigger_type}</div>
                      <div><span className="font-medium">Status:</span> {getJobStatus(selectedJob, new Date())}</div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader className="pb-2">
                      <CardDescription>Timing</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-2 text-sm">
                      <div><span className="font-medium">Schedule:</span> {getScheduleLabel(selectedJob)}</div>
                      <div><span className="font-medium">Next run:</span> {formatDateTime(selectedJob.next_run_at)}</div>
                      <div><span className="font-medium">Last run:</span> {formatDateTime(selectedJob.last_run_at)}</div>
                      <div><span className="font-medium">Created:</span> {formatDateTime(selectedJob.created_at)}</div>
                    </CardContent>
                  </Card>
                </div>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">Purpose</CardTitle>
                    <CardDescription>{purposeLabel?.label}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-lg border bg-muted/30 p-4 text-xs text-muted-foreground">
                      {purposeLabel?.content}
                    </pre>
                  </CardContent>
                </Card>

                <div className="grid gap-4 md:grid-cols-2">
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">Target</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2 text-sm">
                      <div><span className="font-medium">Thing ID:</span> {selectedJob.thing_id || 'Not set'}</div>
                      <div><span className="font-medium">Event name:</span> {selectedJob.event_name || 'Not set'}</div>
                      <div><span className="font-medium">Subscription ID:</span> {selectedJob.subscription_id || 'Not set'}</div>
                      <div><span className="font-medium">Run count:</span> {selectedJob.run_count}</div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">Diagnostics</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2 text-sm">
                      <div><span className="font-medium">Last fetch value:</span> {selectedJob.last_fetch_value || 'Not captured'}</div>
                      <div><span className="font-medium">Last error:</span> {selectedJob.last_error || 'No recent error'}</div>
                      <div><span className="font-medium">Updated:</span> {formatDateTime(selectedJob.updated_at)}</div>
                    </CardContent>
                  </Card>
                </div>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">Last Result</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-lg border bg-muted/30 p-4 text-xs text-muted-foreground">
                      {selectedJob.last_response || 'No result captured yet.'}
                    </pre>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">Subscription Input</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-lg border bg-muted/30 p-4 text-xs text-muted-foreground">
                      {formatJson(selectedJob.subscription_input)}
                    </pre>
                  </CardContent>
                </Card>
              </div>
            </>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}