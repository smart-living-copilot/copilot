'use client';

import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { PanelFrame } from '@/components/copilot/chat-tool-calls/panel-frame';
import {
  type PanelRecord,
  deletePanel,
  fetchPanels,
} from '@/lib/dashboards-api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

function PanelTile({
  panel,
  onDeleted,
}: {
  panel: PanelRecord;
  onDeleted: (id: string) => void;
}) {
  const [isDeleting, setIsDeleting] = useState(false);

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

  return (
    <Card className="gap-0 border-border/70 py-0 shadow-sm shadow-black/5">
      <CardContent className="space-y-2 p-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="truncate text-sm font-medium">{panel.title}</h2>
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
        </div>
        <PanelFrame
          capabilities={panel.capabilities}
          className="h-[24rem]"
          src={`/api/dashboards/${encodeURIComponent(panel.id)}/render`}
          title={panel.title}
        />
      </CardContent>
    </Card>
  );
}

export function DashboardsList() {
  const [panels, setPanels] = useState<PanelRecord[]>([]);
  const [isPending, setIsPending] = useState(true);

  const loadData = useCallback(async () => {
    setIsPending(true);
    try {
      setPanels(await fetchPanels());
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to load dashboards',
      );
    } finally {
      setIsPending(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  return (
    <div className="space-y-5">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight">Dashboards</h1>
          <p className="max-w-3xl text-sm text-muted-foreground">
            Pinned interactive panels. Pin a panel from a chat to keep it here —
            it stays even if you delete the conversation.
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
        <div className="grid gap-4 md:grid-cols-2">
          {['s1', 's2'].map((key) => (
            <Skeleton key={key} className="h-[28rem] w-full rounded-md" />
          ))}
        </div>
      ) : panels.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2">
          {panels.map((panel) => (
            <PanelTile
              key={panel.id}
              panel={panel}
              onDeleted={(id) =>
                setPanels((prev) => prev.filter((p) => p.id !== id))
              }
            />
          ))}
        </div>
      ) : (
        <div className="rounded-md border border-dashed px-6 py-12 text-center">
          <h2 className="text-xl font-semibold tracking-tight">
            No pinned dashboards
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
