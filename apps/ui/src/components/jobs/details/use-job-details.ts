import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';

import { getDegradedResourceMessages } from '@/components/jobs/details/job-details-formatters';
import { useJobEvents } from '@/hooks/use-job-events';
import {
  getJobStatus,
  getPurposePreview,
  getSubmittedRecordResultSummary,
  supportsEventFields,
  supportsJobReply,
  supportsJobThread,
  supportsTimeFields,
} from '@/lib/job-formatters';
import { findLatestCodeResult } from '@/lib/job-run-output';
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

export function useJobDetails(jobId: string) {
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
  const latestCodeResult = useMemo(() => findLatestCodeResult(runs), [runs]);
  const degradedResourceMessages = useMemo(
    () => getDegradedResourceMessages(job),
    [job],
  );
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

  const handleVoiceAnswer = useCallback((message: string) => {
    setReplyText((current) => {
      const currentText = current.trim();
      return currentText ? `${currentText} ${message}` : message;
    });
  }, []);

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

  return {
    job,
    runs,
    isLoading,
    isRunning,
    isReplying,
    isDeleting,
    isBusy,
    replyText,
    setReplyText,
    loadError,
    status,
    purpose,
    hasJobThread,
    isWaitingForReply,
    hasTimeFields,
    hasEventFields,
    showSchemaTab,
    latestCodeResult,
    degradedResourceMessages,
    latestSubmittedRecordSummary,
    load,
    handleRun,
    handleReply,
    handleVoiceAnswer,
    handleToggleEnabled,
    handleCancel,
    handleDelete,
  };
}
