'use client';

import { JobConversationPanel } from '@/components/jobs/job-conversation-panel';
import { JobDetailsHeader } from '@/components/jobs/details/job-details-header';
import { JobDetailsOverviewTab } from '@/components/jobs/details/job-details-overview-tab';
import {
  JobReplyPanel,
  TextPanel,
} from '@/components/jobs/details/job-details-panels';
import { PulseDot } from '@/components/jobs/details/pulse-dot';
import { useJobDetails } from '@/components/jobs/details/use-job-details';
import { JobRunHistoryCard } from '@/components/jobs/job-run-history';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { formatJsonValue, formatJobRunOutcome } from '@/lib/job-run-output';

interface JobDetailsPageProps {
  jobId: string;
  onDeleted?: (jobId: string) => void;
  /** When set (drawer context), shows an "Open" button linking to the page. */
  openHref?: string;
}

const JOB_TABS_TRIGGER_CLASSNAME =
  'flex-none rounded-none border-b-2 border-transparent px-4 py-2.5 font-medium text-muted-foreground data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none data-active:border-primary data-active:bg-transparent data-active:text-foreground data-active:shadow-none';

export function JobDetailsPage({
  jobId,
  onDeleted,
  openHref,
}: JobDetailsPageProps) {
  const {
    job,
    runs,
    runPage,
    isLoading,
    isRunning,
    isReplying,
    isDeleting,
    isBusy,
    replyText,
    setReplyText,
    loadError,
    status,
    purpose,
    hasJobThread,
    isWaitingForReply,
    hasTimeFields,
    hasEventFields,
    showSchemaTab,
    latestCodeResult,
    degradedResourceMessages,
    latestSubmittedRecordSummary,
    load,
    handleRun,
    handleRunPageChange,
    handleReply,
    handleToggleEnabled,
    handleCancel,
    handleDelete,
  } = useJobDetails(jobId, { onDeleted });

  return (
    <div className="space-y-5">
      <JobDetailsHeader
        jobId={jobId}
        job={job}
        openHref={openHref}
        status={status}
        isLoading={isLoading}
        isRunning={isRunning}
        isDeleting={isDeleting}
        isBusy={isBusy}
        onRefresh={() => void load()}
        onRun={() => void handleRun()}
        onCancel={() => void handleCancel()}
        onToggleEnabled={() => void handleToggleEnabled()}
        onDelete={handleDelete}
      />

      {isLoading && !job ? (
        <div className="space-y-4">
          <section className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            {['status', 'action', 'trigger', 'last-run'].map((key) => (
              <Skeleton key={key} className="h-[68px] rounded-md" />
            ))}
          </section>
          <Skeleton className="h-72 rounded-md" />
        </div>
      ) : null}

      {loadError && !job ? (
        <Alert variant="destructive">
          <AlertTitle>Unable to load job</AlertTitle>
          <AlertDescription>{loadError}</AlertDescription>
        </Alert>
      ) : null}

      {job ? (
        <>
          {isWaitingForReply ? (
            <JobReplyPanel
              question={
                job.waiting_question || 'The job is waiting for a reply.'
              }
              value={replyText}
              isSubmitting={isReplying}
              onChange={setReplyText}
              onSubmit={handleReply}
            />
          ) : null}

          {job.last_error ? (
            <Alert variant="destructive">
              <AlertTitle>Last error</AlertTitle>
              <AlertDescription>{job.last_error}</AlertDescription>
            </Alert>
          ) : null}

          {job.resource_health?.status === 'degraded' ? (
            <Alert variant="destructive">
              <AlertTitle>Resource health degraded</AlertTitle>
              <AlertDescription>
                {degradedResourceMessages.length ? (
                  <div className="space-y-1">
                    {degradedResourceMessages.map((resource) => (
                      <div key={resource.name}>
                        <span className="font-medium">{resource.name}:</span>{' '}
                        {resource.message}
                      </div>
                    ))}
                  </div>
                ) : (
                  job.resource_health.last_error ||
                  'One or more job resources need attention.'
                )}
              </AlertDescription>
            </Alert>
          ) : null}

          <JobDetailsOverviewTab
            job={job}
            status={status}
            hasJobThread={hasJobThread}
            hasTimeFields={hasTimeFields}
            hasEventFields={hasEventFields}
            latestCodeResult={latestCodeResult}
            latestSubmittedRecordSummary={latestSubmittedRecordSummary}
          />

          <Tabs defaultValue="runs" className="space-y-5">
            <div className="overflow-x-auto">
              <TabsList
                variant="line"
                className="h-auto min-w-max gap-0 rounded-none border-b border-border/80 bg-transparent p-0"
              >
                <TabsTrigger
                  value="runs"
                  className={JOB_TABS_TRIGGER_CLASSNAME}
                >
                  Runs ({runPage.total})
                </TabsTrigger>
                <TabsTrigger
                  value="definition"
                  className={JOB_TABS_TRIGGER_CLASSNAME}
                >
                  {job.action.kind === 'analysis' ? 'Code' : 'Prompt'}
                </TabsTrigger>
                {showSchemaTab ? (
                  <TabsTrigger
                    value="schema"
                    className={JOB_TABS_TRIGGER_CLASSNAME}
                  >
                    {job.output.kind === 'structured_record'
                      ? 'Schema'
                      : 'Subscription'}
                  </TabsTrigger>
                ) : null}
                {hasJobThread ? (
                  <TabsTrigger
                    value="conversation"
                    className={JOB_TABS_TRIGGER_CLASSNAME}
                  >
                    Conversation
                    {isWaitingForReply ? <PulseDot className="ml-1.5" /> : null}
                  </TabsTrigger>
                ) : null}
              </TabsList>
            </div>

            <TabsContent value="runs" className="mt-0">
              <JobRunHistoryCard
                runs={runs}
                totalRuns={runPage.total}
                limit={runPage.limit}
                offset={runPage.offset}
                description="Recent starts, completion times, and captured outcomes."
                outcome={formatJobRunOutcome}
                onPageChange={handleRunPageChange}
                showFinished
                minWidthClassName="min-w-[860px]"
              />
            </TabsContent>

            <TabsContent value="definition" className="mt-0">
              <TextPanel
                title={purpose.label}
                description="The action payload used when this job runs."
                value={purpose.content}
              />
            </TabsContent>

            {showSchemaTab ? (
              <TabsContent value="schema" className="mt-0 space-y-4">
                {job.output.kind === 'structured_record' ? (
                  <TextPanel
                    title="Record schema"
                    description="JSON Schema used to parse and validate submitted records."
                    value={formatJsonValue(job.output.schema)}
                    compact
                  />
                ) : null}

                {hasEventFields ? (
                  <TextPanel
                    title="Subscription input"
                    description="Stored event subscription payload for event-triggered jobs."
                    value={formatJsonValue(
                      job.trigger.kind === 'event'
                        ? job.trigger.subscription_input
                        : null,
                    )}
                    compact
                  />
                ) : null}
              </TabsContent>
            ) : null}

            {hasJobThread ? (
              <TabsContent value="conversation" className="mt-0">
                <JobConversationPanel jobId={jobId} job={job} />
              </TabsContent>
            ) : null}
          </Tabs>
        </>
      ) : null}
    </div>
  );
}
