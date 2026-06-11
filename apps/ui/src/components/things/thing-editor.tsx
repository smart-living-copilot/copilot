'use client';

import { json as jsonLanguage } from '@codemirror/lang-json';
import { type FormEvent, useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AlertTriangle, Loader2, Save, Sparkles, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { FormPageHeader } from '@/components/form-page-header';
import { ConfirmDialog } from '@/components/confirm-dialog';
import {
  type EnrichmentDiffItem,
  type EnrichmentResult,
  type ThingRecord,
  createThing,
  deleteThing,
  enrichThing,
  fetchThing,
  updateThing,
} from '@/lib/things-api';
import { CodeEditor } from '@/components/code-editor';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { getLocalReturnTo, isCollectionReturnTo } from '@/lib/return-to';
import { useUnsavedChangesGuard } from '@/hooks/use-unsaved-changes-guard';

const THING_TEMPLATE = `{
  "@context": ["https://www.w3.org/2022/wot/td/v1.1"],
  "id": "urn:uuid:example-thing",
  "title": "ExampleThing",
  "description": "Describe the smart thing here.",
  "securityDefinitions": {
    "nosec_sc": {
      "scheme": "nosec"
    }
  },
  "security": "nosec_sc",
  "properties": {},
  "actions": {},
  "events": {}
}`;

const jsonExtensions = [jsonLanguage()];

function summarizeDocument(documentText: string) {
  try {
    const parsed = JSON.parse(documentText) as Record<string, unknown>;
    if (!parsed || Array.isArray(parsed)) {
      return { error: 'Thing Description must be a JSON object.', title: null };
    }
    return {
      document: parsed,
      title: typeof parsed.title === 'string' ? parsed.title : null,
    };
  } catch (error) {
    return {
      error: error instanceof Error ? error.message : 'Invalid JSON',
      title: null,
    };
  }
}

function formatDiffValue(value: unknown): string {
  if (typeof value === 'string') return value;
  return JSON.stringify(value);
}

function diffBadgeVariant(kind: EnrichmentDiffItem['kind']) {
  if (kind === 'unit') return 'default';
  if (kind === 'type') return 'secondary';
  return 'outline';
}

interface ThingEditorProps {
  mode: 'create' | 'edit';
  returnTo?: string;
  thingId?: string;
}

export function ThingEditor({ mode, returnTo, thingId }: ThingEditorProps) {
  const router = useRouter();
  const [documentText, setDocumentText] = useState(THING_TEMPLATE);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isEnriching, setIsEnriching] = useState(false);
  const [enrichment, setEnrichment] = useState<EnrichmentResult | null>(null);
  const [thing, setThing] = useState<ThingRecord | null>(null);
  const [isPending, setIsPending] = useState(mode === 'edit');

  // Load thing for edit mode
  useEffect(() => {
    if (mode !== 'edit' || !thingId) return;
    setIsPending(true);
    fetchThing(thingId)
      .then((data) => {
        setThing(data);
        if (data.json) {
          setDocumentText(data.json);
        }
      })
      .catch((err) =>
        toast.error(
          err instanceof Error ? err.message : 'Failed to load thing',
        ),
      )
      .finally(() => setIsPending(false));
  }, [mode, thingId]);

  const summary = summarizeDocument(documentText);
  const isDirty =
    mode === 'create'
      ? documentText !== THING_TEMPLATE
      : documentText !== (thing?.json ?? '');
  const canSave = !('error' in summary) && (mode === 'create' || isDirty);
  const canEnrich = !('error' in summary) && Boolean(summary.document);
  const fallbackDetailHref = thingId
    ? `/things/${encodeURIComponent(thingId)}`
    : '/things';
  const cancelHref = getLocalReturnTo(
    returnTo,
    mode === 'create' ? '/things' : fallbackDetailHref,
  );

  useUnsavedChangesGuard(
    Boolean(isDirty && !isSubmitting && !isDeleting),
    'You have unsaved Thing Description changes. Leave without saving?',
  );

  function handleFormatDocument() {
    try {
      const parsed = JSON.parse(documentText);
      const formatted = JSON.stringify(parsed, null, 2);
      setDocumentText(formatted);
      toast.success('Formatted JSON');
    } catch {
      toast.error('Fix the JSON before formatting');
    }
  }

  const handleSave = useCallback(async () => {
    if ('error' in summary) {
      toast.error(summary.error);
      return;
    }

    if (isSubmitting || !canSave || !summary.document) {
      return;
    }

    setIsSubmitting(true);
    try {
      const result =
        mode === 'create'
          ? await createThing(summary.document)
          : await updateThing(thingId ?? '', summary.document);
      const savedDetailHref = `/things/${encodeURIComponent(result.id)}`;
      const saveHref =
        mode === 'edit' &&
        returnTo &&
        isCollectionReturnTo(getLocalReturnTo(returnTo, ''), '/things')
          ? getLocalReturnTo(returnTo, savedDetailHref)
          : savedDetailHref;

      toast.success(mode === 'create' ? 'Thing created' : 'Thing updated');
      router.push(saveHref);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Save failed');
    } finally {
      setIsSubmitting(false);
    }
  }, [canSave, isSubmitting, summary, mode, returnTo, thingId, router]);

  const handleEnrich = useCallback(async () => {
    if ('error' in summary) {
      toast.error(summary.error);
      return;
    }
    if (!summary.document || isEnriching) return;

    const draftId =
      typeof summary.document.id === 'string' && summary.document.id.trim()
        ? summary.document.id
        : (thingId ?? 'draft');

    setIsEnriching(true);
    try {
      const result = await enrichThing(draftId, summary.document);
      setEnrichment(result);
      toast.success('Semantic enrichment proposed');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Enrichment failed');
    } finally {
      setIsEnriching(false);
    }
  }, [isEnriching, summary, thingId]);

  const handleApplyEnrichment = useCallback(() => {
    if (!enrichment) return;
    setDocumentText(JSON.stringify(enrichment.enriched, null, 2));
    setEnrichment(null);
    toast.success('Applied enrichment to the draft');
  }, [enrichment]);

  const handleSubmit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      void handleSave();
    },
    [handleSave],
  );

  // Cmd+S save shortcut
  useEffect(() => {
    function handleWindowKeyDown(event: KeyboardEvent) {
      if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== 's')
        return;
      event.preventDefault();
      if (!isSubmitting && canSave) void handleSave();
    }

    window.addEventListener('keydown', handleWindowKeyDown);
    return () => window.removeEventListener('keydown', handleWindowKeyDown);
  }, [isSubmitting, canSave, handleSave]);

  async function handleDeleteThing() {
    if (!thing) return;

    setIsDeleting(true);
    try {
      await deleteThing(thing.id);
      toast.success(`Deleted ${thing.title}`);
      router.push('/things');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Delete failed');
    } finally {
      setIsDeleting(false);
    }
  }

  const headerTitle = mode === 'create' ? 'Create thing' : 'Edit thing';
  const headerDescription =
    mode === 'create'
      ? 'Write or paste a W3C Thing Description JSON document.'
      : thing
        ? `Update the Thing Description JSON for ${thing.title}.`
        : 'Update the Thing Description JSON.';

  if (mode === 'edit' && isPending) {
    return (
      <Card>
        <CardContent className="flex min-h-64 items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <form className="space-y-5" onSubmit={handleSubmit}>
        <FormPageHeader
          title={headerTitle}
          description={headerDescription}
          cancelHref={cancelHref}
          extraActions={
            <>
              <Button
                disabled={!canEnrich || isSubmitting || isEnriching}
                onClick={() => void handleEnrich()}
                size="sm"
                type="button"
                variant="outline"
              >
                {isEnriching ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="h-4 w-4" />
                )}
                Enrich
              </Button>
              <Button
                onClick={handleFormatDocument}
                size="sm"
                type="button"
                variant="outline"
              >
                Format JSON
              </Button>
              {mode === 'edit' && thing ? (
                <ConfirmDialog
                  destructive
                  confirmLabel={isDeleting ? 'Removing...' : 'Remove'}
                  description="This permanently removes the Thing Description and related credentials. This cannot be undone."
                  onConfirm={handleDeleteThing}
                  title={`Remove "${thing.title}"?`}
                  trigger={
                    <Button
                      disabled={isDeleting}
                      size="sm"
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
              ) : null}
            </>
          }
          submitLabel={mode === 'create' ? 'Create thing' : 'Save changes'}
          submitIcon={<Save className="h-4 w-4" />}
          isSubmitting={isSubmitting}
          disabled={isSubmitting || !canSave}
        />

        <Card className="overflow-hidden">
          {'error' in summary && (
            <div className="border-b border-destructive/20 bg-destructive/8 px-5 py-3 text-sm text-destructive">
              <div className="flex items-center gap-2 font-medium">
                <AlertTriangle className="h-4 w-4" />
                Invalid JSON
              </div>
              <p className="mt-2">{summary.error}</p>
            </div>
          )}

          <div className="min-h-[720px]">
            <CodeEditor
              className="rounded-none border-0 text-[13px]"
              extensions={jsonExtensions}
              height="720px"
              onChange={setDocumentText}
              value={documentText}
            />
          </div>
        </Card>
      </form>

      <Dialog
        open={Boolean(enrichment)}
        onOpenChange={(open) => {
          if (!open) setEnrichment(null);
        }}
      >
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Review semantic enrichment</DialogTitle>
            <DialogDescription>
              Apply adds these annotations to the JSON draft. Save changes when
              you are ready to update the catalog.
            </DialogDescription>
          </DialogHeader>

          {enrichment ? (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                <Badge variant="outline">
                  {enrichment.validation.attempts} attempt
                  {enrichment.validation.attempts === 1 ? '' : 's'}
                </Badge>
                <Badge
                  variant={enrichment.validation.ok ? 'default' : 'destructive'}
                >
                  {enrichment.validation.ok ? 'Validated' : 'Needs review'}
                </Badge>
              </div>

              {enrichment.validation.warnings?.length ? (
                <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-900 dark:text-amber-200">
                  {enrichment.validation.warnings.join(' ')}
                </div>
              ) : null}

              <div className="max-h-96 overflow-y-auto rounded-md border border-border/70">
                {enrichment.diff.length ? (
                  <div className="divide-y divide-border/70">
                    {enrichment.diff.map((item, index) => (
                      <div
                        className="grid gap-2 p-3 text-sm sm:grid-cols-[8rem_1fr]"
                        key={`${item.path}-${index}`}
                      >
                        <div>
                          <Badge variant={diffBadgeVariant(item.kind)}>
                            {item.kind}
                          </Badge>
                        </div>
                        <div className="min-w-0 space-y-1">
                          <div className="font-medium">{item.label}</div>
                          <div className="break-all font-mono text-xs text-muted-foreground">
                            {item.path}
                          </div>
                          <div className="break-all font-mono text-xs">
                            {formatDiffValue(item.value)}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="p-4 text-sm text-muted-foreground">
                    No semantic additions were proposed.
                  </div>
                )}
              </div>
            </div>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setEnrichment(null)}
            >
              Cancel
            </Button>
            <Button type="button" onClick={handleApplyEnrichment}>
              Apply
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
