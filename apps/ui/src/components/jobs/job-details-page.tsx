'use client';

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  Ban,
  Loader2,
  MessagesSquare,
  Pause,
  Pencil,
  Play,
  Power,
  RefreshCw,
  Send,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';

import { ConfirmDialog } from '@/components/jobs/confirm-dialog';
import { JobRunHistoryCard } from '@/components/jobs/job-run-history';
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import {
  formatDateTime,
  getSubmittedRecordResultSummary,
  getJobStatus,
  getPurposePreview,
  getScheduleLabel,
  getStatusBadgeVariant,
  getStatusLabel,
  supportsJobReply,
  supportsEventFields,
  supportsJobThread,
  supportsTimeFields,
} from '@/lib/job-formatters';
import { useJobEvents } from '@/hooks/use-job-events';
import {
  type JobRecord,
  type JobRunRecord,
  cancelJobRun,
  createClientReplyId,
  deleteJob,
  fetchJob,
  fetchJobRuns,
  replyToJob,
  runJobNow,
  setJobEnabled,
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
  const submittedRecordSummary = getSubmittedRecordResultSummary(run.result);
  if (submittedRecordSummary) return submittedRecordSummary;
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

function resourceHealthLabel(status: string | undefined): string {
  if (status === 'healthy') return 'Healthy';
  if (status === 'degraded') return 'Degraded';
  return 'Unknown';
}

function resourceHealthBadgeVariant(status: string | undefined) {
  if (status === 'degraded') return 'destructive';
  if (status === 'healthy') return 'secondary';
  return 'outline';
}

function resourceNameLabel(name: string): string {
  if (name === 'event_subscription') return 'Event subscription';
  if (name === 'virtual_record_thing') return 'Virtual record Thing';
  if (name === 'schedule') return 'Schedule';
  return name.replaceAll('_', ' ');
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
      className="rounded-md border-border/70 shadow-sm shadow-black/5 xl:min-w-0 xl:flex-1 xl:basis-0"
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

function CodeOutputPanel({
  result,
  title = 'Code output',
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

function JobReplyPanel({
  question,
  value,
  isSubmitting,
  transcriptHref,
  onChange,
  onSubmit,
}: {
  question: string;
  value: string;
  isSubmitting: boolean;
  transcriptHref: string;
  onChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const canSubmit = value.trim().length > 0 && !isSubmitting;

  return (
    <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
      <CardHeader className="border-b border-border/70">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1">
            <CardTitle className="text-base">Waiting for input</CardTitle>
            <CardDescription>
              Reply to the pending job question.
            </CardDescription>
          </div>
          <Badge variant="secondary">Needs input</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-md border bg-muted/20 p-4">
          <div className="text-xs font-medium text-muted-foreground">
            Question
          </div>
          <p className="mt-2 whitespace-pre-wrap break-words text-base leading-7 text-foreground">
            {question}
          </p>
        </div>
        <form className="space-y-3" onSubmit={onSubmit}>
          <Textarea
            aria-label="Job answer"
            className="min-h-28 resize-y"
            placeholder="Answer..."
            value={value}
            onChange={(event) => onChange(event.target.value)}
            disabled={isSubmitting}
          />
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button variant="outline" asChild>
              <Link href={transcriptHref}>
                <MessagesSquare className="h-4 w-4" />
                View transcript
              </Link>
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {isSubmitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
              Submit answer
            </Button>
          </div>
        </form>
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
  const [isReplying, setIsReplying] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [replyText, setReplyText] = useState('');
  const [loadError, setLoadError] = useState<string | null>(null);
  const pendingReplyRef = useRef<{
    message: string;
    clientReplyId: string;
  } | null>(null);

  const load = useCallback(
    async ({ silent = false }: { silent?: boolean } = {}) => {
      if (!silent) {
        setIsLoading(true);
      }
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
        if (!silent) {
          toast.error(message);
        }
      } finally {
        if (!silent) {
          setIsLoading(false);
        }
      }
    },
    [jobId],
  );

  useEffect(() => {
    void load();
  }, [load]);

  // Live refresh when this job emits a run event.
  useJobEvents(
    useCallback(
      (incoming: JobRecord) => {
        if (incoming.id === jobId) {
          void load({ silent: true });
        }
      },
      [jobId, load],
    ),
  );

  const status = useMemo(
    () => (job ? getJobStatus(job, new Date()) : null),
    [job],
  );
  const purpose = job
    ? getPurposePreview(job)
    : { label: 'Prompt', content: '(empty prompt)' };
  const hasJobThread = job ? supportsJobThread(job) : false;
  const isWaitingForReply = job ? supportsJobReply(job) : false;
  const hasTimeFields = job ? supportsTimeFields(job) : false;
  const hasEventFields = job ? supportsEventFields(job) : false;
  const showSchemaTab = Boolean(
    job && (job.output_kind === 'structured_record' || hasEventFields),
  );
  const latestCodeResult = useMemo(() => {
    const latestRun = runs.find((run) =>
      hasCodeOutput(normalizeJobCodeResult(run.result)),
    );
    return latestRun ? normalizeJobCodeResult(latestRun.result) : null;
  }, [runs]);
  const degradedResourceMessages = useMemo(() => {
    const resources = job?.resource_health?.resources;
    if (!resources) return [];
    return Object.entries(resources)
      .filter(([, resource]) => resource.status === 'degraded')
      .map(([name, resource]) => ({
        name: resourceNameLabel(name),
        message: resource.message || 'Resource check failed.',
      }));
  }, [job?.resource_health]);
  const latestSubmittedRecordSummary = useMemo(() => {
    for (const run of runs) {
      const summary = getSubmittedRecordResultSummary(run.result);
      if (summary) return summary;
    }
    return null;
  }, [runs]);

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

  useEffect(() => {
    if (!isWaitingForReply) {
      setReplyText('');
      pendingReplyRef.current = null;
    }
  }, [isWaitingForReply]);

  const handleReply = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const message = replyText.trim();
      if (!job || !isWaitingForReply || !message) return;
      let pendingReply = pendingReplyRef.current;
      if (!pendingReply || pendingReply.message !== message) {
        pendingReply = {
          message,
          clientReplyId: createClientReplyId(),
        };
        pendingReplyRef.current = pendingReply;
      }

      setIsReplying(true);
      try {
        await replyToJob(job.id, message, pendingReply.clientReplyId);
        toast.success('Answer submitted.');
        pendingReplyRef.current = null;
        setReplyText('');
        await load({ silent: true });
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : 'Failed to submit answer',
        );
      } finally {
        setIsReplying(false);
      }
    },
    [isWaitingForReply, job, load, replyText],
  );

  const handleToggleEnabled = useCallback(async () => {
    if (!job) return;
    setIsBusy(true);
    try {
      const updated = await setJobEnabled(job.id, !job.enabled);
      setJob(updated);
      toast.success(updated.enabled ? 'Job resumed.' : 'Job paused.');
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to update job',
      );
    } finally {
      setIsBusy(false);
    }
  }, [job]);

  const handleCancel = useCallback(async () => {
    if (!job) return;
    setIsBusy(true);
    try {
      const updated = await cancelJobRun(job.id);
      setJob(updated);
      await load({ silent: true });
      toast.success('Run cancelled.');
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to cancel run',
      );
    } finally {
      setIsBusy(false);
    }
  }, [job, load]);

  const handleDelete = useCallback(async () => {
    if (!job) return;
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
                <Badge variant={getStatusBadgeVariant(status)}>
                  {getStatusLabel(status)}
                </Badge>
              ) : null}
              <Badge variant="outline">{getStatusLabel(job.action_kind)}</Badge>
              <Badge variant="outline">{getScheduleLabel(job)}</Badge>
            </div>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            onClick={() => void load()}
            disabled={isLoading || isRunning || isDeleting || isBusy}
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
          {job ? (
            <Button variant="outline" asChild>
              <Link href={`/jobs/${jobId}/edit`}>
                <Pencil className="h-4 w-4" />
                Edit
              </Link>
            </Button>
          ) : null}
          {job?.active_run_id ? (
            <Button
              variant="outline"
              onClick={() => void handleCancel()}
              disabled={isLoading || isRunning || isDeleting || isBusy}
            >
              <Ban className="h-4 w-4" />
              Cancel run
            </Button>
          ) : null}
          {job ? (
            <Button
              variant="outline"
              onClick={() => void handleToggleEnabled()}
              disabled={isLoading || isRunning || isDeleting || isBusy}
            >
              {job.enabled ? (
                <Pause className="h-4 w-4" />
              ) : (
                <Power className="h-4 w-4" />
              )}
              {job.enabled ? 'Pause' : 'Resume'}
            </Button>
          ) : null}
          <Button
            onClick={() => void handleRun()}
            disabled={
              !job ||
              isLoading ||
              isRunning ||
              isDeleting ||
              isBusy ||
              Boolean(job.active_run_id)
            }
          >
            {isRunning ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            Run
          </Button>
          <ConfirmDialog
            title={job ? `Delete "${job.name}"?` : 'Delete job?'}
            description="This permanently removes the job, its schedule, and its run history. This cannot be undone."
            confirmLabel="Delete"
            destructive
            onConfirm={handleDelete}
            trigger={
              <Button
                variant="destructive"
                disabled={
                  !job || isLoading || isRunning || isDeleting || isBusy
                }
              >
                {isDeleting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
                Delete
              </Button>
            }
          />
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
          {isWaitingForReply ? (
            <JobReplyPanel
              question={
                job.waiting_question || 'The job is waiting for a reply.'
              }
              value={replyText}
              isSubmitting={isReplying}
              transcriptHref={`/jobs/${jobId}/thread`}
              onChange={setReplyText}
              onSubmit={handleReply}
            />
          ) : null}

          {job.last_error ? (
            <Alert variant="destructive">
              <AlertTitle>Last error</AlertTitle>
              <AlertDescription>{job.last_error}</AlertDescription>
            </Alert>
          ) : null}

          {job.resource_health?.status === 'degraded' ? (
            <Alert variant="destructive">
              <AlertTitle>Resource health degraded</AlertTitle>
              <AlertDescription>
                {degradedResourceMessages.length ? (
                  <div className="space-y-1">
                    {degradedResourceMessages.map((resource) => (
                      <div key={resource.name}>
                        <span className="font-medium">{resource.name}:</span>{' '}
                        {resource.message}
                      </div>
                    ))}
                  </div>
                ) : (
                  job.resource_health.last_error ||
                  'One or more job resources need attention.'
                )}
              </AlertDescription>
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
                {showSchemaTab ? (
                  <TabsTrigger
                    value="schema"
                    className={JOB_TABS_TRIGGER_CLASSNAME}
                  >
                    {job.output_kind === 'structured_record'
                      ? 'Schema'
                      : 'Subscription'}
                  </TabsTrigger>
                ) : null}
              </TabsList>
            </div>

            <TabsContent value="overview" className="mt-0 space-y-4">
              <section className="grid gap-2 sm:grid-cols-2 xl:flex xl:flex-nowrap">
                <FieldCard
                  label="Status"
                  value={
                    status ? (
                      <Badge variant={getStatusBadgeVariant(status)}>
                        {getStatusLabel(status)}
                      </Badge>
                    ) : (
                      'unknown'
                    )
                  }
                />
                <FieldCard
                  label="Action"
                  value={
                    job.output_kind === 'structured_record'
                      ? 'Record prompt'
                      : getStatusLabel(job.action_kind)
                  }
                />
                <FieldCard
                  label="Trigger"
                  value={getStatusLabel(job.trigger_kind)}
                />
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
                <FieldCard
                  label="Resources"
                  value={
                    <Badge
                      variant={resourceHealthBadgeVariant(
                        job.resource_health?.status,
                      )}
                    >
                      {resourceHealthLabel(job.resource_health?.status)}
                    </Badge>
                  }
                />
                {job.virtual_thing_id ? (
                  <FieldCard
                    label="Virtual thing"
                    value={job.virtual_thing_id}
                    mono
                  />
                ) : null}
                {job.output_kind === 'structured_record' ? (
                  <FieldCard
                    label="Schema version"
                    value={job.record_schema_version || 'Unversioned'}
                  />
                ) : null}
              </section>

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
                    {job.cron_expression ? (
                      <FieldCard
                        label="Cron"
                        value={job.cron_expression}
                        mono
                      />
                    ) : null}
                    {job.cron_timezone ? (
                      <FieldCard
                        label="Timezone"
                        value={job.cron_timezone}
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
                {hasEventFields && job.subscription_id ? (
                  <FieldCard
                    label="Subscription"
                    value={job.subscription_id}
                    mono
                  />
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

              {job.action_kind === 'analysis' ? (
                <CodeOutputPanel
                  result={latestCodeResult ?? {}}
                  title="Latest output"
                />
              ) : (
                <>
                  <TextPanel
                    title={
                      job.output_kind === 'structured_record'
                        ? 'Latest record'
                        : 'Last result'
                    }
                    description={
                      job.output_kind === 'structured_record'
                        ? 'The latest structured record captured from an execution.'
                        : 'The latest response captured from an execution.'
                    }
                    value={
                      latestSubmittedRecordSummary ||
                      job.last_response ||
                      'No result captured yet.'
                    }
                  />
                  {latestCodeResult?.artifacts?.length ? (
                    <CodeOutputPanel
                      result={latestCodeResult}
                      title="Generated artifacts"
                    />
                  ) : null}
                </>
              )}
            </TabsContent>

            <TabsContent value="runs" className="mt-0">
              <JobRunHistoryCard
                runs={runs}
                description="Recent starts, completion times, and captured outcomes."
                outcome={runOutcome}
                showFinished
                minWidthClassName="min-w-[860px]"
              />
            </TabsContent>

            <TabsContent value="definition" className="mt-0">
              <TextPanel
                title={purpose.label}
                description="The action payload used when this job runs."
                value={purpose.content}
              />
            </TabsContent>

            {showSchemaTab ? (
              <TabsContent value="schema" className="mt-0 space-y-4">
                {job.output_kind === 'structured_record' ? (
                  <TextPanel
                    title="Record schema"
                    description="JSON Schema used to parse and validate submitted records."
                    value={formatJson(job.record_schema)}
                    compact
                  />
                ) : null}

                {hasEventFields ? (
                  <TextPanel
                    title="Subscription input"
                    description="Stored event subscription payload for event-triggered jobs."
                    value={formatJson(job.subscription_input)}
                    compact
                  />
                ) : null}
              </TabsContent>
            ) : null}
          </Tabs>
        </>
      ) : null}
    </div>
  );
}
