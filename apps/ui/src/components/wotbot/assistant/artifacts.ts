import {
  normalizeRunCodeResult,
  type RunCodeArtifact,
} from '@/components/wotbot/chat-tool-call-model';
import type { LangChainMessage } from '@/lib/thread-messages';

/**
 * Artifacts produced since the last user message.
 *
 * Live mode shows only the current turn's plots, so this walks back to the
 * most recent human message and collects what the tools returned after it.
 * The LangChain-shaped counterpart of the AG-UI `getLatestTurnArtifacts`.
 */
export function latestTurnArtifacts(
  messages: readonly LangChainMessage[] | undefined,
): RunCodeArtifact[] {
  if (!messages?.length) {
    return [];
  }

  let lastHumanIndex = -1;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const type = messages[index]?.type;
    if (type === 'human' || type === 'user') {
      lastHumanIndex = index;
      break;
    }
  }
  if (lastHumanIndex < 0) {
    return [];
  }

  const artifacts: RunCodeArtifact[] = [];
  const seen = new Set<string>();

  for (const message of messages.slice(lastHumanIndex + 1)) {
    if (message.type !== 'tool') {
      continue;
    }
    const result = normalizeRunCodeResult(message.content);
    for (const artifact of result.artifacts ?? []) {
      const key = `${artifact.kind}:${artifact.filename}`;
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      artifacts.push(artifact);
    }
  }

  return artifacts;
}
