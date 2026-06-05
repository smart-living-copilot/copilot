'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Maximize2, RefreshCw, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { PanelFrame } from '@/components/copilot/chat-tool-calls/panel-frame';
import { PanelDialog } from '@/components/panels/panel-dialog';
import { type PanelRecord, deletePanel, fetchPanels } from '@/lib/panels-api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardAction,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

/** Renders children only once scrolled into view, to avoid mounting every
 *  panel's live bridge at once. */
function WhenVisible({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el || visible) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: '200px' },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [visible]);

  return (
    <div ref={ref} className="h-full w-full">
      {visible ? children : null}
    </div>
  );
}

function PanelCard({
  panel,
  onChanged,
  onDeleted,
}: {
  panel: PanelRecord;
  onChanged: (updated: PanelRecord) => void;
  onDeleted: (id: string) => void;
}) {
  const [isDeleting, setIsDeleting] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await deletePanel(panel.id);
      toast.success('Panel deleted');
      onDeleted(panel.id);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to delete panel',
      );
      setIsDeleting(false);
    }
  };

  const deviceCount = new Set(panel.capabilities.map((c) => c.thingId)).size;

  return (
    <Card className="overflow-hidden py-0">
      <CardHeader className="gap-0 border-b border-border/55 px-3 py-2.5">
        <CardTitle className="truncate text-sm">{panel.title}</CardTitle>
        <CardAction>
          <Button
            aria-label="Delete panel"
            disabled={isDeleting}
            onClick={() => void handleDelete()}
            size="icon-xs"
            type="button"
            variant="ghost"
          >
            <Trash2 className="size-3.5" />
          </Button>
        </CardAction>
      </CardHeader>

      <CardContent className="p-0">
        {/* Non-interactive preview: the overlay captures clicks and opens the
            full interactive dialog instead of letting the iframe handle them. */}
        <button
          aria-label={`Open ${panel.title}`}
          className="group relative block h-[18rem] w-full cursor-pointer"
          onClick={() => setDialogOpen(true)}
          type="button"
        >
          <div className="pointer-events-none absolute inset-0">
            <WhenVisible>
              <PanelFrame
                capabilities={panel.capabilities}
                className="h-full w-full rounded-none border-0"
                src={`/api/panels/${encodeURIComponent(panel.id)}/render`}
                title={panel.title}
              />
            </WhenVisible>
          </div>
          <div className="absolute inset-0 flex items-center justify-center bg-background/0 opacity-0 transition group-hover:bg-background/40 group-hover:opacity-100">
            <span className="flex items-center gap-1.5 rounded-md bg-background/90 px-2.5 py-1 text-xs font-medium shadow-sm">
              <Maximize2 className="size-3.5" />
              Open
            </span>
          </div>
        </button>
      </CardContent>

      <CardFooter className="justify-between px-3 py-2 text-[0.7rem] text-muted-foreground">
        <span>
          {deviceCount} device{deviceCount === 1 ? '' : 's'}
        </span>
        {panel.created_at ? (
          <span>{new Date(panel.created_at).toLocaleDateString()}</span>
        ) : null}
      </CardFooter>

      <PanelDialog
        onChanged={onChanged}
        onOpenChange={setDialogOpen}
        open={dialogOpen}
        panel={panel}
      />
    </Card>
  );
}

export function PanelsList() {
  const [panels, setPanels] = useState<PanelRecord[]>([]);
  const [isPending, setIsPending] = useState(true);

  const loadData = useCallback(async () => {
    setIsPending(true);
    try {
      setPanels(await fetchPanels());
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to load panels',
      );
    } finally {
      setIsPending(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleChanged = useCallback((updated: PanelRecord) => {
    setPanels((prev) =>
      prev.map((p) => (p.id === updated.id ? { ...p, ...updated } : p)),
    );
  }, []);

  const handleDeleted = useCallback((id: string) => {
    setPanels((prev) => prev.filter((p) => p.id !== id));
  }, []);

  return (
    <div className="space-y-5">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight">Panels</h1>
          <p className="max-w-3xl text-sm text-muted-foreground">
            Pinned interactive panels. Pin a panel from a chat to keep it here —
            it stays even if you delete the conversation. Open one to interact,
            edit it with the assistant, or tweak its code.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="secondary">{panels.length} pinned</Badge>
          <Button
            variant="outline"
            onClick={() => void loadData()}
            disabled={isPending}
          >
            <RefreshCw
              className={isPending ? 'h-4 w-4 animate-spin' : 'h-4 w-4'}
            />
            Refresh
          </Button>
        </div>
      </section>

      {isPending ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {['s1', 's2', 's3'].map((key) => (
            <Skeleton key={key} className="h-[24rem] w-full rounded-xl" />
          ))}
        </div>
      ) : panels.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {panels.map((panel) => (
            <PanelCard
              key={panel.id}
              panel={panel}
              onChanged={handleChanged}
              onDeleted={handleDeleted}
            />
          ))}
        </div>
      ) : (
        <div className="rounded-md border border-dashed px-6 py-12 text-center">
          <h2 className="text-xl font-semibold tracking-tight">
            No pinned panels
          </h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            Ask the assistant to build a control panel or dashboard, then click
            the pin icon to keep it here.
          </p>
        </div>
      )}
    </div>
  );
}
