import { useState, type ReactNode } from 'react';
import Link from 'next/link';
import {
  Ban,
  Eye,
  MessagesSquare,
  MoreHorizontal,
  Pause,
  Pencil,
  Play,
  Power,
  Trash2,
} from 'lucide-react';

import { ConfirmDialog } from '@/components/confirm-dialog';
import { hasActiveRun } from '@/components/jobs/list/job-list-formatters';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Spinner } from '@/components/ui/spinner';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { supportsJobReply } from '@/lib/job-formatters';
import { type JobRecord } from '@/lib/jobs-api';
import { withReturnTo } from '@/lib/return-to';

interface IconActionProps {
  label: string;
  disabled?: boolean;
  children: ReactNode;
  onClick?: () => void;
  href?: string;
  destructive?: boolean;
}

function IconAction({
  label,
  disabled,
  children,
  onClick,
  href,
  destructive,
}: IconActionProps) {
  const button = (
    <Button
      aria-label={label}
      title={label}
      size="icon-sm"
      variant={destructive ? 'destructive' : 'outline'}
      disabled={disabled}
      onClick={onClick}
      asChild={Boolean(href)}
    >
      {href ? <Link href={href}>{children}</Link> : children}
    </Button>
  );

  return (
    <Tooltip>
      <TooltipTrigger asChild>{button}</TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

interface JobRowActionsProps {
  job: JobRecord;
  busy: boolean;
  running: boolean;
  onRun: () => void;
  onToggleEnabled: () => void;
  onCancel: () => void;
  onDelete: () => void;
  onOpenDetails: () => void;
}

export function JobRowActions({
  job,
  busy,
  running,
  onRun,
  onToggleEnabled,
  onCancel,
  onDelete,
  onOpenDetails,
}: JobRowActionsProps) {
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const editHref = withReturnTo(`/jobs/${job.id}/edit`, '/jobs');

  return (
    <div className="flex justify-end gap-1.5">
      <ConfirmDialog
        open={confirmDeleteOpen}
        onOpenChange={setConfirmDeleteOpen}
        title={`Delete "${job.name}"?`}
        description="This permanently removes the job, its schedule, and its run history. This cannot be undone."
        confirmLabel="Delete"
        destructive
        onConfirm={onDelete}
      />
      <IconAction label="Run now" disabled={busy} onClick={onRun}>
        {running ? (
          <Spinner className="size-3.5" />
        ) : (
          <Play className="h-3.5 w-3.5" />
        )}
      </IconAction>
      <IconAction
        label={job.enabled ? 'Pause' : 'Resume'}
        disabled={busy}
        onClick={onToggleEnabled}
      >
        {job.enabled ? (
          <Pause className="h-3.5 w-3.5" />
        ) : (
          <Power className="h-3.5 w-3.5" />
        )}
      </IconAction>
      <DropdownMenu>
        <Tooltip>
          <TooltipTrigger asChild>
            <DropdownMenuTrigger asChild>
              <Button
                aria-label="More actions"
                size="icon-sm"
                variant="outline"
                disabled={busy}
              >
                <MoreHorizontal className="h-3.5 w-3.5" />
              </Button>
            </DropdownMenuTrigger>
          </TooltipTrigger>
          <TooltipContent>More actions</TooltipContent>
        </Tooltip>
        <DropdownMenuContent align="end">
          {supportsJobReply(job) ? (
            <DropdownMenuItem onSelect={onOpenDetails}>
              <MessagesSquare className="h-4 w-4" />
              Answer question
            </DropdownMenuItem>
          ) : null}
          <DropdownMenuItem onSelect={onOpenDetails}>
            <Eye className="h-4 w-4" />
            View details
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <Link href={editHref}>
              <Pencil className="h-4 w-4" />
              Edit
            </Link>
          </DropdownMenuItem>
          {hasActiveRun(job) ? (
            <DropdownMenuItem onSelect={() => onCancel()}>
              <Ban className="h-4 w-4" />
              Cancel run
            </DropdownMenuItem>
          ) : null}
          <DropdownMenuSeparator />
          <DropdownMenuItem
            variant="destructive"
            onSelect={(event) => {
              event.preventDefault();
              setConfirmDeleteOpen(true);
            }}
          >
            <Trash2 className="h-4 w-4" />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
