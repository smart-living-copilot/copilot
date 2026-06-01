'use client';

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Loader2, MessagesSquare, Play, RefreshCw, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { RunCodeArtifactCard } from '@/components/copilot/chat-tool-call-cards';
import {
  formatArtifactSummary,
  normalizeRunCodeResult,
  type RunCodeResult,
} from '@/components/copilot/chat-tool-call-model';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  formatDateTime,
  getJobStatus,
  getPurposePreview,
  getScheduleLabel,
  getStatusBadgeVariant,
  supportsEventFields,
  supportsJobThread,
  supportsTimeFields,
} from '@/lib/job-formatters';
import {
  type JobRecord,
  type JobRunRecord,
  deleteJob,
  fetchJob,
  fetchJobRuns,
  runJobNow,
} from '@/lib/jobs-api';

interface JobDetailsPageProps {
  jobId: string;
}

const JOB_TABS_TRIGGER_CLASSNAME =
  'flex-none rounded-none border-b-2 border-transparent px-4 py-2.5 font-medium text-muted-foreground data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none data-active:border-primary data-active:bg-transparent data-active:text-foreground data-active:shadow-none';

function formatJson(value: unknown): string {
  if (value == null) return 'Not available';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function runOutcome(run: JobRunRecord): string {
  const codeResult = normalizeJobCodeResult(run.result);
  const artifactSummary = codeResult.artifacts?.length
    ? formatArtifactSummary(codeResult.artifacts)
    : '';
  if (artifactSummary && codeResult.stdout?.trim()) {
    return `${artifactSummary} • text output`;
  }
  if (artifactSummary) return artifactSummary;
  if (codeResult.stdout?.trim()) return codeResult.stdout.trim();
  if (codeResult.error?.trim()) return codeResult.error.trim();
  if (run.error?.trim()) return run.error.trim();
  if (run.response_text?.trim()) return run.response_text.trim();
  if (run.result != null) return formatJson(run.result);
  return 'No output captured.';
}

function hasCodeOutput(result: RunCodeResult): boolean {
  return Boolean(
    result.error?.trim() ||
    result.stdout?.trim() ||
    (result.artifacts?.length ?? 0) > 0,
  );
}

function normalizeJobCodeResult(value: unknown): RunCodeResult {
  const direct = normalizeRunCodeResult(value);
  if (hasCodeOutput(direct)) {
    return direct;
  }

  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return direct;
  }

  return normalizeRunCodeResult((value as { response?: unknown }).response);
}

function FieldCard({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
}) {
  return (
    <Card
      size="sm"
      className="rounded-md border-border/70 shadow-sm shadow-black/5"
    >
      <CardContent>
        <div className="text-xs text-muted-foreground">{label}</div>
        <div
          className={
            mono
              ? 'mt-1 break-all font-mono text-xs leading-5 text-foreground'
              : 'mt-1 truncate text-sm font-medium text-foreground'
          }
        >
          {value}
        </div>
      </CardContent>
    </Card>
  );
}

function TextPanel({
  title,
  description,
  value,
  compact = false,
}: {
  title: string;
  description?: string;
  value: string;
  compact?: boolean;
}) {
  return (
    <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
      <CardHeader className="border-b border-border/70">
        <CardTitle className="text-base">{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent>
        <pre
          className={
            compact
              ? 'max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs leading-5 text-muted-foreground'
              : 'max-h-[32rem] overflow-auto whitespace-pre-wrap break-words text-sm leading-6 text-muted-foreground'
          }
        >
          {value}
        </pre>
      </CardContent>
    </Card>
  );
}

function RunStatusBadge({ status }: { status: string }) {
  return <Badge variant={getStatusBadgeVariant(status)}>{status}</Badge>;
}

function RunHistoryCard({ runs }: { runs: JobRunRecord[] }) {
  return (
    <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
      <CardHeader className="border-b border-border/70">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle className="text-base">Run history</CardTitle>
            <CardDescription>
              Recent starts, completion times, and captured outcomes.
            </CardDescription>
          </div>
          <Badge variant="outline">{runs.length}</Badge>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {runs.length ? (
          <div className="overflow-x-auto">
            <Table className="min-w-[860px]">
              <TableHeader>
                <TableRow>
                  <TableHead>Status</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Finished</TableHead>
                  <TableHead>Outcome</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((run) => (
                  <TableRow key={run.id}>
                    <TableCell className="align-top">
                      <RunStatusBadge status={run.status} />
                    </TableCell>
                    <TableCell className="align-top">{run.source}</TableCell>
                    <TableCell className="align-top text-xs text-muted-foreground">
                      {formatDateTime(run.started_at)}
                    </TableCell>
                    <TableCell className="align-top text-xs text-muted-foreground">
                      {formatDateTime(run.finished_at)}
                    </TableCell>
                    <TableCell className="align-top text-sm text-muted-foreground">
                      <p className="line-clamp-3 whitespace-pre-wrap break-words">
                        {runOutcome(run)}
                      </p>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : (
          <div className="p-4 text-sm text-muted-foreground">
            No runs recorded yet.
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function AnalysisOutputPanel({
  result,
  title = 'Analysis output',
}: {
  result: RunCodeResult;
  title?: string;
}) {
  const artifactSummary = result.artifacts?.length
    ? formatArtifactSummary(result.artifacts)
    : '';
  const hasStdout = !!result.stdout?.trim();
  const hasError = !!result.error?.trim();

  if (!artifactSummary && !hasStdout && !hasError) {
    return (
      <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
        <CardHeader className="border-b border-border/70">
          <CardTitle className="text-base">{title}</CardTitle>
          <CardDescription>No visible output captured yet.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
      <CardHeader className="border-b border-border/70">
        <CardTitle className="text-base">{title}</CardTitle>
        <CardDescription>
          {artifactSummary || 'Text output from the latest analysis run.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {hasError ? (
          <Alert variant="destructive">
            <AlertTitle>Execution failed</AlertTitle>
            <AlertDescription>
              <pre className="overflow-auto whitespace-pre-wrap text-xs leading-5">
                {result.error}
              </pre>
            </AlertDescription>
          </Alert>
        ) : null}

        {result.artifacts?.length ? (
          <div className="space-y-2">
            {result.artifacts.map((artifact) => (
              <RunCodeArtifactCard
                key={`${artifact.kind}:${artifact.filename}`}
                artifact={artifact}
              />
            ))}
          </div>
        ) : null}

        {hasStdout ? (
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-md border bg-muted/20 p-3 text-sm leading-6 text-muted-foreground">
            {result.stdout}
          </pre>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function JobDetailsPage({ jobId }: JobDetailsPageProps) {
  const router = useRouter();
  const [job, setJob] = useState<JobRecord | null>(null);
  const [runs, setRuns] = useState<JobRunRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRunning, setIsRunning] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const [jobRecord, runRecords] = await Promise.all([
        fetchJob(jobId),
        fetchJobRuns(jobId),
      ]);
      setJob(jobRecord);
      setRuns(runRecords);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Failed to load job';
      setLoadError(message);
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    void load();
  }, [load]);

  const status = useMemo(
    () => (job ? getJobStatus(job, new Date()) : null),
    [job],
  );
  const purpose = job
    ? getPurposePreview(job)
    : { label: 'Prompt', content: '(empty prompt)' };
  const hasJobThread = job ? supportsJobThread(job) : false;
  const hasTimeFields = job ? supportsTimeFields(job) : false;
  const hasEventFields = job ? supportsEventFields(job) : false;
  const latestAnalysisResult = useMemo(() => {
    if (job?.action_kind !== 'analysis') {
      return null;
    }
    const latestRun = runs.find((run) =>
      hasCodeOutput(normalizeJobCodeResult(run.result)),
    );
    return latestRun ? normalizeJobCodeResult(latestRun.result) : null;
  }, [job?.action_kind, runs]);

  const handleRun = useCallback(async () => {
    setIsRunning(true);
    try {
      await runJobNow(jobId);
      toast.success('Job run queued.');
      await load();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to run job');
    } finally {
      setIsRunning(false);
    }
  }, [jobId, load]);

  const handleDelete = useCallback(async () => {
    if (!job || !window.confirm(`Delete job "${job.name}"?`)) return;

    setIsDeleting(true);
    try {
      await deleteJob(job.id);
      toast.success('Job deleted.');
      router.push('/jobs');
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to delete job',
      );
      setIsDeleting(false);
    }
  }, [job, router]);

  return (
    <div className="space-y-5">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-2">
          <div className="space-y-1">
            <h1 className="text-3xl font-semibold tracking-tight">
              {job?.name || 'Job details'}
            </h1>
            <p className="break-all font-mono text-xs text-muted-foreground">
              {jobId}
            </p>
          </div>
          {job ? (
            <div className="flex flex-wrap items-center gap-2">
              {status ? (
                <Badge variant={getStatusBadgeVariant(status)}>{status}</Badge>
              ) : null}
              <Badge variant="outline">{job.action_kind}</Badge>
              <Badge variant="outline">{getScheduleLabel(job)}</Badge>
            </div>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            onClick={() => void load()}
            disabled={isLoading || isRunning || isDeleting}
          >
            <RefreshCw
              className={isLoading ? 'h-4 w-4 animate-spin' : 'h-4 w-4'}
            />
            Refresh
          </Button>
          {hasJobThread ? (
            <Button variant="outline" asChild>
              <Link href={`/jobs/${jobId}/thread`}>
                <MessagesSquare className="h-4 w-4" />
                Thread
              </Link>
            </Button>
          ) : null}
          <Button
            onClick={() => void handleRun()}
            disabled={!job || isLoading || isRunning || isDeleting}
          >
            {isRunning ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            Run
          </Button>
          <Button
            variant="destructive"
            onClick={() => void handleDelete()}
            disabled={!job || isLoading || isRunning || isDeleting}
          >
            {isDeleting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
            Delete
          </Button>
        </div>
      </section>

      {isLoading && !job ? (
        <Card className="rounded-md border-border/70">
          <CardContent className="flex min-h-56 items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
          </CardContent>
        </Card>
      ) : null}

      {loadError && !job ? (
        <Alert variant="destructive">
          <AlertTitle>Unable to load job</AlertTitle>
          <AlertDescription>{loadError}</AlertDescription>
        </Alert>
      ) : null}

      {job ? (
        <>
          {hasJobThread && job.waiting_question ? (
            <Alert>
              <AlertTitle>Waiting for input</AlertTitle>
              <AlertDescription>{job.waiting_question}</AlertDescription>
            </Alert>
          ) : null}

          {job.last_error ? (
            <Alert variant="destructive">
              <AlertTitle>Last error</AlertTitle>
              <AlertDescription>{job.last_error}</AlertDescription>
            </Alert>
          ) : null}

          <Tabs defaultValue="overview" className="space-y-5">
            <div className="overflow-x-auto">
              <TabsList
                variant="line"
                className="h-auto min-w-max gap-0 rounded-none border-b border-border/80 bg-transparent p-0"
              >
                <TabsTrigger
                  value="overview"
                  className={JOB_TABS_TRIGGER_CLASSNAME}
                >
                  Overview
                </TabsTrigger>
                <TabsTrigger
                  value="runs"
                  className={JOB_TABS_TRIGGER_CLASSNAME}
                >
                  Runs ({runs.length})
                </TabsTrigger>
                <TabsTrigger
                  value="definition"
                  className={JOB_TABS_TRIGGER_CLASSNAME}
                >
                  {job.action_kind === 'analysis' ? 'Code' : 'Prompt'}
                </TabsTrigger>
                <TabsTrigger
                  value="configuration"
                  className={JOB_TABS_TRIGGER_CLASSNAME}
                >
                  Configuration
                </TabsTrigger>
              </TabsList>
            </div>

            <TabsContent value="overview" className="mt-0 space-y-4">
              <section className="grid gap-2 sm:grid-cols-2 xl:grid-cols-6">
                <FieldCard
                  label="Status"
                  value={
                    status ? (
                      <Badge variant={getStatusBadgeVariant(status)}>
                        {status}
                      </Badge>
                    ) : (
                      'unknown'
                    )
                  }
                />
                <FieldCard label="Action" value={job.action_kind} />
                <FieldCard label="Trigger" value={job.trigger_kind} />
                {hasTimeFields ? (
                  <>
                    <FieldCard label="Schedule" value={getScheduleLabel(job)} />
                    <FieldCard
                      label="Next run"
                      value={formatDateTime(job.next_run_at)}
                    />
                  </>
                ) : null}
                {hasEventFields ? (
                  <>
                    <FieldCard
                      label="Thing"
                      value={job.thing_id || 'Unbound'}
                      mono
                    />
                    <FieldCard
                      label="Event"
                      value={job.event_name || 'Unbound'}
                    />
                  </>
                ) : null}
                <FieldCard
                  label="Last run"
                  value={job.last_run_status || 'No runs'}
                />
              </section>

              {job.action_kind === 'analysis' ? (
                <AnalysisOutputPanel
                  result={latestAnalysisResult ?? {}}
                  title="Latest output"
                />
              ) : (
                <TextPanel
                  title="Last result"
                  description="The latest response captured from an execution."
                  value={job.last_response || 'No result captured yet.'}
                />
              )}
            </TabsContent>

            <TabsContent value="runs" className="mt-0">
              <RunHistoryCard runs={runs} />
            </TabsContent>

            <TabsContent value="definition" className="mt-0">
              <TextPanel
                title={purpose.label}
                description="The action payload used when this job runs."
                value={purpose.content}
              />
            </TabsContent>

            <TabsContent value="configuration" className="mt-0 space-y-4">
              <section className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                {hasJobThread ? (
                  <FieldCard
                    label="Job thread"
                    value={job.job_thread_id}
                    mono
                  />
                ) : null}
                {hasTimeFields ? (
                  <>
                    <FieldCard
                      label="Schedule kind"
                      value={job.schedule_kind || 'Time trigger'}
                    />
                    {job.interval_seconds ? (
                      <FieldCard
                        label="Interval"
                        value={`${job.interval_seconds}s`}
                      />
                    ) : null}
                    {job.run_at ? (
                      <FieldCard
                        label="Run once at"
                        value={formatDateTime(job.run_at)}
                      />
                    ) : null}
                  </>
                ) : null}
                {hasEventFields ? (
                  <>
                    <FieldCard
                      label="Thing"
                      value={job.thing_id || 'Unbound'}
                      mono
                    />
                    <FieldCard
                      label="Event"
                      value={job.event_name || 'Unbound'}
                    />
                    {job.subscription_id ? (
                      <FieldCard
                        label="Subscription"
                        value={job.subscription_id}
                        mono
                      />
                    ) : null}
                  </>
                ) : null}
                <FieldCard
                  label="Active run"
                  value={job.active_run_id || 'None'}
                  mono
                />
                <FieldCard label="Run count" value={job.run_count} />
                <FieldCard
                  label="Last run at"
                  value={formatDateTime(job.last_run_at)}
                />
                <FieldCard
                  label="Updated"
                  value={formatDateTime(job.updated_at)}
                />
              </section>

              {hasEventFields ? (
                <TextPanel
                  title="Subscription input"
                  description="Stored event subscription payload for event-triggered jobs."
                  value={formatJson(job.subscription_input)}
                  compact
                />
              ) : null}
            </TabsContent>
          </Tabs>
        </>
      ) : null}
    </div>
  );
}
