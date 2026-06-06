'use client';

import { json as jsonLanguage } from '@codemirror/lang-json';
import { type FormEvent, useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AlertTriangle, Loader2, Save, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { FormPageHeader } from '@/components/form-page-header';
import { ConfirmDialog } from '@/components/confirm-dialog';
import {
  type ThingRecord,
  createThing,
  deleteThing,
  fetchThing,
  updateThing,
} from '@/lib/things-api';
import { CodeEditor } from '@/components/code-editor';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
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
    <form className="space-y-5" onSubmit={handleSubmit}>
      <FormPageHeader
        title={headerTitle}
        description={headerDescription}
        cancelHref={cancelHref}
        extraActions={
          <>
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
  );
}
