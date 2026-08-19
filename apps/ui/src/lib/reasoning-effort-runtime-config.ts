import {
  parseReasoningEffortLevels,
  resolveDefaultReasoningEffort,
  type ReasoningEffortConfig,
} from './reasoning-effort';

export const REASONING_EFFORT_ENABLED_ENV = 'REASONING_EFFORT_ENABLED';
export const REASONING_EFFORT_LEVELS_ENV = 'REASONING_EFFORT_LEVELS';
export const REASONING_EFFORT_DEFAULT_ENV = 'REASONING_EFFORT_DEFAULT';

const DEFAULT_LEVELS = 'low,medium,high';

type RuntimeEnvironment = Record<string, string | undefined>;

export function getReasoningEffortRuntimeConfig(
  environment: RuntimeEnvironment = process.env,
): ReasoningEffortConfig {
  const levels = parseReasoningEffortLevels(
    environment[REASONING_EFFORT_LEVELS_ENV] ?? DEFAULT_LEVELS,
  );

  return {
    enabled: environment[REASONING_EFFORT_ENABLED_ENV] === 'true',
    levels,
    defaultLevel: resolveDefaultReasoningEffort(
      levels,
      environment[REASONING_EFFORT_DEFAULT_ENV],
    ),
  };
}
