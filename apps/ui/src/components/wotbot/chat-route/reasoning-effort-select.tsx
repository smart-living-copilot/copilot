import { Gauge } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  REASONING_EFFORT_STORAGE_KEY,
  isReasoningEffortSelectorEnabled,
  makeReasoningEffortOptions,
  resolveStoredReasoningEffort,
  type ReasoningEffortConfig,
} from '@/lib/reasoning-effort';

function readStoredReasoningEffort(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    return window.localStorage.getItem(REASONING_EFFORT_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function ReasoningEffortSelect({
  config,
  onLevelChange,
  value,
}: {
  config: ReasoningEffortConfig;
  /** Reports the active level so the next run can carry it as graph state. */
  onLevelChange?: (level: string | null) => void;
  /** The level the parent already holds, if any. */
  value?: string;
}) {
  // Seed from the level the parent is holding, falling back to the SSR-safe
  // default (localStorage doesn't exist on the server, and reading the stored
  // preference here would make the server markup and the client's first render
  // disagree — a hydration mismatch). The stored value is adopted right after
  // mount below.
  //
  // The fallback is not just an SSR concern: this component unmounts for the
  // duration of every run (ThreadPrimitive.If running={false} in
  // assistant/thread.tsx) and remounts when the run ends. Without `value` each
  // remount would restart at the default and the effect below would report that
  // default back up, overwriting the user's pick — so the choice would survive
  // only as far as localStorage carried it.
  const [level, setLevel] = useState(() =>
    resolveStoredReasoningEffort(
      config.levels,
      value ?? null,
      config.defaultLevel,
    ),
  );
  const selectorEnabled = isReasoningEffortSelectorEnabled(config);
  const options = makeReasoningEffortOptions(config.levels);

  // Runs once, client-only, after hydration: swap in the user's last pick if
  // one is stored and still valid for the current level list. Skipped when the
  // parent already handed us a level, so the precedence stays parent > stored >
  // default — the parent's copy is the one that just came from this session.
  useEffect(() => {
    if (value) {
      return;
    }
    const stored = resolveStoredReasoningEffort(
      config.levels,
      readStoredReasoningEffort(),
      null,
    );
    if (stored) {
      setLevel(stored);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentionally mount-only
  }, []);

  // Report the initial (and every changed) level so the very first run already
  // carries it, not just runs after the first change. It travels as ordinary
  // graph state; wotbot's chat graph reads it back as `reasoning_effort` (see
  // agent/nodes.py).
  useEffect(() => {
    onLevelChange?.(selectorEnabled && level ? level : null);
  }, [level, onLevelChange, selectorEnabled]);

  const handleChange = useCallback((next: string) => {
    // The composer's action row unmounts while a run is in flight (see
    // ThreadPrimitive.If running={false} in assistant/thread.tsx). Radix
    // reports that teardown as a change to the empty value, which would blank
    // `level` -- and a blank level renders nothing, so the control silently
    // disappeared for the rest of the session. Only real picks count.
    if (!next) {
      return;
    }
    setLevel(next);
    try {
      window.localStorage.setItem(REASONING_EFFORT_STORAGE_KEY, next);
    } catch {
      // Persistence is best-effort in private or restricted contexts.
    }
  }, []);

  if (!selectorEnabled || !level) {
    return null;
  }

  return (
    <Select onValueChange={handleChange} value={level}>
      <SelectTrigger
        aria-label="Reasoning effort"
        className="h-8"
        size="sm"
        title="Reasoning effort"
      >
        <Gauge className="size-4 text-muted-foreground" />
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
