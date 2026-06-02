import { Badge } from '@/components/ui/badge';
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
  description: string;
  outcome: (run: JobRunRecord) => string;
  showFinished?: boolean;
  minWidthClassName?: string;
  readOutcome?: boolean;
}

export function JobRunHistoryCard({
  runs,
  description,
  outcome,
  showFinished = false,
  minWidthClassName = 'min-w-[760px]',
  readOutcome = false,
}: JobRunHistoryCardProps) {
  return (
    <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
      <CardHeader className="border-b border-border/70">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle className="text-base">Run history</CardTitle>
            <CardDescription>{description}</CardDescription>
          </div>
          <Badge variant="outline">{runs.length}</Badge>
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
            No runs recorded yet.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
