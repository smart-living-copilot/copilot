'use client';

import { useCopilotAction } from '@copilotkit/react-core';
import { CircleAlert, CheckCircle2, ChevronDown, Loader2 } from 'lucide-react';
import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

type ToolCallStatus = 'inProgress' | 'executing' | 'complete';

type CatchAllToolCallRenderProps = {
  args: unknown;
  name: string;
  result: unknown;
  status: ToolCallStatus;
};

type RunCodeArtifact = {
  filename: string;
  kind: 'image' | 'plotly';
  ref: string;
};

type RunCodeResult = {
  artifacts?: RunCodeArtifact[];
  stdout?: string;
  error?: string;
};

const STATUS_DESCRIPTION: Record<ToolCallStatus, string> = {
  inProgress: 'Collecting the tool inputs and preparing the next step.',
  executing: 'Running the tool with the collected inputs.',
  complete: 'Finished and returned structured data to the assistant.',
};

function hasInspectableData(value: unknown) {
  if (value === undefined || value === null) {
    return false;
  }
  if (typeof value === 'string') {
    return value.trim().length > 0;
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (typeof value === 'object') {
    return Object.keys(value as Record<string, unknown>).length > 0;
  }
  return true;
}

function formatToolName(name: string) {
  return name
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatToolData(value: unknown) {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) {
      return '';
    }

    try {
      return JSON.stringify(JSON.parse(trimmed), null, 2);
    } catch {
      return value;
    }
  }

  if (typeof value === 'object') {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }

  return String(value);
}

function summarizeValue(label: string, value: unknown) {
  if (!hasInspectableData(value)) {
    return `${label}: none`;
  }

  if (typeof value === 'string') {
    return `${label}: text`;
  }

  if (Array.isArray(value)) {
    const count = value.length;
    return `${label}: ${count} item${count === 1 ? '' : 's'}`;
  }

  if (typeof value === 'object') {
    const count = Object.keys(value as Record<string, unknown>).length;
    return `${label}: ${count} field${count === 1 ? '' : 's'}`;
  }

  return `${label}: ready`;
}

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
    <div className="overflow-hidden rounded-lg border border-border/60 bg-background/80">
      <div className="border-b border-border/60 px-3 py-2 text-[0.66rem] font-semibold tracking-[0.16em] text-muted-foreground uppercase">
        {title}
      </div>
      <pre className="max-h-60 overflow-auto px-3 py-2.5 text-[0.74rem] leading-5 whitespace-pre-wrap text-foreground">
        {formatToolData(value)}
      </pre>
    </div>
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

function hasErrorResult(value: unknown) {
  if (!value) {
    return false;
  }

  if (typeof value === 'string') {
    return /^error\b/i.test(value.trim());
  }

  if (typeof value === 'object' && !Array.isArray(value)) {
    const error = (value as { error?: unknown }).error;
    return typeof error === 'string' && error.trim().length > 0;
  }

  return false;
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

function formatArtifactSummary(artifacts: RunCodeArtifact[]) {
  const images = artifacts.filter(
    (artifact) => artifact.kind === 'image',
  ).length;
  const charts = artifacts.filter(
    (artifact) => artifact.kind === 'plotly',
  ).length;
  const parts: string[] = [];

  if (charts) {
    parts.push(`${charts} chart${charts === 1 ? '' : 's'}`);
  }

  if (images) {
    parts.push(`${images} image${images === 1 ? '' : 's'}`);
  }

  return parts.join(' • ');
}

function normalizeRunCodeResult(value: unknown): RunCodeResult {
  let rawResult = value;

  if (typeof rawResult === 'string') {
    try {
      rawResult = JSON.parse(rawResult);
    } catch {
      rawResult = { stdout: rawResult };
    }
  }

  if (!rawResult || typeof rawResult !== 'object' || Array.isArray(rawResult)) {
    return {};
  }

  const raw = rawResult as Record<string, unknown>;
  const artifacts: RunCodeArtifact[] = [];

  if (Array.isArray(raw.artifacts)) {
    for (const artifact of raw.artifacts) {
      if (
        !artifact ||
        typeof artifact !== 'object' ||
        Array.isArray(artifact)
      ) {
        continue;
      }

      const candidate = artifact as Record<string, unknown>;
      const ref = typeof candidate.ref === 'string' ? candidate.ref : '';
      const kind =
        candidate.kind === 'image' || candidate.kind === 'plotly'
          ? candidate.kind
          : null;
      const filename =
        typeof candidate.filename === 'string' ? candidate.filename : '';

      if (ref && kind && filename) {
        artifacts.push({ ref, kind, filename });
      }
    }
  }

  if (!artifacts.length) {
    const imageFilenames = Array.isArray(raw.images) ? raw.images : [];
    const plotlyFilenames = Array.isArray(raw.plotly) ? raw.plotly : [];

    for (const [index, filename] of imageFilenames.entries()) {
      if (typeof filename === 'string') {
        artifacts.push({
          ref: `image_${index + 1}`,
          kind: 'image',
          filename,
        });
      }
    }

    for (const [index, filename] of plotlyFilenames.entries()) {
      if (typeof filename === 'string') {
        artifacts.push({
          ref: `chart_${index + 1}`,
          kind: 'plotly',
          filename,
        });
      }
    }
  }

  return {
    artifacts,
    error: typeof raw.error === 'string' ? raw.error : undefined,
    stdout: typeof raw.stdout === 'string' ? raw.stdout : undefined,
  };
}

function RunCodeOutput({ result }: { result: RunCodeResult }) {
  if (!(result.artifacts?.length ?? 0)) {
    return null;
  }

  return (
    <div className="space-y-2">
      {result.artifacts?.map((artifact) => (
        <div
          key={`${artifact.kind}:${artifact.filename}`}
          className="space-y-1.5 rounded-lg border border-border/55 bg-background/45 p-2"
        >
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
        </div>
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
        <pre className="overflow-auto rounded-lg border border-destructive/25 bg-destructive/5 px-3 py-2.5 text-[0.72rem] leading-5 whitespace-pre-wrap text-destructive">
          {result.error}
        </pre>
      ) : null}

      {hasStdout ? (
        <pre className="max-h-52 overflow-auto rounded-lg border border-border/55 bg-background/80 px-3 py-2.5 text-[0.72rem] leading-5 whitespace-pre-wrap text-foreground">
          {result.stdout}
        </pre>
      ) : null}
    </div>
  );
}

function RunCodeCard({ args, result, status }: CatchAllToolCallRenderProps) {
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

  return (
    <div className="smart-living-tool-call space-y-2">
      <div
        className={cn(
          'flex flex-wrap items-center justify-between gap-2 px-1 py-1 text-card-foreground',
          !isCompleted &&
            'rounded-lg border border-border/45 bg-background/45 px-2.5 py-1.5',
        )}
      >
        <div className="flex min-w-0 items-center gap-2.5">
          <ToolStatusIcon hasError={hasError} status={status} />

          <div className="min-w-0 space-y-0.5">
            <div className="flex flex-wrap items-center gap-2">
              <p
                className={cn(
                  'truncate font-medium text-foreground',
                  isCompleted ? 'text-[0.76rem]' : 'text-[0.82rem]',
                )}
              >
                {formatToolName('run_code')}
              </p>
            </div>

            <p className="truncate text-[0.7rem] text-muted-foreground">
              {summary}
            </p>
          </div>
        </div>

        {code || hasStdout || hasError ? (
          <button
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[0.66rem] font-medium text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
            onClick={() => setShowDetails((value) => !value)}
            type="button"
          >
            <span>{showDetails ? 'Hide details' : 'Details'}</span>
            <ChevronDown
              className={cn(
                'size-3 transition-transform',
                showDetails && 'rotate-180',
              )}
            />
          </button>
        ) : null}
      </div>

      {showDetails ? (
        <div className="space-y-2 rounded-lg border border-border/45 bg-background/35 p-2.5">
          {code ? (
            <pre className="max-h-52 overflow-auto rounded-lg border border-border/55 bg-muted/20 px-3 py-2.5 text-[0.72rem] leading-5 whitespace-pre-wrap text-foreground">
              {code}
            </pre>
          ) : null}
          <RunCodeDetails result={parsedResult} />
        </div>
      ) : null}

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
    </div>
  );
}

function GenericToolCallCard({
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
    <div
      className={cn(
        'smart-living-tool-call text-card-foreground',
        isExpanded && 'space-y-2',
      )}
    >
      <div
        className={cn(
          'flex flex-wrap items-center justify-between gap-2 px-1 py-1',
          !isCompleted &&
            'rounded-lg border border-border/45 bg-background/45 px-2.5 py-1.5',
        )}
      >
        <div className="flex min-w-0 items-center gap-2.5">
          <ToolStatusIcon hasError={hasError} status={status} />

          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p
                className={cn(
                  'truncate font-medium text-foreground',
                  isCompleted ? 'text-[0.76rem]' : 'text-[0.82rem]',
                )}
              >
                {formattedName}
              </p>
            </div>

            {!isCompleted ? (
              <p className="truncate font-mono text-[0.66rem] text-muted-foreground">
                {summary}
              </p>
            ) : null}
          </div>
        </div>

        {canExpand ? (
          <button
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[0.66rem] font-medium text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
            onClick={() => setIsExpanded((expanded) => !expanded)}
            type="button"
          >
            <span>{isExpanded ? 'Hide' : 'Details'}</span>
            <ChevronDown
              className={cn(
                'size-3 transition-transform',
                isExpanded && 'rotate-180',
              )}
            />
          </button>
        ) : (
          <span className="text-[0.68rem] text-muted-foreground">
            {hasError ? 'Tool failed.' : STATUS_DESCRIPTION[status]}
          </span>
        )}
      </div>

      {isExpanded ? (
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
      ) : null}
    </div>
  );
}

export function ChatToolCallRenderer() {
  useCopilotAction(
    {
      name: '*',
      render: (props: CatchAllToolCallRenderProps) => {
        if (props.name === 'run_code') {
          return <RunCodeCard {...props} />;
        }

        return <GenericToolCallCard {...props} />;
      },
    },
    [],
  );

  return null;
}
