export interface ReasoningEffortOption {
  label: string;
  value: string;
}

export interface ReasoningEffortConfig {
  enabled: boolean;
  levels: string[];
  defaultLevel: string | null;
}

export const DISABLED_REASONING_EFFORT_CONFIG: ReasoningEffortConfig = {
  enabled: false,
  levels: [],
  defaultLevel: null,
};

export function parseReasoningEffortLevels(raw: string | undefined): string[] {
  if (!raw) {
    return [];
  }

  const seen = new Set<string>();
  for (const rawLevel of raw.split(',')) {
    const level = rawLevel.trim();
    if (level) {
      seen.add(level);
    }
  }
  return [...seen];
}

export function toReasoningEffortLabel(level: string): string {
  return level.length ? level[0].toUpperCase() + level.slice(1) : level;
}

export function resolveDefaultReasoningEffort(
  levels: string[],
  requested: string | undefined,
): string | null {
  if (levels.length === 0) {
    return null;
  }

  const trimmed = requested?.trim();
  if (trimmed && levels.includes(trimmed)) {
    return trimmed;
  }
  return levels[0];
}

export function makeReasoningEffortOptions(
  levels: string[],
): ReasoningEffortOption[] {
  return levels.map((value) => ({
    value,
    label: toReasoningEffortLabel(value),
  }));
}

export function isReasoningEffortSelectorEnabled(
  config: ReasoningEffortConfig,
): boolean {
  return config.enabled && config.levels.length > 0;
}

// Remembers the last level a user picked across page loads (best-effort; a
// disabled/changed level list, or a browser that blocks storage, just falls
// back to the runtime-configured default).
export const REASONING_EFFORT_STORAGE_KEY = 'wotbot-reasoning-effort';

export function resolveStoredReasoningEffort(
  levels: string[],
  stored: string | null,
  fallback: string | null,
): string | null {
  return stored && levels.includes(stored) ? stored : fallback;
}
