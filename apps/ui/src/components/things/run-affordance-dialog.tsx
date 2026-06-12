'use client';

import { json as jsonLanguage } from '@codemirror/lang-json';
import { EditorView } from '@codemirror/view';
import { Copy, Loader2, Play } from 'lucide-react';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';

import { CodeEditor } from '@/components/code-editor';
import { AffordanceIcon } from '@/components/things/affordance-icon';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  evaluateVirtualEvent,
  emitVirtualEvent,
  invokeVirtualAction,
  readVirtualProperty,
  type VirtualThingBinding,
} from '@/lib/virtual-things-api';

const jsonExtensions = [jsonLanguage(), EditorView.lineWrapping];

function parseJsonInput(value: string): unknown {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  return JSON.parse(trimmed);
}

export function RunAffordanceDialog({
  thingId,
  binding,
  note,
  open,
  onOpenChange,
}: {
  thingId: string;
  binding: VirtualThingBinding | null;
  /** Optional caption, e.g. a warning that runs use the last saved version. */
  note?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [eventMode, setEventMode] = useState<'evaluate' | 'emit'>('evaluate');
  const [inputText, setInputText] = useState('{}');
  const [resultText, setResultText] = useState('');
  const [isRunning, setIsRunning] = useState(false);

  const needsInput = !!binding && binding.affordance_type !== 'property';
  const isEvent = binding?.affordance_type === 'event';

  useEffect(() => {
    setResultText('');
    setInputText('{}');
    setEventMode('evaluate');
  }, [binding?.affordance_type, binding?.affordance_name]);

  async function handleRun() {
    if (!binding || isRunning) return;

    let input: unknown;
    try {
      input = parseJsonInput(inputText);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Invalid JSON input',
      );
      return;
    }

    setIsRunning(true);
    setResultText('');
    try {
      const result =
        binding.affordance_type === 'property'
          ? await readVirtualProperty(thingId, binding.affordance_name)
          : binding.affordance_type === 'action'
            ? await invokeVirtualAction(thingId, binding.affordance_name, input)
            : eventMode === 'emit'
              ? await emitVirtualEvent(thingId, binding.affordance_name, input)
              : await evaluateVirtualEvent(
                  thingId,
                  binding.affordance_name,
                  input,
                  true,
                );
      setResultText(JSON.stringify(result, null, 2));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Run failed');
    } finally {
      setIsRunning(false);
    }
  }

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(resultText);
      toast.success('Result copied');
    } catch {
      toast.error('Copy failed');
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {binding ? <AffordanceIcon type={binding.affordance_type} /> : null}
            <span className="font-mono text-base">
              {binding
                ? `${binding.affordance_type}:${binding.affordance_name}`
                : 'Run'}
            </span>
            {binding ? <Badge variant="secondary">{binding.kind}</Badge> : null}
          </DialogTitle>
          <DialogDescription>
            {note ??
              (isEvent
                ? 'Evaluate runs a dry-run; Emit fires the event for real.'
                : 'Execute this affordance and inspect the result.')}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {isEvent ? (
            <Tabs
              value={eventMode}
              onValueChange={(value) =>
                setEventMode(value as 'evaluate' | 'emit')
              }
            >
              <TabsList>
                <TabsTrigger value="evaluate">Evaluate</TabsTrigger>
                <TabsTrigger value="emit">Emit</TabsTrigger>
              </TabsList>
            </Tabs>
          ) : null}

          {needsInput ? (
            <div className="space-y-1.5">
              <span className="text-sm font-medium">Input</span>
              <CodeEditor
                className="text-[13px]"
                extensions={jsonExtensions}
                height="12rem"
                onChange={setInputText}
                value={inputText}
              />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              This {binding?.affordance_type ?? 'affordance'} takes no input.
            </p>
          )}

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Result</span>
              {resultText ? (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => void handleCopy()}
                >
                  <Copy />
                  Copy
                </Button>
              ) : null}
            </div>
            <CodeEditor
              className="text-[13px]"
              disabled
              extensions={jsonExtensions}
              height="14rem"
              onChange={() => {}}
              value={resultText || '// Run to see the result'}
            />
          </div>
        </div>

        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="outline">
              Close
            </Button>
          </DialogClose>
          <Button
            type="button"
            onClick={() => void handleRun()}
            disabled={isRunning || !binding}
          >
            {isRunning ? <Loader2 className="animate-spin" /> : <Play />}
            Run
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
