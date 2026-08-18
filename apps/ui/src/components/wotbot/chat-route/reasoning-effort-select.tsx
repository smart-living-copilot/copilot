import { useCopilotKit } from '@copilotkit/react-core/v2';
import { useEffect, useState } from 'react';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  DEFAULT_REASONING_EFFORT,
  REASONING_EFFORT_OPTIONS,
  isReasoningEffortSelectorEnabled,
} from '@/lib/reasoning-effort';

export function ReasoningEffortSelect() {
  const { copilotkit } = useCopilotKit();
  const [level, setLevel] = useState(DEFAULT_REASONING_EFFORT);

  // Forward the initial (and every changed) level as AG-UI forwardedProps so
  // the very first run already carries it, not just runs after the first
  // change. wotbot's chat graph reads it back from state as
  // `reasoning_effort` (see agent/nodes.py).
  useEffect(() => {
    if (level) {
      copilotkit.setProperties({ reasoningEffort: level });
    }
  }, [copilotkit, level]);

  if (!isReasoningEffortSelectorEnabled() || !level) {
    return null;
  }

  return (
    <Select onValueChange={setLevel} value={level}>
      <SelectTrigger
        aria-label="Reasoning effort"
        className="h-8"
        size="sm"
        title="Reasoning effort"
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {REASONING_EFFORT_OPTIONS.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
