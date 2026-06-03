import {
  Bot,
  CheckCircle2,
  CircleDot,
  ClipboardCheck,
  MessageSquare,
  XCircle,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { type JobRunEventRecord, type JobRunEventType } from '@/lib/jobs-api';

function eventLabel(type: JobRunEventType): string {
  switch (type) {
    case 'run_started':
      return 'Started';
    case 'user_reply':
      return 'Reply';
    case 'waiting_for_input':
      return 'Waiting';
    case 'assistant_message':
      return 'Assistant';
    case 'record_submitted':
      return 'Record';
    case 'run_succeeded':
      return 'Succeeded';
    case 'run_failed':
      return 'Failed';
    case 'run_cancelled':
      return 'Cancelled';
    case 'run_skipped':
      return 'Skipped';
  }
}

function eventIcon(type: JobRunEventType) {
  switch (type) {
    case 'run_succeeded':
      return <CheckCircle2 className="h-4 w-4 text-emerald-600" />;
    case 'run_failed':
    case 'run_cancelled':
      return <XCircle className="h-4 w-4 text-destructive" />;
    case 'user_reply':
      return <MessageSquare className="h-4 w-4 text-sky-600" />;
    case 'assistant_message':
    case 'waiting_for_input':
      return <Bot className="h-4 w-4 text-primary" />;
    case 'record_submitted':
      return <ClipboardCheck className="h-4 w-4 text-emerald-600" />;
    default:
      return <CircleDot className="h-4 w-4 text-muted-foreground" />;
  }
}

function eventFallbackMessage(type: JobRunEventType): string {
  switch (type) {
    case 'run_started':
      return 'Run started.';
    case 'record_submitted':
      return 'Structured record submitted.';
    case 'run_succeeded':
      return 'Run succeeded.';
    case 'run_failed':
      return 'Run failed.';
    case 'run_cancelled':
      return 'Run cancelled.';
    case 'run_skipped':
      return 'Run skipped.';
    case 'waiting_for_input':
      return 'Waiting for input.';
    case 'user_reply':
      return 'Reply received.';
    case 'assistant_message':
      return 'Assistant response.';
  }
}

function formatEventTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function payloadPreview(payload: unknown): string | null {
  if (payload == null) return null;
  try {
    return JSON.stringify(payload, null, 2);
  } catch {
    return String(payload);
  }
}

export function JobEventTimeline({ events }: { events: JobRunEventRecord[] }) {
  return (
    <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold tracking-tight">Timeline</h2>
          <Badge variant="outline">{events.length} events</Badge>
        </div>
        <div className="divide-y rounded-md border bg-background">
          {events.map((event) => {
            const preview =
              event.event_type === 'record_submitted'
                ? payloadPreview(event.payload)
                : null;
            return (
              <div
                key={event.id}
                className="grid grid-cols-[2rem_1fr] gap-3 px-4 py-3"
              >
                <div className="flex h-8 w-8 items-center justify-center rounded-md border bg-muted/30">
                  {eventIcon(event.event_type)}
                </div>
                <div className="min-w-0 space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="secondary">
                      {eventLabel(event.event_type)}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      {formatEventTime(event.created_at)}
                    </span>
                  </div>
                  <p className="whitespace-pre-wrap break-words text-sm leading-6 text-foreground">
                    {event.message || eventFallbackMessage(event.event_type)}
                  </p>
                  {preview ? (
                    <pre className="max-h-64 overflow-auto rounded-md bg-muted/30 p-3 text-xs leading-5 text-muted-foreground">
                      {preview}
                    </pre>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
