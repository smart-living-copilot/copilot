'use client';

import { useCallback, useEffect, useState } from 'react';
import { Info, RefreshCw, TriangleAlert } from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { APP_VERSION } from '@/lib/app-version';
import {
  findConfigMismatches,
  formatConfigValue,
  type ConfigMismatch,
  type ConfigReport,
} from '@/lib/config-report';
import { httpJson } from '@/lib/http-client';
import type { ReasoningEffortConfig } from '@/lib/reasoning-effort';

interface SystemInfoResponse {
  backend: ConfigReport;
  ui: { reasoningEffort: ReasoningEffortConfig };
}

function MismatchWarning({ mismatches }: { mismatches: ConfigMismatch[] }) {
  return (
    <Alert variant="destructive">
      <TriangleAlert className="size-4" />
      <AlertTitle>UI and backend disagree</AlertTitle>
      <AlertDescription>
        <p>
          These settings are read separately by each container, so one can be
          redeployed without the other. The agent follows the backend value.
        </p>
        <ul className="mt-2 space-y-1">
          {mismatches.map((mismatch) => (
            <li key={mismatch.setting} className="font-mono text-xs">
              {mismatch.setting}: UI has {mismatch.uiValue}, backend has{' '}
              {mismatch.backendValue}
            </li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}

export function SystemInfoPanel() {
  const [data, setData] = useState<SystemInfoResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await httpJson<SystemInfoResponse>('/config'));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const mismatches = data
    ? findConfigMismatches(data.backend, data.ui.reasoningEffort)
    : [];

  return (
    <div className="space-y-6">
      <section className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Info className="size-5 text-muted-foreground" />
              <h3 className="text-lg font-medium">System info</h3>
            </div>
            <p className="text-sm text-muted-foreground">
              The configuration this deployment actually resolved at startup.
              Read-only: every value comes from the environment and changes on
              restart. Secrets are shown as set or not set, never by value.
            </p>
          </div>
          <Button
            disabled={loading}
            onClick={() => void load()}
            variant="outline"
          >
            <RefreshCw className={loading ? 'animate-spin' : undefined} />
            Refresh
          </Button>
        </div>

        <Separator />

        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <span className="text-muted-foreground">
            UI build{' '}
            <span className="font-mono text-foreground">{APP_VERSION}</span>
          </span>
          <span className="text-muted-foreground">
            Backend{' '}
            <span className="font-mono text-foreground">
              {data?.backend.version ?? 'unknown'}
            </span>
          </span>
        </div>
      </section>

      {error ? (
        <Alert variant="destructive">
          <TriangleAlert className="size-4" />
          <AlertTitle>Could not load configuration</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {mismatches.length > 0 ? (
        <MismatchWarning mismatches={mismatches} />
      ) : null}

      {loading && !data ? (
        <p className="text-sm text-muted-foreground">Loading configuration...</p>
      ) : null}

      {data?.backend.sections.map((section) => (
        <Card key={section.key}>
          <CardHeader>
            <CardTitle className="text-base">{section.title}</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="divide-y divide-border">
              {section.fields.map((field) => (
                <div
                  key={field.name}
                  className="flex flex-col gap-1 py-2 sm:flex-row sm:items-baseline sm:gap-4"
                >
                  <dt className="min-w-0 font-mono text-xs break-all text-muted-foreground sm:w-80 sm:shrink-0">
                    {field.name}
                  </dt>
                  <dd className="flex min-w-0 flex-1 flex-wrap items-baseline gap-2">
                    <span className="min-w-0 font-mono text-xs break-all">
                      {formatConfigValue(field)}
                    </span>
                    {field.is_default ? (
                      <Badge variant="secondary">default</Badge>
                    ) : null}
                    {field.note ? (
                      <span className="text-xs text-muted-foreground">
                        {field.note}
                      </span>
                    ) : null}
                  </dd>
                </div>
              ))}
            </dl>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
