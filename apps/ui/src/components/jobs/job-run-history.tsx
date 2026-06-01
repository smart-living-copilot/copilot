import { Badge } from '@/components/ui/badge';
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
}

export function JobRunHistoryCard({
  runs,
  description,
  outcome,
  showFinished = false,
  minWidthClassName = 'min-w-[760px]',
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
                {runs.map((run) => (
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
                      <p className="line-clamp-3 whitespace-pre-wrap break-words">
                        {outcome(run)}
                      </p>
                    </TableCell>
                  </TableRow>
                ))}
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
