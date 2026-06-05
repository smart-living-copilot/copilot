import { type RunCodeResult } from '@/components/copilot/chat-tool-call-model';
import { type ReactNode } from 'react';

import {
  CodeOutputPanel,
  TextPanel,
} from '@/components/jobs/details/job-details-panels';
import {
  resourceHealthBadgeVariant,
  resourceHealthLabel,
} from '@/components/jobs/details/job-details-formatters';
import { Badge } from '@/components/ui/badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  formatDateTime,
  getScheduleLabel,
  getStatusBadgeVariant,
  getStatusLabel,
  type JobDisplayStatus,
} from '@/lib/job-formatters';
import { getCodeArtifactSummary } from '@/lib/job-run-output';
import { type JobRecord } from '@/lib/jobs-api';

interface JobDetailsOverviewTabProps {
  job: JobRecord;
  status: JobDisplayStatus | null;
  hasJobThread: boolean;
  hasTimeFields: boolean;
  hasEventFields: boolean;
  latestCodeResult: RunCodeResult | null;
  latestSubmittedRecordSummary: string | null;
}

function SummaryItem({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0 space-y-1">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div
        className={
          mono
            ? 'break-all font-mono text-xs leading-5 text-foreground'
            : 'truncate text-sm font-medium text-foreground'
        }
      >
        {value}
      </div>
    </div>
  );
}

function SummarySection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="space-y-3">
      <h2 className="text-xs font-medium uppercase text-muted-foreground">
        {title}
      </h2>
      <div className="grid gap-x-5 gap-y-3 sm:grid-cols-2">{children}</div>
    </section>
  );
}

export function JobDetailsOverviewTab({
  job,
  status,
  hasJobThread,
  hasTimeFields,
  hasEventFields,
  latestCodeResult,
  latestSubmittedRecordSummary,
}: JobDetailsOverviewTabProps) {
  const actionLabel =
    job.output_kind === 'structured_record'
      ? 'Record prompt'
      : getStatusLabel(job.action_kind);

  return (
    <>
      <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
        <CardHeader className="border-b border-border/70">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <CardTitle className="text-base">Overview</CardTitle>
              <CardDescription>
                Current state, trigger, resources, and recent run metadata.
              </CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              {status ? (
                <Badge variant={getStatusBadgeVariant(status)}>
                  {getStatusLabel(status)}
                </Badge>
              ) : null}
              <Badge variant="outline">{actionLabel}</Badge>
              <Badge variant="outline">
                {getStatusLabel(job.trigger_kind)}
              </Badge>
              <Badge
                variant={resourceHealthBadgeVariant(
                  job.resource_health?.status,
                )}
              >
                {resourceHealthLabel(job.resource_health?.status)}
              </Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent className="grid gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(18rem,0.85fr)]">
          <div className="space-y-5">
            <SummarySection title="Trigger">
              <SummaryItem label="Schedule" value={getScheduleLabel(job)} />
              {hasTimeFields ? (
                <>
                  <SummaryItem
                    label="Next run"
                    value={formatDateTime(job.next_run_at)}
                  />
                  <SummaryItem
                    label="Schedule kind"
                    value={job.schedule_kind || 'Time trigger'}
                  />
                  {job.interval_seconds ? (
                    <SummaryItem
                      label="Interval"
                      value={`${job.interval_seconds}s`}
                    />
                  ) : null}
                  {job.cron_expression ? (
                    <SummaryItem
                      label="Cron"
                      value={job.cron_expression}
                      mono
                    />
                  ) : null}
                  {job.cron_timezone ? (
                    <SummaryItem label="Timezone" value={job.cron_timezone} />
                  ) : null}
                  {job.run_at ? (
                    <SummaryItem
                      label="Run once at"
                      value={formatDateTime(job.run_at)}
                    />
                  ) : null}
                </>
              ) : null}
              {hasEventFields ? (
                <>
                  <SummaryItem
                    label="Thing"
                    value={job.thing_id || 'Unbound'}
                    mono
                  />
                  <SummaryItem
                    label="Event"
                    value={job.event_name || 'Unbound'}
                  />
                  {job.subscription_id ? (
                    <SummaryItem
                      label="Subscription"
                      value={job.subscription_id}
                      mono
                    />
                  ) : null}
                </>
              ) : null}
            </SummarySection>

            <SummarySection title="Binding">
              {hasJobThread ? (
                <SummaryItem
                  label="Job thread"
                  value={job.job_thread_id}
                  mono
                />
              ) : null}
              {job.virtual_thing_id ? (
                <SummaryItem
                  label="Virtual thing"
                  value={job.virtual_thing_id}
                  mono
                />
              ) : null}
              {job.output_kind === 'structured_record' ? (
                <SummaryItem
                  label="Schema version"
                  value={job.record_schema_version || 'Unversioned'}
                />
              ) : null}
              {!hasJobThread &&
              !job.virtual_thing_id &&
              job.output_kind !== 'structured_record' ? (
                <SummaryItem label="Linked resources" value="None" />
              ) : null}
            </SummarySection>
          </div>

          <div className="space-y-5 border-t border-border/70 pt-5 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0">
            <SummarySection title="Runs">
              <SummaryItem
                label="Last run"
                value={
                  job.last_run_status
                    ? getStatusLabel(job.last_run_status)
                    : 'No runs'
                }
              />
              <SummaryItem
                label="Last run at"
                value={formatDateTime(job.last_run_at)}
              />
              <SummaryItem label="Run count" value={job.run_count} />
              <SummaryItem
                label="Active run"
                value={job.active_run_id || 'None'}
                mono
              />
              <SummaryItem
                label="Updated"
                value={formatDateTime(job.updated_at)}
              />
            </SummarySection>
          </div>
        </CardContent>
      </Card>

      {job.action_kind === 'analysis' ? (
        <CodeOutputPanel
          result={latestCodeResult ?? {}}
          title="Latest output"
          readText={
            latestCodeResult?.stdout?.trim() || latestCodeResult?.error?.trim()
          }
        />
      ) : (
        <>
          <TextPanel
            title={
              job.output_kind === 'structured_record'
                ? 'Latest record'
                : 'Last result'
            }
            description={
              job.output_kind === 'structured_record'
                ? 'The latest structured record captured from an execution.'
                : 'The latest response captured from an execution.'
            }
            value={
              latestSubmittedRecordSummary ||
              job.last_response ||
              'No result captured yet.'
            }
            readText={
              latestSubmittedRecordSummary || job.last_response || undefined
            }
          />
          {latestCodeResult?.artifacts?.length ? (
            <CodeOutputPanel
              result={latestCodeResult}
              title="Generated artifacts"
              readText={
                latestCodeResult.stdout?.trim() ||
                getCodeArtifactSummary(latestCodeResult)
              }
            />
          ) : null}
        </>
      )}
    </>
  );
}
