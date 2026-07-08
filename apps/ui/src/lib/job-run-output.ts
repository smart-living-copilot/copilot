import {
  formatArtifactSummary,
  type RunCodeResult,
} from '@/components/wotbot/chat-tool-call-model';
import { hasCodeOutput, normalizeJobCodeResult } from '@/lib/job-code-result';
import { getSubmittedRecordResultSummary } from '@/lib/job-formatters';
import { type JobRunRecord } from '@/lib/jobs-api';

export function formatJsonValue(value: unknown): string {
  if (value == null) return 'Not available';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function getCodeArtifactSummary(result: RunCodeResult): string {
  return result.artifacts?.length
    ? formatArtifactSummary(result.artifacts)
    : '';
}

export function formatJobRunOutcome(run: JobRunRecord): string {
  const codeResult = normalizeJobCodeResult(run.result);
  const artifactSummary = getCodeArtifactSummary(codeResult);
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
  if (run.result != null) return formatJsonValue(run.result);
  return 'No output captured.';
}

export function findLatestCodeResult(
  runs: JobRunRecord[],
): RunCodeResult | null {
  const latestRun = runs.find((run) =>
    hasCodeOutput(normalizeJobCodeResult(run.result)),
  );
  return latestRun ? normalizeJobCodeResult(latestRun.result) : null;
}
