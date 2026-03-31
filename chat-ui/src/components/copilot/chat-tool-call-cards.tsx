'use client';

import { type ReactNode, useState } from 'react';
import { CircleAlert, CheckCircle2, ChevronDown, Loader2 } from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';

import {
  formatArtifactSummary,
  formatToolData,
  formatToolName,
  hasErrorResult,
  hasInspectableData,
  normalizeRunCodeResult,
  summarizeValue,
  TOOL_STATUS_DESCRIPTION,
  type CatchAllToolCallRenderProps,
  type RunCodeArtifact,
  type RunCodeResult,
  type ToolCallStatus,
} from './chat-tool-call-model';

function ToolPayloadSection({
  title,
  value,
}: {
  title: string;
  value: unknown;
}) {
  if (!hasInspectableData(value)) {
    return null;
  }

  return (
    <Card className="gap-0 border border-border/60 bg-background/80 py-0 shadow-none ring-0">
      <CardHeader className="border-b border-border/60 py-2">
        <CardTitle className="text-[0.66rem] font-semibold tracking-[0.16em] text-muted-foreground uppercase">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="py-2.5">
        <pre className="max-h-60 overflow-auto text-[0.74rem] leading-5 whitespace-pre-wrap text-foreground">
          {formatToolData(value)}
        </pre>
      </CardContent>
    </Card>
  );
}

function PlotlyChart({ filename, title }: { filename: string; title: string }) {
  return (
    <iframe
      className="h-[24rem] w-full rounded-lg border border-border/55 bg-background"
      loading="lazy"
      sandbox="allow-scripts allow-same-origin"
      src={`/api/artifacts/${encodeURIComponent(filename)}`}
      title={title}
    />
  );
}

function ToolStatusIcon({
  hasError = false,
  status,
}: {
  hasError?: boolean;
  status: ToolCallStatus;
}) {
  if (hasError) {
    return <CircleAlert className="size-3.5 text-destructive" />;
  }

  if (status === 'complete') {
    return (
      <CheckCircle2 className="size-3.5 text-emerald-600 dark:text-emerald-400" />
    );
  }

  return <Loader2 className="size-3.5 animate-spin text-primary" />;
}

function ToolCardHeader({
  action,
  hasError = false,
  isCompleted,
  status,
  summary,
  title,
}: {
  action?: ReactNode;
  hasError?: boolean;
  isCompleted: boolean;
  status: ToolCallStatus;
  summary?: ReactNode;
  title: string;
}) {
  return (
    <div
      className={cn(
        'flex flex-wrap items-center justify-between gap-2 px-1 py-1',
        !isCompleted &&
          'rounded-lg border border-border/45 bg-background/45 px-2.5 py-1.5',
      )}
    >
      <div className="flex min-w-0 items-center gap-2.5">
        <ToolStatusIcon hasError={hasError} status={status} />

        <div className="min-w-0 space-y-0.5">
          <p
            className={cn(
              'truncate font-medium text-foreground',
              isCompleted ? 'text-[0.76rem]' : 'text-[0.82rem]',
            )}
          >
            {title}
          </p>

          {summary ? (
            <div className="truncate text-[0.7rem] text-muted-foreground">
              {summary}
            </div>
          ) : null}
        </div>
      </div>

      {action}
    </div>
  );
}

function RunCodeArtifactCard({ artifact }: { artifact: RunCodeArtifact }) {
  return (
    <Card className="gap-0 border border-border/55 bg-background/45 py-0 shadow-none ring-0">
      <CardContent className="space-y-1.5 py-2">
        <div className="flex items-center gap-2 px-0.5">
          <Badge className="h-5 font-mono text-[0.66rem]" variant="outline">
            {artifact.ref}
          </Badge>
          <span className="text-[0.7rem] text-muted-foreground">
            {artifact.kind === 'plotly' ? 'Interactive chart' : 'Image'}
          </span>
        </div>

        {artifact.kind === 'image' ? (
          // eslint-disable-next-line @next/next/no-img-element -- generated code artifacts are proxied files and do not benefit from Next image optimization
          <img
            alt={artifact.ref}
            className="max-w-full rounded-lg border border-border/55"
            src={`/api/artifacts/${encodeURIComponent(artifact.filename)}`}
          />
        ) : (
          <PlotlyChart
            filename={artifact.filename}
            title={`Chart ${artifact.ref}`}
          />
        )}
      </CardContent>
    </Card>
  );
}

function RunCodeOutput({ result }: { result: RunCodeResult }) {
  if (!(result.artifacts?.length ?? 0)) {
    return null;
  }

  return (
    <div className="space-y-2">
      {result.artifacts?.map((artifact) => (
        <RunCodeArtifactCard
          key={`${artifact.kind}:${artifact.filename}`}
          artifact={artifact}
        />
      ))}
    </div>
  );
}

function RunCodeDetails({ result }: { result: RunCodeResult }) {
  const hasStdout = !!result.stdout?.trim();
  const hasError = !!result.error;

  if (!hasStdout && !hasError) {
    return null;
  }

  return (
    <div className="space-y-2 rounded-lg border border-border/55 bg-background/40 p-2.5">
      {hasError ? (
        <Alert
          className="border-destructive/25 bg-destructive/5"
          variant="destructive"
        >
          <CircleAlert className="h-4 w-4" />
          <AlertTitle>Execution failed</AlertTitle>
          <AlertDescription>
            <pre className="overflow-auto font-mono text-[0.72rem] leading-5 whitespace-pre-wrap text-destructive">
              {result.error}
            </pre>
          </AlertDescription>
        </Alert>
      ) : null}

      {hasStdout ? (
        <pre className="max-h-52 overflow-auto rounded-lg border border-border/55 bg-background/80 px-3 py-2.5 text-[0.72rem] leading-5 whitespace-pre-wrap text-foreground">
          {result.stdout}
        </pre>
      ) : null}
    </div>
  );
}

function DetailsToggle({
  expanded,
  label = 'Details',
}: {
  expanded: boolean;
  label?: string;
}) {
  return (
    <CollapsibleTrigger asChild>
      <Button
        className="text-[0.66rem] font-medium text-muted-foreground hover:text-foreground"
        size="xs"
        type="button"
        variant="ghost"
      >
        <span>{expanded ? `Hide ${label.toLowerCase()}` : label}</span>
        <ChevronDown
          className={cn(
            'size-3 transition-transform',
            expanded && 'rotate-180',
          )}
        />
      </Button>
    </CollapsibleTrigger>
  );
}

export function RunCodeCard({
  args,
  result,
  status,
}: CatchAllToolCallRenderProps) {
  const [showDetails, setShowDetails] = useState(false);
  const code = (args as { code?: string } | undefined)?.code ?? '';
  const parsedResult =
    status === 'complete' ? normalizeRunCodeResult(result) : {};
  const hasArtifacts = (parsedResult.artifacts?.length ?? 0) > 0;
  const hasStdout = !!parsedResult.stdout?.trim();
  const hasError = !!parsedResult.error;
  const artifactSummary = parsedResult.artifacts?.length
    ? formatArtifactSummary(parsedResult.artifacts)
    : '';
  const summary =
    status === 'executing'
      ? 'Executing analysis'
      : hasError
        ? 'Execution failed'
        : artifactSummary ||
          (hasStdout ? 'Generated text output' : 'No visible output');
  const isCompleted = status === 'complete';
  const canShowDetails = code || hasStdout || hasError;

  return (
    <Collapsible
      className="smart-living-tool-call space-y-2"
      open={showDetails}
      onOpenChange={setShowDetails}
    >
      <ToolCardHeader
        action={
          canShowDetails ? <DetailsToggle expanded={showDetails} /> : undefined
        }
        hasError={hasError}
        isCompleted={isCompleted}
        status={status}
        summary={summary}
        title={formatToolName('run_code')}
      />

      <CollapsibleContent className="data-closed:hidden">
        <div className="space-y-2 rounded-lg border border-border/45 bg-background/35 p-2.5">
          {code ? (
            <pre className="max-h-52 overflow-auto rounded-lg border border-border/55 bg-muted/20 px-3 py-2.5 text-[0.72rem] leading-5 whitespace-pre-wrap text-foreground">
              {code}
            </pre>
          ) : null}
          <RunCodeDetails result={parsedResult} />
        </div>
      </CollapsibleContent>

      {status === 'executing' ? (
        <div className="rounded-lg border border-dashed border-border/60 bg-background/45 px-2.5 py-2 text-[0.7rem] text-muted-foreground">
          Executing code…
        </div>
      ) : null}

      {status === 'complete' && hasArtifacts ? (
        <RunCodeOutput result={parsedResult} />
      ) : null}

      {status === 'complete' && !hasArtifacts && !hasStdout && !hasError ? (
        <p className="px-0.5 text-[0.72rem] text-muted-foreground">
          No visible output.
        </p>
      ) : null}
    </Collapsible>
  );
}

export function GenericToolCallCard({
  args,
  name,
  result,
  status,
}: CatchAllToolCallRenderProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const formattedName = formatToolName(name);
  const hasResult = hasInspectableData(result);
  const hasError = hasErrorResult(result);
  const hasArgs = hasInspectableData(args);
  const canExpand = hasArgs || hasResult;
  const isCompleted = status === 'complete';
  const summary = [
    summarizeValue('inputs', args),
    hasResult
      ? summarizeValue('result', result)
      : status === 'complete'
        ? 'result: none'
        : 'result: pending',
  ].join(' • ');

  return (
    <Collapsible
      className={cn(
        'smart-living-tool-call text-card-foreground',
        isExpanded && 'space-y-2',
      )}
      open={isExpanded}
      onOpenChange={setIsExpanded}
    >
      <ToolCardHeader
        action={
          canExpand ? (
            <DetailsToggle expanded={isExpanded} />
          ) : (
            <span className="text-[0.68rem] text-muted-foreground">
              {hasError ? 'Tool failed.' : TOOL_STATUS_DESCRIPTION[status]}
            </span>
          )
        }
        hasError={hasError}
        isCompleted={isCompleted}
        status={status}
        summary={!isCompleted ? summary : undefined}
        title={formattedName}
      />

      <CollapsibleContent className="data-closed:hidden">
        <div
          className={cn(
            'space-y-2 rounded-lg border border-border/45 bg-background/35 p-2.5',
            !isCompleted && 'mt-2',
          )}
        >
          <ToolPayloadSection title="Inputs" value={args} />
          {hasResult ? (
            <ToolPayloadSection title="Result" value={result} />
          ) : status !== 'complete' ? (
            <div className="rounded-lg border border-dashed border-border/70 bg-background/60 px-3 py-2 text-[0.72rem] text-muted-foreground">
              Waiting for the tool result to stream back.
            </div>
          ) : null}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
