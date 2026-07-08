import type { Message } from '@copilotkit/shared';

import {
  normalizeRunCodeResult,
  type RunCodeArtifact,
} from '@/components/wotbot/chat-tool-call-model';

export function dedupeMessages(messages: Message[]): Message[] {
  const latestById = new Map<string, Message>();
  for (const message of messages) {
    latestById.set(message.id, message);
  }

  const deduped: Message[] = [];
  const seen = new Set<string>();
  for (const message of messages) {
    const latest = latestById.get(message.id);
    if (!latest || seen.has(latest.id)) {
      continue;
    }
    seen.add(latest.id);
    deduped.push(latest);
  }

  return deduped;
}

function getMessageRole(message: Message) {
  return typeof message.role === 'string' ? message.role : '';
}

function getMessageContent(message: Message) {
  return (message as { content?: unknown }).content;
}

export function getLatestTurnArtifacts(messages: Message[]): RunCodeArtifact[] {
  let lastUserIndex = -1;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (getMessageRole(messages[index]) === 'user') {
      lastUserIndex = index;
      break;
    }
  }

  if (lastUserIndex < 0) {
    return [];
  }

  const artifacts: RunCodeArtifact[] = [];
  const seen = new Set<string>();

  for (const message of messages.slice(lastUserIndex + 1)) {
    if (getMessageRole(message) !== 'tool') {
      continue;
    }

    const result = normalizeRunCodeResult(getMessageContent(message));
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
