import { type FormEvent, type ReactNode } from 'react';
import { Send } from 'lucide-react';

import { RunCodeArtifactCard } from '@/components/wotbot/chat-tool-call-cards';
import { type RunCodeResult } from '@/components/wotbot/chat-tool-call-model';
import { PulseDot } from '@/components/jobs/details/pulse-dot';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Spinner } from '@/components/ui/spinner';
import { Textarea } from '@/components/ui/textarea';
import { getCodeArtifactSummary } from '@/lib/job-run-output';

export function FieldCard({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
}) {
  return (
    <Card
      size="sm"
      className="rounded-md border-border/70 shadow-sm shadow-black/5 xl:min-w-0 xl:flex-1 xl:basis-0"
    >
      <CardContent>
        <div className="text-xs text-muted-foreground">{label}</div>
        <div
          className={
            mono
              ? 'mt-1 break-all font-mono text-xs leading-5 text-foreground'
              : 'mt-1 truncate text-sm font-medium text-foreground'
          }
        >
          {value}
        </div>
      </CardContent>
    </Card>
  );
}

export function TextPanel({
  title,
  description,
  value,
  compact = false,
}: {
  title: string;
  description?: string;
  value: string;
  compact?: boolean;
}) {
  return (
    <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
      <CardHeader className="border-b border-border/70">
        <CardTitle className="text-base">{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent>
        <pre
          className={
            compact
              ? 'max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs leading-5 text-muted-foreground'
              : 'max-h-[32rem] overflow-auto whitespace-pre-wrap break-words text-sm leading-6 text-muted-foreground'
          }
        >
          {value}
        </pre>
      </CardContent>
    </Card>
  );
}

export function CodeOutputPanel({
  result,
  title = 'Code output',
}: {
  result: RunCodeResult;
  title?: string;
}) {
  const artifactSummary = getCodeArtifactSummary(result);
  const hasStdout = !!result.stdout?.trim();
  const hasError = !!result.error?.trim();

  if (!artifactSummary && !hasStdout && !hasError) {
    return (
      <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
        <CardHeader className="border-b border-border/70">
          <CardTitle className="text-base">{title}</CardTitle>
          <CardDescription>No visible output captured yet.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
      <CardHeader className="border-b border-border/70">
        <CardTitle className="text-base">{title}</CardTitle>
        <CardDescription>
          {artifactSummary || 'Text output from the latest analysis run.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {hasError ? (
          <Alert variant="destructive">
            <AlertTitle>Execution failed</AlertTitle>
            <AlertDescription>
              <pre className="overflow-auto whitespace-pre-wrap text-xs leading-5">
                {result.error}
              </pre>
            </AlertDescription>
          </Alert>
        ) : null}

        {result.artifacts?.length ? (
          <div className="space-y-2">
            {result.artifacts.map((artifact) => (
              <RunCodeArtifactCard
                key={`${artifact.kind}:${artifact.filename}`}
                artifact={artifact}
              />
            ))}
          </div>
        ) : null}

        {hasStdout ? (
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-md border bg-muted/20 p-3 text-sm leading-6 text-muted-foreground">
            {result.stdout}
          </pre>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function JobReplyPanel({
  question,
  value,
  isSubmitting,
  onChange,
  onSubmit,
}: {
  question: string;
  value: string;
  isSubmitting: boolean;
  onChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const canSubmit = value.trim().length > 0 && !isSubmitting;

  return (
    <Card className="rounded-md border-primary/40 bg-primary/5 shadow-sm shadow-black/5">
      <CardHeader className="border-b border-primary/20">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2 text-base">
              <PulseDot />
              Waiting for your answer
            </CardTitle>
            <CardDescription>
              Reply to the pending question to continue the run.
            </CardDescription>
          </div>
          <Badge>Needs input</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-md border border-primary/20 bg-background p-4">
          <div className="text-xs font-medium text-muted-foreground">
            Question
          </div>
          <p className="mt-2 whitespace-pre-wrap break-words text-base leading-7 text-foreground">
            {question}
          </p>
        </div>
        <form className="space-y-3" onSubmit={onSubmit}>
          <Textarea
            aria-label="Job answer"
            className="min-h-28 resize-y"
            placeholder="Answer..."
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            disabled={isSubmitting}
          />
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span className="text-xs text-muted-foreground">
              Press Cmd/Ctrl + Enter to submit
            </span>
            <div className="flex justify-end gap-2">
              <Button type="submit" size="sm" disabled={!canSubmit}>
                {isSubmitting ? (
                  <Spinner className="size-4" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
                Submit answer
              </Button>
            </div>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
