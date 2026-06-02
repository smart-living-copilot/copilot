import {
  normalizeRunCodeResult,
  type RunCodeResult,
} from '@/components/copilot/chat-tool-call-model';

/** True when a run produced visible output: stdout, an error, or artifacts. */
export function hasCodeOutput(result: RunCodeResult): boolean {
  return Boolean(
    result.error?.trim() ||
    result.stdout?.trim() ||
    (result.artifacts?.length ?? 0) > 0,
  );
}

/**
 * Normalize a job run result into a {@link RunCodeResult}, transparently
 * unwrapping a nested `{ response: ... }` envelope when the top-level value
 * carries no visible output.
 */
export function normalizeJobCodeResult(value: unknown): RunCodeResult {
  const direct = normalizeRunCodeResult(value);
  if (hasCodeOutput(direct)) {
    return direct;
  }

  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return direct;
  }

  return normalizeRunCodeResult((value as { response?: unknown }).response);
}
