'use client';

import { json as jsonLanguage } from '@codemirror/lang-json';
import { python as pythonLanguage } from '@codemirror/lang-python';
import { EditorView } from '@codemirror/view';
import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Play,
  Power,
  Save,
  Trash2,
  Undo2,
} from 'lucide-react';
import { toast } from 'sonner';

import { CodeEditor } from '@/components/code-editor';
import { ConfirmDialog } from '@/components/confirm-dialog';
import { FormPageHeader } from '@/components/form-page-header';
import { AffordanceIcon } from '@/components/things/affordance-icon';
import { RunAffordanceDialog } from '@/components/things/run-affordance-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Toggle } from '@/components/ui/toggle';
import { useUnsavedChangesGuard } from '@/hooks/use-unsaved-changes-guard';
import { getLocalReturnTo } from '@/lib/return-to';
import { cn } from '@/lib/utils';
import {
  buildDefineVirtualThingRequest,
  defineVirtualThing,
  deleteVirtualThing,
  fetchVirtualThingDefinition,
  type DefineVirtualThingRequest,
  type VirtualThingBinding,
  type VirtualThingDefinition,
  type VirtualValidationReport,
} from '@/lib/virtual-things-api';

const pythonExtensions = [pythonLanguage()];
const jsonExtensions = [jsonLanguage(), EditorView.lineWrapping];

interface BindingDraft {
  key: string;
  binding: VirtualThingBinding;
  handlerCode: string | null;
  capabilitiesText: string;
  triggerText: string;
}

type RequestSummary =
  | { request: DefineVirtualThingRequest }
  | { error: string };

function hasRequest(
  summary: RequestSummary,
): summary is { request: DefineVirtualThingRequest } {
  return 'request' in summary;
}

function bindingKey(binding: VirtualThingBinding) {
  return `${binding.affordance_type}:${binding.affordance_name}`;
}

function makeBindingDraft(binding: VirtualThingBinding): BindingDraft {
  return {
    key: bindingKey(binding),
    binding,
    handlerCode: binding.handler_code,
    capabilitiesText: JSON.stringify(binding.capabilities ?? [], null, 2),
    triggerText: JSON.stringify(binding.trigger ?? null, null, 2),
  };
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

function reportTitle(
  report: VirtualValidationReport | null,
  savedSmoke: boolean,
) {
  if (report) return report.ok ? 'Validated' : 'Needs review';
  if (savedSmoke) return 'Saved and smoke tested';
  return null;
}

function ValidationPanel({
  report,
  savedSmoke,
}: {
  report: VirtualValidationReport | null;
  savedSmoke: boolean;
}) {
  const title = reportTitle(report, savedSmoke);
  if (!title) return null;

  const ok = !report || report.ok;
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
          <span>{title}</span>
          {report ? (
            <Badge variant="outline">
              {report.smoke_tested ? 'smoke tested' : 'static validation'}
            </Badge>
          ) : savedSmoke ? (
            <Badge variant="outline">smoke tested</Badge>
          ) : null}
        </div>
        {report?.issues.length ? (
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

export function VirtualThingEditor({
  returnTo,
  thingId,
}: {
  returnTo?: string;
  thingId: string;
}) {
  const router = useRouter();
  const [definition, setDefinition] = useState<VirtualThingDefinition | null>(
    null,
  );
  const [drafts, setDrafts] = useState<BindingDraft[]>([]);
  const [status, setStatus] = useState<'active' | 'disabled'>('active');
  const [isPending, setIsPending] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [validationReport, setValidationReport] =
    useState<VirtualValidationReport | null>(null);
  const [savedSmokeTested, setSavedSmokeTested] = useState(false);
  const [activeBindingKey, setActiveBindingKey] = useState('');
  const [originalFingerprint, setOriginalFingerprint] = useState('');
  const [runKey, setRunKey] = useState<string | null>(null);

  const fallbackDetailHref = `/things/${encodeURIComponent(thingId)}`;
  const cancelHref = getLocalReturnTo(returnTo, fallbackDetailHref);

  useEffect(() => {
    let cancelled = false;
    setIsPending(true);
    setValidationReport(null);
    setSavedSmokeTested(false);

    fetchVirtualThingDefinition(thingId, true)
      .then((data) => {
        if (cancelled) return;
        const nextDrafts = data.bindings.map(makeBindingDraft);
        const request = buildDefineVirtualThingRequest(data);
        setDefinition(data);
        setDrafts(nextDrafts);
        setStatus(data.status);
        setActiveBindingKey(nextDrafts[0]?.key ?? '');
        setOriginalFingerprint(requestFingerprint(request));
      })
      .catch((error) =>
        toast.error(
          error instanceof Error
            ? error.message
            : 'Failed to load virtual Thing',
        ),
      )
      .finally(() => {
        if (!cancelled) setIsPending(false);
      });

    return () => {
      cancelled = true;
    };
  }, [thingId]);

  const requestSummary = useMemo<RequestSummary>(() => {
    if (!definition) return { error: 'Definition not loaded.' };
    try {
      const bindings = drafts.map((draft) => {
        if (draft.binding.kind === 'record') {
          return draft.binding;
        }
        return {
          ...draft.binding,
          handler_code: draft.handlerCode,
          capabilities: parseJsonField<VirtualThingBinding['capabilities']>(
            `${draft.key} capabilities`,
            draft.capabilitiesText,
          ),
          trigger: parseJsonField<VirtualThingBinding['trigger']>(
            `${draft.key} trigger`,
            draft.triggerText,
          ),
        };
      });
      const request = buildDefineVirtualThingRequest(definition, {
        status,
        bindings,
      });
      return { request };
    } catch (error) {
      return {
        error: error instanceof Error ? error.message : 'Invalid editor state',
      };
    }
  }, [definition, drafts, status]);

  const currentFingerprint = hasRequest(requestSummary)
    ? requestFingerprint(requestSummary.request)
    : originalFingerprint;
  const isDirty = currentFingerprint !== originalFingerprint;
  const canSave = hasRequest(requestSummary) && isDirty;

  const activeDraft =
    drafts.find((draft) => draft.key === activeBindingKey) ?? drafts[0] ?? null;
  const runBinding = runKey
    ? (definition?.bindings.find((binding) => bindingKey(binding) === runKey) ??
      null)
    : null;

  useUnsavedChangesGuard(
    Boolean(isDirty && !isSubmitting && !isDeleting),
    'You have unsaved Virtual Thing changes. Leave without saving?',
  );

  const handleSave = useCallback(async () => {
    if (!definition || !hasRequest(requestSummary)) {
      if (!hasRequest(requestSummary)) toast.error(requestSummary.error);
      return;
    }
    if (isSubmitting || !canSave) return;

    setIsSubmitting(true);
    setValidationReport(null);
    setSavedSmokeTested(false);
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

      const nextDefinition = result.definition;
      const nextDrafts = nextDefinition.bindings.map(makeBindingDraft);
      const nextRequest = buildDefineVirtualThingRequest(nextDefinition);
      setDefinition(nextDefinition);
      setDrafts(nextDrafts);
      setStatus(nextDefinition.status);
      setActiveBindingKey((current) => current || nextDrafts[0]?.key || '');
      setOriginalFingerprint(requestFingerprint(nextRequest));
      setSavedSmokeTested(requestSummary.request.status === 'active');
      toast.success('Virtual Thing saved');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Save failed');
    } finally {
      setIsSubmitting(false);
    }
  }, [canSave, definition, isSubmitting, requestSummary]);

  const handleSubmit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      void handleSave();
    },
    [handleSave],
  );

  useEffect(() => {
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
  }, [canSave, handleSave, isSubmitting]);

  function updateDraft(key: string, update: Partial<BindingDraft>) {
    setDrafts((current) =>
      current.map((draft) =>
        draft.key === key ? { ...draft, ...update } : draft,
      ),
    );
  }

  function handleRevert() {
    if (!definition) return;
    const nextDrafts = definition.bindings.map(makeBindingDraft);
    setDrafts(nextDrafts);
    setStatus(definition.status);
    setValidationReport(null);
    setSavedSmokeTested(false);
    setActiveBindingKey(nextDrafts[0]?.key ?? '');
    toast.success('Reverted unsaved changes');
  }

  async function handleDelete() {
    if (!definition) return;
    setIsDeleting(true);
    try {
      await deleteVirtualThing(definition.id);
      toast.success(`Deleted ${definition.title}`);
      router.push('/things');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Delete failed');
    } finally {
      setIsDeleting(false);
    }
  }

  if (isPending) {
    return (
      <Card>
        <CardContent className="flex min-h-64 items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </CardContent>
      </Card>
    );
  }

  if (!definition) {
    return (
      <Card>
        <CardContent className="flex min-h-64 items-center justify-center text-sm text-muted-foreground">
          Virtual Thing not found.
        </CardContent>
      </Card>
    );
  }

  return (
    <form className="space-y-5" onSubmit={handleSubmit}>
      <FormPageHeader
        title={`Edit ${definition.title}`}
        description={definition.id}
        extraActions={
          <>
            <Toggle
              variant="outline"
              pressed={status === 'active'}
              onPressedChange={(pressed) =>
                setStatus(pressed ? 'active' : 'disabled')
              }
              aria-label="Toggle enabled"
            >
              <Power />
              {status === 'active' ? 'Enabled' : 'Disabled'}
            </Toggle>
            <Button
              type="button"
              variant="outline"
              onClick={handleRevert}
              disabled={!isDirty}
            >
              <Undo2 />
              Revert
            </Button>
            <ConfirmDialog
              destructive
              confirmLabel={isDeleting ? 'Removing...' : 'Remove'}
              description="This removes the Virtual Thing definition, bindings, and produced Thing."
              onConfirm={handleDelete}
              title={`Remove "${definition.title}"?`}
              trigger={
                <Button
                  disabled={isDeleting}
                  type="button"
                  variant="destructive"
                >
                  {isDeleting ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Trash2 className="h-4 w-4" />
                  )}
                  Remove
                </Button>
              }
            />
          </>
        }
      />

      <ValidationPanel
        report={validationReport}
        savedSmoke={savedSmokeTested}
      />

      {!hasRequest(requestSummary) ? (
        <Card className="rounded-md border-destructive/30 bg-destructive/8">
          <CardContent className="flex items-start gap-2 p-4 text-sm text-destructive">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span className="min-w-0 break-words">{requestSummary.error}</span>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[15rem_minmax(0,1fr)]">
        <div className="space-y-2">
          <div className="flex items-center justify-between px-1">
            <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
              Bindings
            </span>
            <Badge variant="outline">{drafts.length}</Badge>
          </div>
          <div className="space-y-1">
            {drafts.map((draft) => {
              const isActive = draft.key === activeDraft?.key;
              return (
                <div
                  key={draft.key}
                  className={cn(
                    'flex items-center gap-1 rounded-md border px-2 py-1.5 transition-colors',
                    isActive
                      ? 'border-primary/40 bg-primary/5'
                      : 'border-border/70 hover:bg-muted/50',
                  )}
                >
                  <button
                    type="button"
                    onClick={() => setActiveBindingKey(draft.key)}
                    className="flex min-w-0 flex-1 items-center gap-2 text-left"
                  >
                    <AffordanceIcon type={draft.binding.affordance_type} />
                    <span className="min-w-0 flex-1 truncate font-mono text-sm">
                      {draft.binding.affordance_name}
                    </span>
                    <Badge variant="secondary" className="shrink-0">
                      {draft.binding.kind}
                    </Badge>
                  </button>
                  <Button
                    type="button"
                    size="icon-sm"
                    variant="ghost"
                    aria-label={`Run ${draft.binding.affordance_name}`}
                    onClick={() => setRunKey(draft.key)}
                  >
                    <Play />
                  </Button>
                </div>
              );
            })}
          </div>
        </div>

        {activeDraft ? (
          <Card className="rounded-md border-border/70">
            <CardContent className="space-y-5 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <AffordanceIcon type={activeDraft.binding.affordance_type} />
                  <span className="font-mono text-sm">
                    {activeDraft.binding.affordance_type}:
                    {activeDraft.binding.affordance_name}
                  </span>
                  <Badge variant="secondary">{activeDraft.binding.kind}</Badge>
                  <Badge variant="outline">
                    timeout {activeDraft.binding.timeout_seconds ?? 30}s
                  </Badge>
                  <Badge variant="outline">
                    cache {activeDraft.binding.cache_ttl_seconds ?? 30}s
                  </Badge>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setRunKey(activeDraft.key)}
                >
                  <Play />
                  Run
                </Button>
              </div>

              {activeDraft.binding.kind === 'record' ? (
                <div className="rounded-md border border-border/70 bg-muted/30 p-3 text-sm text-muted-foreground">
                  Record bindings are managed by their owning job.
                </div>
              ) : (
                <Tabs
                  key={activeDraft.key}
                  defaultValue="handler"
                  className="space-y-3"
                >
                  <TabsList>
                    <TabsTrigger value="handler">Handler</TabsTrigger>
                    <TabsTrigger value="capabilities">Capabilities</TabsTrigger>
                    {activeDraft.binding.affordance_type === 'event' ? (
                      <TabsTrigger value="trigger">Trigger</TabsTrigger>
                    ) : null}
                  </TabsList>

                  <TabsContent value="handler" className="mt-0">
                    <CodeEditor
                      className="text-[13px]"
                      extensions={pythonExtensions}
                      height="32rem"
                      onChange={(value) =>
                        updateDraft(activeDraft.key, { handlerCode: value })
                      }
                      value={activeDraft.handlerCode ?? ''}
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
                      extensions={jsonExtensions}
                      height="28rem"
                      onChange={(value) =>
                        updateDraft(activeDraft.key, {
                          capabilitiesText: value,
                        })
                      }
                      value={activeDraft.capabilitiesText}
                    />
                  </TabsContent>

                  {activeDraft.binding.affordance_type === 'event' ? (
                    <TabsContent value="trigger" className="mt-0 space-y-2">
                      <p className="text-xs text-muted-foreground">
                        When this event fires: interval, source_event, or
                        explicit.
                      </p>
                      <CodeEditor
                        className="text-[13px]"
                        extensions={jsonExtensions}
                        height="28rem"
                        onChange={(value) =>
                          updateDraft(activeDraft.key, { triggerText: value })
                        }
                        value={activeDraft.triggerText}
                      />
                    </TabsContent>
                  ) : null}
                </Tabs>
              )}
            </CardContent>
          </Card>
        ) : null}
      </div>

      <RunAffordanceDialog
        thingId={definition.id}
        binding={runBinding}
        note={
          isDirty
            ? 'Runs the last saved version — save your changes to test them.'
            : undefined
        }
        open={runKey !== null}
        onOpenChange={(next) => {
          if (!next) setRunKey(null);
        }}
      />

      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm text-muted-foreground">
          {isDirty ? (
            <span className="flex items-center gap-1.5 text-amber-600 dark:text-amber-500">
              <span className="h-1.5 w-1.5 rounded-full bg-current" />
              Unsaved changes
            </span>
          ) : (
            'All changes saved'
          )}
        </span>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" asChild>
            <Link href={cancelHref}>Cancel</Link>
          </Button>
          <Button type="submit" disabled={isSubmitting || !canSave}>
            {isSubmitting ? <Loader2 className="animate-spin" /> : <Save />}
            Save changes
          </Button>
        </div>
      </div>
    </form>
  );
}
