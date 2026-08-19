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
  const [level, setLevel] = useState(() =>
    resolveStoredReasoningEffort(
      config.levels,
      readStoredReasoningEffort(),
      config.defaultLevel,
    ),
  );
  const selectorEnabled = isReasoningEffortSelectorEnabled(config);
  const options = makeReasoningEffortOptions(config.levels);

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
