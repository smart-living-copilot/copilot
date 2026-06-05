'use client';

import { useCallback, useEffect, useState } from 'react';
import { Loader2, Sparkles } from 'lucide-react';
import { toast } from 'sonner';

import { PanelFrame } from '@/components/copilot/chat-tool-calls/panel-frame';
import {
  type PanelRecord,
  editPanel,
  fetchPanelSource,
  updatePanel,
} from '@/lib/panels-api';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';

export function PanelDialog({
  panel,
  open,
  onOpenChange,
  onChanged,
}: {
  panel: PanelRecord;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onChanged: (updated: PanelRecord) => void;
}) {
  // Bumped on every successful edit to force the live iframe to reload.
  const [version, setVersion] = useState(0);
  const [title, setTitle] = useState(panel.title);

  // AI edit state
  const [instruction, setInstruction] = useState('');
  const [isEditing, setIsEditing] = useState(false);

  // Raw code state
  const [html, setHtml] = useState('');
  const [capsText, setCapsText] = useState('');
  const [sourceLoaded, setSourceLoaded] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    setTitle(panel.title);
  }, [panel.title]);

  const applied = useCallback(
    (updated: PanelRecord) => {
      onChanged(updated);
      setVersion((v) => v + 1);
      setSourceLoaded(false); // re-fetch source next time the Code tab opens
    },
    [onChanged],
  );

  const loadSource = useCallback(async () => {
    try {
      const detail = await fetchPanelSource(panel.id);
      setHtml(detail.html ?? '');
      setCapsText(JSON.stringify(detail.capabilities ?? [], null, 2));
      setSourceLoaded(true);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to load panel source',
      );
    }
  }, [panel.id]);

  const handleRename = async () => {
    if (title.trim() === panel.title) return;
    try {
      applied(await updatePanel(panel.id, { title: title.trim() }));
      toast.success('Renamed');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Rename failed');
    }
  };

  const handleAiEdit = async () => {
    if (!instruction.trim()) return;
    setIsEditing(true);
    try {
      applied(await editPanel(panel.id, instruction.trim()));
      setInstruction('');
      toast.success('Panel updated');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Edit failed');
    } finally {
      setIsEditing(false);
    }
  };

  const handleSaveCode = async () => {
    let capabilities;
    try {
      capabilities = JSON.parse(capsText);
    } catch {
      toast.error('Capabilities is not valid JSON');
      return;
    }
    setIsSaving(true);
    try {
      applied(await updatePanel(panel.id, { html, capabilities }));
      toast.success('Saved');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Save failed');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[88vh] max-w-[min(96vw,80rem)] flex-col gap-0 p-0 sm:max-w-[min(96vw,80rem)]">
        <DialogHeader className="border-b border-border/55 px-4 py-3 pr-12">
          <DialogTitle className="sr-only">{panel.title}</DialogTitle>
          <DialogDescription className="sr-only">
            View and edit the pinned panel.
          </DialogDescription>
          <Input
            aria-label="Panel title"
            className="h-8 max-w-md border-transparent bg-transparent px-1 text-sm font-medium shadow-none focus-visible:border-border focus-visible:bg-background"
            onBlur={handleRename}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void handleRename();
            }}
            value={title}
          />
        </DialogHeader>

        <Tabs
          className="flex min-h-0 flex-1 flex-col"
          defaultValue="panel"
          onValueChange={(v) => {
            if (v === 'code' && !sourceLoaded) void loadSource();
          }}
        >
          <TabsList className="mx-4 mt-3 w-fit">
            <TabsTrigger value="panel">Panel</TabsTrigger>
            <TabsTrigger value="edit">Edit with AI</TabsTrigger>
            <TabsTrigger value="code">Code</TabsTrigger>
          </TabsList>

          <TabsContent
            className="min-h-0 flex-1 overflow-auto p-4"
            value="panel"
          >
            <PanelFrame
              key={version}
              capabilities={panel.capabilities}
              className="h-full min-h-[24rem] w-full rounded-xl"
              src={`/api/panels/${encodeURIComponent(panel.id)}/render?v=${version}`}
              title={panel.title}
            />
          </TabsContent>

          <TabsContent
            className="min-h-0 flex-1 space-y-3 overflow-auto p-4"
            value="edit"
          >
            <p className="text-sm text-muted-foreground">
              Describe a change and the assistant will rebuild the panel — it
              can discover new devices if needed.
            </p>
            <Textarea
              className="min-h-28"
              disabled={isEditing}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="e.g. add a humidity tile, use a dark theme, put the lights on the left"
              value={instruction}
            />
            <div className="flex justify-end">
              <Button
                disabled={isEditing || !instruction.trim()}
                onClick={() => void handleAiEdit()}
              >
                {isEditing ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Sparkles className="size-4" />
                )}
                {isEditing ? 'Updating…' : 'Apply change'}
              </Button>
            </div>
          </TabsContent>

          <TabsContent
            className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-4"
            value="code"
          >
            <div className="flex min-h-0 flex-1 flex-col gap-1">
              <span className="text-xs text-muted-foreground">HTML</span>
              <Textarea
                className="min-h-0 flex-1 font-mono text-xs"
                onChange={(e) => setHtml(e.target.value)}
                spellCheck={false}
                value={html}
              />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground">
                Capabilities (JSON)
              </span>
              <Textarea
                className="h-28 font-mono text-xs"
                onChange={(e) => setCapsText(e.target.value)}
                spellCheck={false}
                value={capsText}
              />
            </div>
            <div className="flex justify-end">
              <Button
                disabled={isSaving || !sourceLoaded}
                onClick={() => void handleSaveCode()}
              >
                {isSaving ? <Loader2 className="size-4 animate-spin" /> : null}
                {isSaving ? 'Saving…' : 'Save'}
              </Button>
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
