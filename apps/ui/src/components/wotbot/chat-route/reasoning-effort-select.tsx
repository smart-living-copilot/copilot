import { useCopilotKit } from '@copilotkit/react-core/v2';
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
}: {
  config: ReasoningEffortConfig;
}) {
  const { copilotkit } = useCopilotKit();
  // Start from the SSR-safe default (localStorage doesn't exist on the
  // server), not the stored preference — otherwise the server-rendered
  // markup and the client's first render disagree and React flags a
  // hydration mismatch. The stored value is adopted right after mount below.
  const [level, setLevel] = useState(config.defaultLevel);
  const selectorEnabled = isReasoningEffortSelectorEnabled(config);
  const options = makeReasoningEffortOptions(config.levels);

  // Runs once, client-only, after hydration: swap in the user's last pick if
  // one is stored and still valid for the current level list.
  useEffect(() => {
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

  // Forward the initial (and every changed) level as AG-UI forwardedProps so
  // the very first run already carries it, not just runs after the first
  // change. wotbot's chat graph reads it back from state as
  // `reasoning_effort` (see agent/nodes.py).
  useEffect(() => {
    if (selectorEnabled && level) {
      copilotkit.setProperties({
        ...copilotkit.properties,
        reasoningEffort: level,
      });
    }
  }, [copilotkit, level, selectorEnabled]);

  const handleChange = useCallback((next: string) => {
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
