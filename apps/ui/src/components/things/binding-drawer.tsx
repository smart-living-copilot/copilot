'use client';

import { json as jsonLanguage } from '@codemirror/lang-json';
import { python as pythonLanguage } from '@codemirror/lang-python';
import { EditorView } from '@codemirror/view';
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Save,
  Undo2,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';

import { CodeEditor } from '@/components/code-editor';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useUnsavedChangesGuard } from '@/hooks/use-unsaved-changes-guard';
import {
  buildDefineVirtualThingRequest,
  defineVirtualThing,
  type DefineVirtualThingRequest,
  type VirtualThingBinding,
  type VirtualThingDefinition,
  type VirtualValidationReport,
} from '@/lib/virtual-things-api';

const pythonExtensions = [pythonLanguage()];
const jsonExtensions = [jsonLanguage(), EditorView.lineWrapping];

export function bindingKey(binding: VirtualThingBinding) {
  return `${binding.affordance_type}:${binding.affordance_name}`;
}

function parseJsonField<T>(label: string, value: string): T {
  try {
    return JSON.parse(value) as T;
  } catch (error) {
    throw new Error(
      `${label}: ${error instanceof Error ? error.message : 'Invalid JSON'}`,
    );
  }
}

function requestFingerprint(request: DefineVirtualThingRequest) {
  return JSON.stringify(request);
}

function ValidationPanel({
  report,
}: {
  report: VirtualValidationReport | null;
}) {
  if (!report) return null;

  const ok = report.ok;
  return (
    <Card
      className={
        ok
          ? 'rounded-md border-emerald-500/30 bg-emerald-500/10'
          : 'rounded-md border-amber-500/30 bg-amber-500/10'
      }
    >
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-2 text-sm font-medium">
          {ok ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
          ) : (
            <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
          )}
          <span>{ok ? 'Validated' : 'Needs review'}</span>
          <Badge variant="outline">
            {report.smoke_tested ? 'smoke tested' : 'static validation'}
          </Badge>
        </div>
        {report.issues.length ? (
          <div className="space-y-2">
            {report.issues.map((issue, index) => (
              <div
                className="grid gap-2 text-sm sm:grid-cols-[7rem_1fr]"
                key={`${issue.phase}-${issue.affordance_type ?? 'thing'}-${index}`}
              >
                <Badge variant="outline">{issue.phase}</Badge>
                <div className="min-w-0">
                  {issue.affordance_type && issue.affordance_name ? (
                    <div className="font-mono text-xs text-muted-foreground">
                      {issue.affordance_type}:{issue.affordance_name}
                    </div>
                  ) : null}
                  <div className="break-words">{issue.message}</div>
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function BindingDrawer({
  definition,
  activeKey,
  open,
  onOpenChange,
  onSaved,
}: {
  definition: VirtualThingDefinition | null;
  activeKey: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: (next: VirtualThingDefinition) => void;
}) {
  const [handlerCode, setHandlerCode] = useState<string | null>(null);
  const [capabilitiesText, setCapabilitiesText] = useState('[]');
  const [triggerText, setTriggerText] = useState('null');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [validationReport, setValidationReport] =
    useState<VirtualValidationReport | null>(null);

  const original = useMemo(
    () =>
      definition && activeKey
        ? (definition.bindings.find((b) => bindingKey(b) === activeKey) ?? null)
        : null,
    [definition, activeKey],
  );

  const isRecord = original?.kind === 'record';
  const isEvent = original?.affordance_type === 'event';

  // Reset the draft whenever the targeted binding changes.
  useEffect(() => {
    if (!original) return;
    setHandlerCode(original.handler_code);
    setCapabilitiesText(JSON.stringify(original.capabilities ?? [], null, 2));
    setTriggerText(JSON.stringify(original.trigger ?? null, null, 2));
    setValidationReport(null);
  }, [original]);

  const requestSummary = useMemo<
    { request: DefineVirtualThingRequest } | { error: string }
  >(() => {
    if (!definition || !original) return { error: 'Binding not loaded.' };
    if (isRecord) {
      return { request: buildDefineVirtualThingRequest(definition) };
    }
    try {
      const edited: VirtualThingBinding = {
        ...original,
        handler_code: handlerCode,
        capabilities: parseJsonField<VirtualThingBinding['capabilities']>(
          'capabilities',
          capabilitiesText,
        ),
        trigger: parseJsonField<VirtualThingBinding['trigger']>(
          'trigger',
          triggerText,
        ),
      };
      const bindings = definition.bindings.map((b) =>
        bindingKey(b) === activeKey ? edited : b,
      );
      return {
        request: buildDefineVirtualThingRequest(definition, { bindings }),
      };
    } catch (error) {
      return {
        error: error instanceof Error ? error.message : 'Invalid editor state',
      };
    }
  }, [
    definition,
    original,
    isRecord,
    handlerCode,
    capabilitiesText,
    triggerText,
    activeKey,
  ]);

  const originalFingerprint = useMemo(
    () =>
      definition
        ? requestFingerprint(buildDefineVirtualThingRequest(definition))
        : '',
    [definition],
  );
  const hasRequest = 'request' in requestSummary;
  const currentFingerprint = hasRequest
    ? requestFingerprint(requestSummary.request)
    : originalFingerprint;
  const isDirty = !isRecord && currentFingerprint !== originalFingerprint;
  const canSave = !isRecord && hasRequest && isDirty;

  useUnsavedChangesGuard(
    Boolean(isDirty && !isSubmitting && open),
    'You have unsaved Virtual Thing changes. Leave without saving?',
  );

  const handleSave = useCallback(async () => {
    if (!definition || !('request' in requestSummary)) {
      if (!('request' in requestSummary)) toast.error(requestSummary.error);
      return;
    }
    if (isSubmitting || isRecord || !isDirty) return;

    setIsSubmitting(true);
    setValidationReport(null);
    try {
      const result = await defineVirtualThing(
        definition.id,
        requestSummary.request,
      );
      if (result.validationReport) {
        setValidationReport(result.validationReport);
        toast.error('Virtual Thing validation failed');
        return;
      }
      onSaved(result.definition);
      toast.success('Binding saved');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Save failed');
    } finally {
      setIsSubmitting(false);
    }
  }, [definition, requestSummary, isSubmitting, isRecord, isDirty, onSaved]);

  function handleRevert() {
    if (!original) return;
    setHandlerCode(original.handler_code);
    setCapabilitiesText(JSON.stringify(original.capabilities ?? [], null, 2));
    setTriggerText(JSON.stringify(original.trigger ?? null, null, 2));
    setValidationReport(null);
  }

  useEffect(() => {
    if (!open) return;
    function handleWindowKeyDown(event: KeyboardEvent) {
      if (
        !(event.metaKey || event.ctrlKey) ||
        event.key.toLowerCase() !== 's'
      ) {
        return;
      }
      event.preventDefault();
      if (!isSubmitting && canSave) void handleSave();
    }
    window.addEventListener('keydown', handleWindowKeyDown);
    return () => window.removeEventListener('keydown', handleWindowKeyDown);
  }, [open, canSave, handleSave, isSubmitting]);

  function requestClose(next: boolean) {
    if (
      !next &&
      isDirty &&
      !window.confirm('Discard unsaved changes to this binding?')
    ) {
      return;
    }
    onOpenChange(next);
  }

  return (
    <Sheet open={open} onOpenChange={requestClose}>
      <SheetContent
        className="flex w-full flex-col gap-0 p-0"
        style={{ width: 'min(100vw, 64rem)', maxWidth: 'none' }}
      >
        {original ? (
          <>
            <SheetHeader className="gap-1 border-b border-border/70">
              <SheetTitle className="pr-8 font-mono text-base">
                {original.affordance_name}
              </SheetTitle>
              <SheetDescription>
                <span className="capitalize">{original.affordance_type}</span>
                {isRecord ? ' · managed by its owning job (read-only)' : null}
              </SheetDescription>
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <Badge variant="secondary">{original.kind}</Badge>
                <Badge variant="outline">
                  timeout {original.timeout_seconds ?? 30}s
                </Badge>
                <Badge variant="outline">
                  cache {original.cache_ttl_seconds ?? 30}s
                </Badge>
              </div>
            </SheetHeader>

            <div className="flex-1 space-y-4 overflow-y-auto p-4">
              <ValidationPanel report={validationReport} />

              {!hasRequest ? (
                <Card className="rounded-md border-destructive/30 bg-destructive/8">
                  <CardContent className="flex items-start gap-2 p-4 text-sm text-destructive">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span className="min-w-0 break-words">
                      {'error' in requestSummary ? requestSummary.error : ''}
                    </span>
                  </CardContent>
                </Card>
              ) : null}

              <Tabs
                key={activeKey ?? ''}
                defaultValue="handler"
                className="space-y-3"
              >
                <TabsList>
                  <TabsTrigger value="handler">Handler</TabsTrigger>
                  <TabsTrigger value="capabilities">Capabilities</TabsTrigger>
                  {isEvent ? (
                    <TabsTrigger value="trigger">Trigger</TabsTrigger>
                  ) : null}
                </TabsList>

                <TabsContent value="handler" className="mt-0">
                  <CodeEditor
                    className="text-[13px]"
                    disabled={isRecord}
                    extensions={pythonExtensions}
                    height="24rem"
                    onChange={isRecord ? () => {} : setHandlerCode}
                    value={handlerCode ?? ''}
                  />
                </TabsContent>

                <TabsContent value="capabilities" className="mt-0 space-y-2">
                  <p className="text-xs text-muted-foreground">
                    Inferred automatically from the{' '}
                    <code className="font-mono">wot.read_property</code> /{' '}
                    <code className="font-mono">invoke_action</code> calls in
                    your handler. Override only for non-literal thing_ids.
                  </p>
                  <CodeEditor
                    className="text-[13px]"
                    disabled={isRecord}
                    extensions={jsonExtensions}
                    height="20rem"
                    onChange={isRecord ? () => {} : setCapabilitiesText}
                    value={capabilitiesText}
                  />
                </TabsContent>

                {isEvent ? (
                  <TabsContent value="trigger" className="mt-0 space-y-2">
                    <p className="text-xs text-muted-foreground">
                      When this event fires: interval, source_event, or
                      explicit.
                    </p>
                    <CodeEditor
                      className="text-[13px]"
                      disabled={isRecord}
                      extensions={jsonExtensions}
                      height="20rem"
                      onChange={isRecord ? () => {} : setTriggerText}
                      value={triggerText}
                    />
                  </TabsContent>
                ) : null}
              </Tabs>
            </div>

            <SheetFooter className="flex-row flex-wrap items-center justify-between gap-2 border-t border-border/70">
              <span className="text-sm text-muted-foreground">
                {isRecord ? (
                  'Read-only'
                ) : isDirty ? (
                  <span className="flex items-center gap-1.5 text-amber-600 dark:text-amber-500">
                    <span className="h-1.5 w-1.5 rounded-full bg-current" />
                    Unsaved changes
                  </span>
                ) : (
                  'All changes saved'
                )}
              </span>
              {!isRecord ? (
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={handleRevert}
                    disabled={!isDirty}
                  >
                    <Undo2 />
                    Revert
                  </Button>
                  <Button
                    type="button"
                    onClick={() => void handleSave()}
                    disabled={isSubmitting || !canSave}
                  >
                    {isSubmitting ? (
                      <Loader2 className="animate-spin" />
                    ) : (
                      <Save />
                    )}
                    Save
                  </Button>
                </div>
              ) : null}
            </SheetFooter>
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
            Binding not found.
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
