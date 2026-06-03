'use client';

import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { useRouter } from 'next/navigation';
import { Save } from 'lucide-react';
import { toast } from 'sonner';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Spinner } from '@/components/ui/spinner';
import { JobActionFields } from '@/components/jobs/form/job-action-fields';
import { JobEnabledField } from '@/components/jobs/form/job-enabled-field';
import { JobFormCard } from '@/components/jobs/form/job-form-card';
import { JobFormHeader } from '@/components/jobs/form/job-form-header';
import {
  type EditJobFormState,
  type JobScheduleKind,
  getEditableScheduleKind,
  toEditJobFormState,
  toUpdateJobPayload,
  validateEditJobForm,
} from '@/components/jobs/form/job-form-model';
import { JobScheduleFields } from '@/components/jobs/form/job-schedule-fields';
import { getScheduleLabel, getStatusLabel } from '@/lib/job-formatters';
import { type JobRecord, fetchJob, updateJob } from '@/lib/jobs-api';

interface JobEditPageProps {
  jobId: string;
}

function getScheduleDescription(scheduleKind: JobScheduleKind): string {
  if (scheduleKind === 'interval') {
    return 'How often this job runs. Saving resets the next run.';
  }
  if (scheduleKind === 'cron') {
    return 'The cron expression and timezone for this recurring job.';
  }
  return 'When this one-time job runs.';
}

export function JobEditPage({ jobId }: JobEditPageProps) {
  const router = useRouter();
  const [job, setJob] = useState<JobRecord | null>(null);
  const [form, setForm] = useState<EditJobFormState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const load = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const record = await fetchJob(jobId);
      setJob(record);
      setForm(toEditJobFormState(record));
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
    <K extends keyof EditJobFormState>(
      field: K,
      value: EditJobFormState[K],
    ) => {
      setForm((current) =>
        current ? { ...current, [field]: value } : current,
      );
    },
    [],
  );

  const scheduleKind = job ? getEditableScheduleKind(job) : null;

  const validationError = useMemo(() => {
    if (!job || !form) return null;
    return validateEditJobForm(job, form);
  }, [form, job]);

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!job || !form || validationError) return;

      setIsSubmitting(true);
      try {
        await updateJob(job.id, toUpdateJobPayload(job, form));
        toast.success('Job updated.');
        router.push(`/jobs/${job.id}`);
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : 'Failed to update job',
        );
        setIsSubmitting(false);
      }
    },
    [form, job, router, validationError],
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
      <JobFormHeader
        title="Edit job"
        description="Update the name, action, and schedule. The trigger type and event binding are fixed — recreate the job to change those."
        cancelHref={`/jobs/${job.id}`}
        submitLabel="Save"
        submitIcon={<Save className="h-4 w-4" />}
        isSubmitting={isSubmitting}
        disabled={isSubmitting || Boolean(validationError)}
      />

      <JobFormCard
        title="Identity"
        description="Name the background automation."
        contentClassName="space-y-4"
        headerAction={
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">{getStatusLabel(job.action_kind)}</Badge>
            <Badge variant="outline">{getScheduleLabel(job)}</Badge>
          </div>
        }
      >
        <div className="space-y-2">
          <label className="text-sm font-medium">Name</label>
          <Input
            value={form.name}
            onChange={(event) => setField('name', event.target.value)}
            placeholder="Morning energy summary"
          />
        </div>
        <JobEnabledField
          enabled={form.enabled}
          onEnabledChange={(value) => setField('enabled', value)}
        />
      </JobFormCard>

      <JobFormCard
        title={job.action_kind === 'analysis' ? 'Analysis code' : 'Prompt'}
        description="What the job runs each time it is triggered."
      >
        <JobActionFields
          actionKind={job.action_kind}
          prompt={form.prompt}
          analysisCode={form.analysisCode}
          onPromptChange={(value) => setField('prompt', value)}
          onAnalysisCodeChange={(value) => setField('analysisCode', value)}
          showLabels={false}
        />
      </JobFormCard>

      {scheduleKind ? (
        <JobFormCard
          title="Schedule"
          description={getScheduleDescription(scheduleKind)}
        >
          <JobScheduleFields
            scheduleKind={scheduleKind}
            intervalSeconds={form.intervalSeconds}
            runAt={form.runAt}
            cronExpression={form.cronExpression}
            cronTimezone={form.cronTimezone}
            onIntervalSecondsChange={(value) =>
              setField('intervalSeconds', value)
            }
            onRunAtChange={(value) => setField('runAt', value)}
            onCronExpressionChange={(value) =>
              setField('cronExpression', value)
            }
            onCronTimezoneChange={(value) => setField('cronTimezone', value)}
          />
        </JobFormCard>
      ) : null}

      {validationError ? (
        <p className="text-sm text-destructive">{validationError}</p>
      ) : null}
    </form>
  );
}
