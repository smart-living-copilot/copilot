'use client';

import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Save } from 'lucide-react';
import { toast } from 'sonner';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { getScheduleLabel, getStatusLabel } from '@/lib/job-formatters';
import {
  type JobRecord,
  type UpdateJobPayload,
  fetchJob,
  updateJob,
} from '@/lib/jobs-api';

interface JobEditPageProps {
  jobId: string;
}

interface EditFormState {
  name: string;
  prompt: string;
  analysisCode: string;
  intervalSeconds: string;
  runAt: string;
  cronExpression: string;
  cronTimezone: string;
  enabled: boolean;
}

function toDatetimeLocal(iso: string | null): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (value: number) => String(value).padStart(2, '0');
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

function toFormState(job: JobRecord): EditFormState {
  return {
    name: job.name,
    prompt: job.prompt ?? '',
    analysisCode: job.analysis_code ?? '',
    intervalSeconds:
      job.interval_seconds != null ? String(job.interval_seconds) : '',
    runAt: toDatetimeLocal(job.run_at),
    cronExpression: job.cron_expression ?? '',
    cronTimezone: job.cron_timezone ?? 'Europe/Berlin',
    enabled: job.enabled,
  };
}

export function JobEditPage({ jobId }: JobEditPageProps) {
  const router = useRouter();
  const [job, setJob] = useState<JobRecord | null>(null);
  const [form, setForm] = useState<EditFormState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const load = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const record = await fetchJob(jobId);
      setJob(record);
      setForm(toFormState(record));
    } catch (error) {
      setLoadError(
        error instanceof Error ? error.message : 'Failed to load job',
      );
    } finally {
      setIsLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    void load();
  }, [load]);

  const setField = useCallback(
    <K extends keyof EditFormState>(field: K, value: EditFormState[K]) => {
      setForm((current) =>
        current ? { ...current, [field]: value } : current,
      );
    },
    [],
  );

  const isInterval =
    job?.trigger_kind === 'time' && job.schedule_kind === 'interval';
  const isOnce = job?.trigger_kind === 'time' && job.schedule_kind === 'once';
  const isCron = job?.trigger_kind === 'time' && job.schedule_kind === 'cron';

  const validationError = useMemo(() => {
    if (!job || !form) return null;
    if (!form.name.trim()) return 'Name is required.';
    if (job.action_kind === 'prompt' && !form.prompt.trim()) {
      return 'Prompt is required.';
    }
    if (job.action_kind === 'analysis' && !form.analysisCode.trim()) {
      return 'Analysis code is required.';
    }
    if (isInterval) {
      const seconds = Number(form.intervalSeconds);
      if (
        !form.intervalSeconds.trim() ||
        !Number.isFinite(seconds) ||
        seconds < 1
      ) {
        return 'Interval must be a positive number of seconds.';
      }
    }
    if (isOnce && !form.runAt.trim()) {
      return 'Run time is required for one-time jobs.';
    }
    if (isCron && !form.cronExpression.trim()) {
      return 'Cron expression is required.';
    }
    return null;
  }, [form, isCron, isInterval, isOnce, job]);

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!job || !form || validationError) return;

      const payload: UpdateJobPayload = {
        name: form.name.trim(),
        enabled: form.enabled,
      };
      if (job.action_kind === 'prompt') {
        payload.prompt = form.prompt.trim();
      } else {
        payload.analysis_code = form.analysisCode.trim();
      }
      if (isInterval) {
        payload.interval_seconds = Number(form.intervalSeconds);
      }
      if (isOnce) {
        payload.run_at = new Date(form.runAt).toISOString();
      }
      if (isCron) {
        payload.cron_expression = form.cronExpression.trim();
        payload.cron_timezone = form.cronTimezone.trim();
      }

      setIsSubmitting(true);
      try {
        await updateJob(job.id, payload);
        toast.success('Job updated.');
        router.push(`/jobs/${job.id}`);
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : 'Failed to update job',
        );
        setIsSubmitting(false);
      }
    },
    [form, isCron, isInterval, isOnce, job, router, validationError],
  );

  if (isLoading) {
    return (
      <Card className="rounded-md border-border/70">
        <CardContent className="flex min-h-56 items-center justify-center">
          <Spinner className="size-6 text-primary" />
        </CardContent>
      </Card>
    );
  }

  if (loadError || !job || !form) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Unable to load job</AlertTitle>
        <AlertDescription>{loadError ?? 'Job not found.'}</AlertDescription>
      </Alert>
    );
  }

  return (
    <form className="space-y-5" onSubmit={(event) => void handleSubmit(event)}>
      <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight">Edit job</h1>
          <p className="max-w-3xl text-sm text-muted-foreground">
            Update the name, action, and schedule. The trigger type and event
            binding are fixed — recreate the job to change those.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" variant="outline" asChild>
            <Link href={`/jobs/${job.id}`}>Cancel</Link>
          </Button>
          <Button
            type="submit"
            disabled={isSubmitting || Boolean(validationError)}
          >
            {isSubmitting ? (
              <Spinner className="size-4" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            Save
          </Button>
        </div>
      </section>

      <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
        <CardHeader className="border-b border-border/70">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <CardTitle className="text-base">Identity</CardTitle>
              <CardDescription>Name the background automation.</CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline">{getStatusLabel(job.action_kind)}</Badge>
              <Badge variant="outline">{getScheduleLabel(job)}</Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Name</label>
            <Input
              value={form.name}
              onChange={(event) => setField('name', event.target.value)}
              placeholder="Morning energy summary"
            />
          </div>
          <div className="flex items-center justify-between rounded-md border border-border/70 px-3 py-2">
            <div>
              <div className="text-sm font-medium">Enabled</div>
              <p className="text-xs text-muted-foreground">
                Paused jobs keep their history but never run automatically.
              </p>
            </div>
            <Switch
              checked={form.enabled}
              onCheckedChange={(value) => setField('enabled', value)}
            />
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
        <CardHeader className="border-b border-border/70">
          <CardTitle className="text-base">
            {job.action_kind === 'analysis' ? 'Analysis code' : 'Prompt'}
          </CardTitle>
          <CardDescription>
            What the job runs each time it is triggered.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {job.action_kind === 'analysis' ? (
            <Textarea
              rows={12}
              value={form.analysisCode}
              onChange={(event) => setField('analysisCode', event.target.value)}
              placeholder="print({'summary': '...', 'value': 0.8})"
            />
          ) : (
            <Textarea
              rows={9}
              value={form.prompt}
              onChange={(event) => setField('prompt', event.target.value)}
              placeholder="Summarize the latest occupancy and temperature changes."
            />
          )}
        </CardContent>
      </Card>

      {isInterval || isOnce || isCron ? (
        <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
          <CardHeader className="border-b border-border/70">
            <CardTitle className="text-base">Schedule</CardTitle>
            <CardDescription>
              {isInterval
                ? 'How often this job runs. Saving resets the next run.'
                : isCron
                  ? 'The cron expression and timezone for this recurring job.'
                  : 'When this one-time job runs.'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isInterval ? (
              <div className="space-y-2 sm:max-w-xs">
                <label className="text-sm font-medium">Interval seconds</label>
                <Input
                  type="number"
                  min="1"
                  value={form.intervalSeconds}
                  onChange={(event) =>
                    setField('intervalSeconds', event.target.value)
                  }
                  placeholder="300"
                />
              </div>
            ) : isCron ? (
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Cron expression</label>
                  <Input
                    value={form.cronExpression}
                    onChange={(event) =>
                      setField('cronExpression', event.target.value)
                    }
                    placeholder="0 9 * * sun"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Cron timezone</label>
                  <Input
                    value={form.cronTimezone}
                    onChange={(event) =>
                      setField('cronTimezone', event.target.value)
                    }
                    placeholder="Europe/Berlin"
                  />
                </div>
              </div>
            ) : (
              <div className="space-y-2 sm:max-w-xs">
                <label className="text-sm font-medium">Run once at</label>
                <Input
                  type="datetime-local"
                  value={form.runAt}
                  onChange={(event) => setField('runAt', event.target.value)}
                />
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}

      {validationError ? (
        <p className="text-sm text-destructive">{validationError}</p>
      ) : null}
    </form>
  );
}
