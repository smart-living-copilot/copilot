'use client';

import { json as jsonLanguage } from '@codemirror/lang-json';
import { EditorView } from '@codemirror/view';
import Form from '@rjsf/shadcn';
import { type RJSFSchema } from '@rjsf/utils';
import validator from '@rjsf/validator-ajv8';
import { Copy, Loader2, Play } from 'lucide-react';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';

import { CodeEditor } from '@/components/code-editor';
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
const HIDE_SUBMIT_UI_SCHEMA = {
  'ui:submitButtonOptions': { norender: true },
} as const;

function parseJsonInput(value: string): unknown {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  return JSON.parse(trimmed);
}

export function RunAffordanceDialog({
  thingId,
  binding,
  inputSchema,
  note,
  open,
  onOpenChange,
}: {
  thingId: string;
  binding: VirtualThingBinding | null;
  /** JSON Schema for the affordance input, used to render the form view. */
  inputSchema?: RJSFSchema | null;
  /** Optional caption, e.g. a warning that runs use the last saved version. */
  note?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [eventMode, setEventMode] = useState<'evaluate' | 'emit'>('evaluate');
  const [inputMode, setInputMode] = useState<'form' | 'raw'>('form');
  const [inputText, setInputText] = useState('{}');
  const [formData, setFormData] = useState<unknown>(undefined);
  const [resultText, setResultText] = useState('');
  const [isRunning, setIsRunning] = useState(false);

  const needsInput = !!binding && binding.affordance_type !== 'property';
  const isEvent = binding?.affordance_type === 'event';
  const canUseForm = needsInput && !!inputSchema;

  useEffect(() => {
    setResultText('');
    setInputText('{}');
    setFormData(undefined);
    setEventMode('evaluate');
    setInputMode(inputSchema ? 'form' : 'raw');
  }, [binding?.affordance_type, binding?.affordance_name, inputSchema]);

  function switchInputMode(next: 'form' | 'raw') {
    if (next === inputMode) return;
    if (next === 'form') {
      try {
        setFormData(parseJsonInput(inputText));
      } catch {
        toast.error('Fix the raw JSON before switching to the form');
        return;
      }
    } else {
      setInputText(JSON.stringify(formData ?? null, null, 2));
    }
    setInputMode(next);
  }

  async function handleRun() {
    if (!binding || isRunning) return;

    let input: unknown;
    if (needsInput) {
      if (inputMode === 'form') {
        input = formData;
      } else {
        try {
          input = parseJsonInput(inputText);
        } catch (error) {
          toast.error(
            error instanceof Error ? error.message : 'Invalid JSON input',
          );
          return;
        }
      }
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
          <DialogTitle className="pr-8 font-mono text-base">
            {binding ? binding.affordance_name : 'Run'}
          </DialogTitle>
          <DialogDescription>
            {binding ? (
              <>
                <span className="capitalize">{binding.affordance_type}</span>
                {` · ${binding.kind}`}
              </>
            ) : (
              'Execute this affordance and inspect the result.'
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {note ? (
            <p className="text-sm text-muted-foreground">{note}</p>
          ) : null}

          {isEvent ? (
            <div className="space-y-1.5">
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
              <p className="text-xs text-muted-foreground">
                Evaluate runs a dry-run; Emit fires the event for real.
              </p>
            </div>
          ) : null}

          {needsInput ? (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">Input</span>
                {canUseForm ? (
                  <Tabs
                    value={inputMode}
                    onValueChange={(value) =>
                      switchInputMode(value as 'form' | 'raw')
                    }
                  >
                    <TabsList>
                      <TabsTrigger value="form">Form</TabsTrigger>
                      <TabsTrigger value="raw">Raw</TabsTrigger>
                    </TabsList>
                  </Tabs>
                ) : null}
              </div>
              {inputMode === 'form' && inputSchema ? (
                <div className="max-h-72 overflow-y-auto rounded-md border border-border/70 p-3">
                  <Form
                    schema={inputSchema}
                    validator={validator}
                    formData={formData}
                    onChange={(event) => setFormData(event.formData)}
                    uiSchema={HIDE_SUBMIT_UI_SCHEMA}
                  />
                </div>
              ) : (
                <CodeEditor
                  className="text-[13px]"
                  extensions={jsonExtensions}
                  height="12rem"
                  onChange={setInputText}
                  value={inputText}
                />
              )}
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
