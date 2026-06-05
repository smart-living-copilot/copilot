import { ChevronLeft, ChevronRight } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ReadAloudButton } from '@/components/jobs/job-speech-controls';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  formatDateTime,
  getStatusBadgeVariant,
  getStatusLabel,
} from '@/lib/job-formatters';
import { type JobRunRecord } from '@/lib/jobs-api';

export function RunStatusBadge({ status }: { status: string }) {
  return (
    <Badge variant={getStatusBadgeVariant(status)}>
      {getStatusLabel(status)}
    </Badge>
  );
}

interface JobRunHistoryCardProps {
  runs: JobRunRecord[];
  totalRuns?: number;
  limit?: number;
  offset?: number;
  description: string;
  outcome: (run: JobRunRecord) => string;
  onPageChange?: (offset: number) => void;
  showFinished?: boolean;
  minWidthClassName?: string;
  readOutcome?: boolean;
}

export function JobRunHistoryCard({
  runs,
  totalRuns,
  limit,
  offset = 0,
  description,
  outcome,
  onPageChange,
  showFinished = false,
  minWidthClassName = 'min-w-[760px]',
  readOutcome = false,
}: JobRunHistoryCardProps) {
  const total = totalRuns ?? runs.length;
  const pageSize = limit ?? Math.max(runs.length, 1);
  const firstVisibleRun = runs.length ? offset + 1 : 0;
  const lastVisibleRun = runs.length
    ? Math.min(offset + runs.length, total)
    : 0;
  const canGoBack = offset > 0;
  const canGoForward = lastVisibleRun < total;
  const showPagination =
    Boolean(onPageChange) && (total > pageSize || offset > 0);

  return (
    <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
      <CardHeader className="border-b border-border/70">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle className="text-base">Run history</CardTitle>
            <CardDescription>{description}</CardDescription>
          </div>
          <Badge variant="outline">{total}</Badge>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {runs.length ? (
          <div className="overflow-x-auto">
            <Table className={minWidthClassName}>
              <TableHeader>
                <TableRow>
                  <TableHead>Status</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Started</TableHead>
                  {showFinished ? <TableHead>Finished</TableHead> : null}
                  <TableHead>Outcome</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((run) => {
                  const outcomeText = outcome(run);
                  return (
                    <TableRow key={run.id}>
                      <TableCell className="align-top">
                        <RunStatusBadge status={run.status} />
                      </TableCell>
                      <TableCell className="align-top capitalize">
                        {run.source}
                      </TableCell>
                      <TableCell className="align-top text-xs text-muted-foreground">
                        {formatDateTime(run.started_at)}
                      </TableCell>
                      {showFinished ? (
                        <TableCell className="align-top text-xs text-muted-foreground">
                          {formatDateTime(run.finished_at)}
                        </TableCell>
                      ) : null}
                      <TableCell className="align-top text-sm text-muted-foreground">
                        <div className="flex items-start gap-2">
                          <p className="line-clamp-3 flex-1 whitespace-pre-wrap break-words">
                            {outcomeText}
                          </p>
                          {readOutcome ? (
                            <ReadAloudButton text={outcomeText} compact />
                          ) : null}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        ) : (
          <div className="p-4 text-sm text-muted-foreground">
            {total ? 'No runs on this page.' : 'No runs recorded yet.'}
          </div>
        )}
        {showPagination ? (
          <div className="flex flex-col gap-3 border-t border-border/70 px-4 py-3 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
            <span>
              Showing {firstVisibleRun}-{lastVisibleRun} of {total}
            </span>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!canGoBack}
                onClick={() => onPageChange?.(Math.max(0, offset - pageSize))}
              >
                <ChevronLeft className="h-4 w-4" />
                Previous
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!canGoForward}
                onClick={() => onPageChange?.(offset + pageSize)}
              >
                Next
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
