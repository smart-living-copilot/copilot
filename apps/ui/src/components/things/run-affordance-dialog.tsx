'use client';

import { json as jsonLanguage } from '@codemirror/lang-json';
import { EditorView } from '@codemirror/view';
import Form from '@rjsf/shadcn';
import { type RJSFSchema } from '@rjsf/utils';
import validator from '@rjsf/validator-ajv8';
import { ChevronDown, Copy, Loader2, Play } from 'lucide-react';
import { type ReactNode, useEffect, useState } from 'react';
import { toast } from 'sonner';

import { CodeEditor } from '@/components/code-editor';
import { Button } from '@/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
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
  invokeRuntimeAction,
  readRuntimeProperty,
  subscribeRuntimeEvent,
  type RuntimeAffordanceType,
} from '@/lib/wot-runtime-api';
import {
  evaluateVirtualEvent,
  emitVirtualEvent,
  invokeVirtualAction,
  readVirtualProperty,
} from '@/lib/virtual-things-api';

const jsonExtensions = [jsonLanguage(), EditorView.lineWrapping];
const HIDE_SUBMIT_UI_SCHEMA = {
  'ui:submitButtonOptions': { norender: true },
} as const;

export type RunAffordanceTarget = {
  thingId: string;
  affordanceType: RuntimeAffordanceType;
  affordanceName: string;
  source: 'virtual' | 'runtime';
  kind?: string;
};

function parseJsonInput(value: string): unknown {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  return JSON.parse(trimmed);
}

function ParameterSection({
  actions,
  children,
  open,
  onOpenChange,
  title,
}: {
  actions?: ReactNode;
  children: ReactNode;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
}) {
  return (
    <Collapsible
      open={open}
      onOpenChange={onOpenChange}
      className="space-y-1.5"
    >
      <div className="flex items-center justify-between gap-3">
        <CollapsibleTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="group -ml-2 h-8 px-2 text-sm font-medium"
          >
            <ChevronDown className="h-4 w-4 transition-transform group-data-[state=closed]:-rotate-90" />
            {title}
          </Button>
        </CollapsibleTrigger>
        {actions}
      </div>
      <CollapsibleContent className="data-closed:hidden">
        {children}
      </CollapsibleContent>
    </Collapsible>
  );
}

async function runTarget(
  target: RunAffordanceTarget,
  input: unknown,
  uriVariables: Record<string, unknown> | undefined,
  eventMode: 'evaluate' | 'emit',
): Promise<unknown> {
  if (target.source === 'virtual') {
    if (target.affordanceType === 'property') {
      return readVirtualProperty(target.thingId, target.affordanceName);
    }
    if (target.affordanceType === 'action') {
      return invokeVirtualAction(target.thingId, target.affordanceName, input);
    }
    if (eventMode === 'emit') {
      return emitVirtualEvent(target.thingId, target.affordanceName, input);
    }
    return evaluateVirtualEvent(
      target.thingId,
      target.affordanceName,
      input,
      true,
    );
  }

  if (target.affordanceType === 'property') {
    return readRuntimeProperty(
      target.thingId,
      target.affordanceName,
      uriVariables,
    );
  }
  if (target.affordanceType === 'action') {
    return invokeRuntimeAction(
      target.thingId,
      target.affordanceName,
      input,
      uriVariables,
    );
  }
  return subscribeRuntimeEvent(
    target.thingId,
    target.affordanceName,
    input,
    uriVariables,
  );
}

export function RunAffordanceDialog({
  target,
  inputSchema,
  uriVariablesSchema,
  note,
  open,
  onOpenChange,
}: {
  target: RunAffordanceTarget | null;
  /** JSON Schema for the affordance input, used to render the form view. */
  inputSchema?: RJSFSchema | null;
  /** JSON Schema for URI variables, rendered separately from body input. */
  uriVariablesSchema?: RJSFSchema | null;
  /** Optional caption, e.g. a warning that runs use the last saved version. */
  note?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [eventMode, setEventMode] = useState<'evaluate' | 'emit'>('evaluate');
  const [inputMode, setInputMode] = useState<'form' | 'raw'>('form');
  const [inputText, setInputText] = useState('{}');
  const [formData, setFormData] = useState<unknown>(undefined);
  const [uriVariablesData, setUriVariablesData] = useState<unknown>(undefined);
  const [inputOpen, setInputOpen] = useState(true);
  const [uriVariablesOpen, setUriVariablesOpen] = useState(false);
  const [resultText, setResultText] = useState('');
  const [isRunning, setIsRunning] = useState(false);

  const needsInput = !!target && target.affordanceType !== 'property';
  const showInput = needsInput && !!inputSchema;
  const showUriVariables = target?.source === 'runtime' && !!uriVariablesSchema;
  const hasRunParameters = showInput || showUriVariables;
  const isVirtualEvent =
    target?.source === 'virtual' && target.affordanceType === 'event';

  useEffect(() => {
    setResultText('');
    setInputText('{}');
    setFormData(undefined);
    setUriVariablesData(undefined);
    setEventMode('evaluate');
    setInputMode(inputSchema ? 'form' : 'raw');
    setInputOpen(Boolean(inputSchema));
    setUriVariablesOpen(!inputSchema && Boolean(uriVariablesSchema));
  }, [
    target?.affordanceType,
    target?.affordanceName,
    target?.source,
    inputSchema,
    uriVariablesSchema,
  ]);

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
    if (!target || isRunning) return;

    let input: unknown;
    if (showInput) {
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
    const uriVariables =
      showUriVariables &&
      uriVariablesData &&
      typeof uriVariablesData === 'object' &&
      !Array.isArray(uriVariablesData)
        ? (uriVariablesData as Record<string, unknown>)
        : undefined;

    setIsRunning(true);
    setResultText('');
    try {
      const result = await runTarget(target, input, uriVariables, eventMode);
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
            {target ? target.affordanceName : 'Run'}
          </DialogTitle>
          <DialogDescription>
            {target ? (
              <>
                <span className="capitalize">{target.affordanceType}</span>
                {target.kind ? ` · ${target.kind}` : ' · runtime'}
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

          {isVirtualEvent ? (
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

          {hasRunParameters ? (
            <div className="space-y-3">
              {showInput ? (
                <ParameterSection
                  title="Input"
                  open={inputOpen}
                  onOpenChange={setInputOpen}
                  actions={
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
                  }
                >
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
                </ParameterSection>
              ) : null}

              {showUriVariables && uriVariablesSchema ? (
                <ParameterSection
                  title="URI Variables"
                  open={uriVariablesOpen}
                  onOpenChange={setUriVariablesOpen}
                >
                  <div className="max-h-72 overflow-y-auto rounded-md border border-border/70 p-3">
                    <Form
                      schema={uriVariablesSchema}
                      validator={validator}
                      formData={uriVariablesData}
                      onChange={(event) => setUriVariablesData(event.formData)}
                      uiSchema={HIDE_SUBMIT_UI_SCHEMA}
                    />
                  </div>
                </ParameterSection>
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              This {target?.affordanceType ?? 'affordance'} has no declared
              input or URI variables.
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
            disabled={isRunning || !target}
          >
            {isRunning ? <Loader2 className="animate-spin" /> : <Play />}
            Run
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
