'use client';

import { Loader2, RefreshCw } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  type ThingRefreshPreview,
  applyThingRefresh,
  previewThingRefresh,
} from '@/lib/sources-api';

function ActionList({ label, values }: { label: string; values: string[] }) {
  if (!values.length) return null;
  return (
    <div className="space-y-1">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="break-words text-sm">{values.join(', ')}</p>
    </div>
  );
}

export function ThingRefreshDialog({
  thingId,
  onRefreshed,
}: {
  thingId: string;
  onRefreshed: () => Promise<void> | void;
}) {
  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState<ThingRefreshPreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [applying, setApplying] = useState(false);

  async function handlePreview() {
    setPreviewing(true);
    try {
      const result = await previewThingRefresh(thingId);
      setPreview(result);
      setOpen(true);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Could not prepare refresh',
      );
    } finally {
      setPreviewing(false);
    }
  }

  async function handleApply() {
    if (!preview) return;
    setApplying(true);
    try {
      await applyThingRefresh(thingId, preview.refresh_id);
      await onRefreshed();
      setOpen(false);
      setPreview(null);
      toast.success('Thing regenerated from its source');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Refresh failed');
    } finally {
      setApplying(false);
    }
  }

  const diff = preview?.diff;
  const noActionChanges =
    diff &&
    !diff.added_actions.length &&
    !diff.removed_actions.length &&
    !diff.changed_actions.length;

  return (
    <>
      <Button variant="outline" disabled={previewing} onClick={handlePreview}>
        {previewing ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <RefreshCw className="h-4 w-4" />
        )}
        Regenerate from source
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Regenerate from source?</DialogTitle>
            <DialogDescription>
              Review the prepared OpenAPI changes. Local title, description, and
              manually added affordances are preserved.
            </DialogDescription>
          </DialogHeader>
          {diff ? (
            <div className="max-h-80 space-y-4 overflow-y-auto">
              <ActionList label="Added actions" values={diff.added_actions} />
              <ActionList
                label="Removed actions"
                values={diff.removed_actions}
              />
              <ActionList
                label="Changed actions"
                values={diff.changed_actions}
              />
              {noActionChanges ? (
                <p className="text-sm text-muted-foreground">
                  No generated action changes.
                </p>
              ) : null}
              {diff.server_changed ? (
                <p className="text-sm">The selected API server changed.</p>
              ) : null}
              {diff.security_changed ? (
                <p className="text-sm">
                  API security changed. Affected stored credentials will be
                  removed.
                </p>
              ) : null}
              {preview?.warnings.length ? (
                <div className="rounded-md border border-yellow-500/40 bg-yellow-500/5 p-3">
                  <p className="mb-1 text-xs font-medium uppercase tracking-wide">
                    Warnings
                  </p>
                  <ul className="list-disc space-y-1 pl-5 text-sm">
                    {preview.warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button disabled={!preview || applying} onClick={handleApply}>
              {applying ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Apply regeneration
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
