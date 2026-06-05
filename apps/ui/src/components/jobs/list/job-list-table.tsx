import {
  actionLabel,
  renderRelative,
  targetLabel,
  triggerLabel,
  type JobTabValue,
} from '@/components/jobs/list/job-list-formatters';
import { JobRowActions } from '@/components/jobs/list/job-row-actions';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  getJobStatus,
  getStatusBadgeVariant,
  getStatusLabel,
  supportsTimeFields,
} from '@/lib/job-formatters';
import { type JobRecord } from '@/lib/jobs-api';

interface JobListTableProps {
  activeTab: JobTabValue;
  activeTabLabel: string;
  busyJobId: string | null;
  deferredSearch: string;
  isHydrated: boolean;
  isPending: boolean;
  jobs: JobRecord[];
  now: Date;
  runningJobId: string | null;
  onCancel: (jobId: string) => void;
  onClearSearch: () => void;
  onDelete: (job: JobRecord) => void;
  onOpenDetails: (jobId: string) => void;
  onRun: (jobId: string) => void;
  onShowAll: () => void;
  onToggleEnabled: (job: JobRecord) => void;
}

export function JobListTable({
  activeTab,
  activeTabLabel,
  busyJobId,
  deferredSearch,
  isHydrated,
  isPending,
  jobs,
  now,
  runningJobId,
  onCancel,
  onClearSearch,
  onDelete,
  onOpenDetails,
  onRun,
  onShowAll,
  onToggleEnabled,
}: JobListTableProps) {
  if (isPending) {
    return (
      <div className="space-y-2 rounded-md border p-3">
        {['r1', 'r2', 'r3', 'r4', 'r5'].map((key) => (
          <Skeleton key={key} className="h-12 w-full rounded-md" />
        ))}
      </div>
    );
  }

  if (jobs.length === 0) {
    return (
      <EmptyJobList
        activeTab={activeTab}
        activeTabLabel={activeTabLabel}
        deferredSearch={deferredSearch}
        onClearSearch={onClearSearch}
        onShowAll={onShowAll}
      />
    );
  }

  return (
    <div className="overflow-x-auto rounded-md border">
      <Table className="min-w-[920px] table-fixed">
        <TableHeader>
          <TableRow>
            <TableHead className="w-[34%]">Job</TableHead>
            <TableHead className="w-[17%]">State</TableHead>
            <TableHead className="w-[22%]">Trigger</TableHead>
            <TableHead className="w-[15%]">Last run</TableHead>
            <TableHead className="w-[12%] text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {jobs.map((job) => {
            const status = getJobStatus(job, now);
            const busy = busyJobId === job.id;

            return (
              <TableRow key={job.id}>
                <TableCell className="align-middle">
                  <div className="min-w-0 space-y-1.5">
                    <button
                      className="block max-w-full truncate font-medium transition-colors hover:text-primary"
                      onClick={() => onOpenDetails(job.id)}
                      type="button"
                    >
                      {job.name}
                    </button>
                    <div className="flex flex-wrap gap-1.5">
                      <Badge variant="outline">{actionLabel(job)}</Badge>
                    </div>
                  </div>
                </TableCell>
                <TableCell className="align-middle">
                  <div className="flex flex-wrap gap-1.5">
                    <Badge variant={getStatusBadgeVariant(status)}>
                      {getStatusLabel(status)}
                    </Badge>
                    {job.last_error && status !== 'failed' ? (
                      <Badge variant="destructive">Error</Badge>
                    ) : null}
                  </div>
                </TableCell>
                <TableCell className="align-middle">
                  <div className="space-y-1 text-sm">
                    <div className="font-medium">{triggerLabel(job)}</div>
                    <div className="line-clamp-1 text-muted-foreground">
                      {targetLabel(job)}
                    </div>
                    {supportsTimeFields(job) && job.next_run_at ? (
                      <div className="text-xs text-muted-foreground">
                        Next {renderRelative(job.next_run_at, isHydrated, now)}
                      </div>
                    ) : null}
                  </div>
                </TableCell>
                <TableCell className="align-middle text-sm">
                  <div className="space-y-1">
                    <div>
                      {job.last_run_status
                        ? getStatusLabel(job.last_run_status)
                        : 'No runs'}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {renderRelative(job.last_run_at, isHydrated, now)}
                    </div>
                  </div>
                </TableCell>
                <TableCell className="align-middle">
                  <JobRowActions
                    job={job}
                    busy={busy}
                    running={runningJobId === job.id}
                    onRun={() => onRun(job.id)}
                    onToggleEnabled={() => onToggleEnabled(job)}
                    onCancel={() => onCancel(job.id)}
                    onDelete={() => onDelete(job)}
                    onOpenDetails={() => onOpenDetails(job.id)}
                  />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

function EmptyJobList({
  activeTab,
  activeTabLabel,
  deferredSearch,
  onClearSearch,
  onShowAll,
}: {
  activeTab: JobTabValue;
  activeTabLabel: string;
  deferredSearch: string;
  onClearSearch: () => void;
  onShowAll: () => void;
}) {
  const hasSearch = Boolean(deferredSearch.trim());

  return (
    <div className="rounded-md border border-dashed px-6 py-12 text-center">
      <h2 className="text-xl font-semibold tracking-tight">No jobs found</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
        {hasSearch
          ? `No jobs match "${deferredSearch.trim()}".`
          : activeTab !== 'all'
            ? `No jobs are currently in ${activeTabLabel.toLowerCase()}.`
            : 'No automation jobs have been created yet.'}
      </p>
      {hasSearch || activeTab !== 'all' ? (
        <div className="mt-5 flex flex-wrap justify-center gap-2">
          {hasSearch ? (
            <Button variant="outline" onClick={onClearSearch}>
              Clear search
            </Button>
          ) : null}
          {activeTab !== 'all' ? (
            <Button variant="outline" onClick={onShowAll}>
              Show all
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
