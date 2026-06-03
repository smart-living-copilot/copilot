import { type ChatSummary } from '@/lib/chat-list-cache';

const relativeTimeFormatter = new Intl.RelativeTimeFormat(undefined, {
  numeric: 'auto',
});

const shortDateFormatter = new Intl.DateTimeFormat(undefined, {
  month: 'short',
  day: 'numeric',
});

export function formatUpdatedAt(updatedAt: string): string {
  const date = new Date(updatedAt);
  if (Number.isNaN(date.getTime())) {
    return 'Recently updated';
  }

  const diffMs = date.getTime() - Date.now();
  const absDiffMs = Math.abs(diffMs);

  if (absDiffMs < 60_000) {
    return 'Updated just now';
  }

  if (absDiffMs < 3_600_000) {
    return `Updated ${relativeTimeFormatter.format(
      Math.round(diffMs / 60_000),
      'minute',
    )}`;
  }

  if (absDiffMs < 86_400_000) {
    return `Updated ${relativeTimeFormatter.format(
      Math.round(diffMs / 3_600_000),
      'hour',
    )}`;
  }

  if (absDiffMs < 604_800_000) {
    return `Updated ${relativeTimeFormatter.format(
      Math.round(diffMs / 86_400_000),
      'day',
    )}`;
  }

  return `Updated ${shortDateFormatter.format(date)}`;
}

function getHistoryGroupLabel(updatedAt: string): string {
  const date = new Date(updatedAt);
  if (Number.isNaN(date.getTime())) {
    return 'Earlier';
  }

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const updatedDay = new Date(date);
  updatedDay.setHours(0, 0, 0, 0);

  const diffDays = Math.floor(
    (today.getTime() - updatedDay.getTime()) / 86_400_000,
  );

  if (diffDays <= 0) {
    return 'Today';
  }

  if (diffDays === 1) {
    return 'Yesterday';
  }

  if (diffDays < 7) {
    return 'This week';
  }

  return 'Earlier';
}

export function groupChatsByUpdatedAt(chats: ChatSummary[]) {
  const groupedChats: Array<{ label: string; chats: ChatSummary[] }> = [];

  for (const chat of chats) {
    const label = getHistoryGroupLabel(chat.updatedAt);
    const existingGroup = groupedChats.find((group) => group.label === label);

    if (existingGroup) {
      existingGroup.chats.push(chat);
    } else {
      groupedChats.push({ label, chats: [chat] });
    }
  }

  return groupedChats;
}
