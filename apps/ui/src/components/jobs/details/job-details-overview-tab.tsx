import { type RunCodeResult } from '@/components/copilot/chat-tool-call-model';
import {
  CodeOutputPanel,
  FieldCard,
  TextPanel,
} from '@/components/jobs/details/job-details-panels';
import {
  resourceHealthBadgeVariant,
  resourceHealthLabel,
} from '@/components/jobs/details/job-details-formatters';
import { Badge } from '@/components/ui/badge';
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

export function JobDetailsOverviewTab({
  job,
  status,
  hasJobThread,
  hasTimeFields,
  hasEventFields,
  latestCodeResult,
  latestSubmittedRecordSummary,
}: JobDetailsOverviewTabProps) {
  return (
    <>
      <section className="grid gap-2 sm:grid-cols-2 xl:flex xl:flex-nowrap">
        <FieldCard
          label="Status"
          value={
            status ? (
              <Badge variant={getStatusBadgeVariant(status)}>
                {getStatusLabel(status)}
              </Badge>
            ) : (
              'unknown'
            )
          }
        />
        <FieldCard
          label="Action"
          value={
            job.output_kind === 'structured_record'
              ? 'Record prompt'
              : getStatusLabel(job.action_kind)
          }
        />
        <FieldCard label="Trigger" value={getStatusLabel(job.trigger_kind)} />
        {hasTimeFields ? (
          <>
            <FieldCard label="Schedule" value={getScheduleLabel(job)} />
            <FieldCard
              label="Next run"
              value={formatDateTime(job.next_run_at)}
            />
          </>
        ) : null}
        {hasEventFields ? (
          <>
            <FieldCard label="Thing" value={job.thing_id || 'Unbound'} mono />
            <FieldCard label="Event" value={job.event_name || 'Unbound'} />
          </>
        ) : null}
        <FieldCard label="Last run" value={job.last_run_status || 'No runs'} />
        <FieldCard
          label="Resources"
          value={
            <Badge
              variant={resourceHealthBadgeVariant(job.resource_health?.status)}
            >
              {resourceHealthLabel(job.resource_health?.status)}
            </Badge>
          }
        />
        {job.virtual_thing_id ? (
          <FieldCard label="Virtual thing" value={job.virtual_thing_id} mono />
        ) : null}
        {job.output_kind === 'structured_record' ? (
          <FieldCard
            label="Schema version"
            value={job.record_schema_version || 'Unversioned'}
          />
        ) : null}
      </section>

      <section className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {hasJobThread ? (
          <FieldCard label="Job thread" value={job.job_thread_id} mono />
        ) : null}
        {hasTimeFields ? (
          <>
            <FieldCard
              label="Schedule kind"
              value={job.schedule_kind || 'Time trigger'}
            />
            {job.interval_seconds ? (
              <FieldCard label="Interval" value={`${job.interval_seconds}s`} />
            ) : null}
            {job.cron_expression ? (
              <FieldCard label="Cron" value={job.cron_expression} mono />
            ) : null}
            {job.cron_timezone ? (
              <FieldCard label="Timezone" value={job.cron_timezone} />
            ) : null}
            {job.run_at ? (
              <FieldCard
                label="Run once at"
                value={formatDateTime(job.run_at)}
              />
            ) : null}
          </>
        ) : null}
        {hasEventFields && job.subscription_id ? (
          <FieldCard label="Subscription" value={job.subscription_id} mono />
        ) : null}
        <FieldCard
          label="Active run"
          value={job.active_run_id || 'None'}
          mono
        />
        <FieldCard label="Run count" value={job.run_count} />
        <FieldCard
          label="Last run at"
          value={formatDateTime(job.last_run_at)}
        />
        <FieldCard label="Updated" value={formatDateTime(job.updated_at)} />
      </section>

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
