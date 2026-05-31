'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AlertTriangle, Loader2, Save, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import {
  type ThingRecord,
  createThing,
  deleteThing,
  fetchThing,
  updateThing,
} from '@/lib/things-api';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';

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

const EDITOR_TAB = '  ';

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
  thingId?: string;
}

export function ThingEditor({ mode, thingId }: ThingEditorProps) {
  const router = useRouter();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [documentText, setDocumentText] = useState(THING_TEMPLATE);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [scrollTop, setScrollTop] = useState(0);
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
          setScrollTop(0);
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
  const liveLineCount = documentText.split('\n').length;
  const lineNumbers = Array.from(
    { length: Math.max(liveLineCount, 1) },
    (_, i) => i + 1,
  );
  const isDirty =
    mode === 'create'
      ? documentText !== THING_TEMPLATE
      : documentText !== (thing?.json ?? '');
  const canSave = !('error' in summary) && (mode === 'create' || isDirty);

  function handleFormatDocument() {
    try {
      const parsed = JSON.parse(documentText);
      const formatted = JSON.stringify(parsed, null, 2);
      setDocumentText(formatted);
      setScrollTop(0);
      toast.success('Formatted JSON');
      requestAnimationFrame(() => {
        textareaRef.current?.setSelectionRange(0, 0);
        textareaRef.current?.scrollTo({ top: 0 });
      });
    } catch {
      toast.error('Fix the JSON before formatting');
    }
  }

  function handleEditorKeyDown(
    event: React.KeyboardEvent<HTMLTextAreaElement>,
  ) {
    if (event.key !== 'Tab') return;
    event.preventDefault();

    const target = event.currentTarget;
    const selectionStart = target.selectionStart ?? 0;
    const selectionEnd = target.selectionEnd ?? selectionStart;
    const nextText = `${documentText.slice(0, selectionStart)}${EDITOR_TAB}${documentText.slice(selectionEnd)}`;
    const nextCursor = selectionStart + EDITOR_TAB.length;

    setDocumentText(nextText);
    requestAnimationFrame(() => {
      target.selectionStart = nextCursor;
      target.selectionEnd = nextCursor;
    });
  }

  const handleSave = useCallback(async () => {
    if (!('document' in summary) || !summary.document) {
      toast.error(
        'error' in summary ? summary.error : 'Invalid Thing Description',
      );
      return;
    }

    setIsSubmitting(true);
    try {
      const result =
        mode === 'create'
          ? await createThing(summary.document)
          : await updateThing(thingId ?? '', summary.document);

      toast.success(mode === 'create' ? 'Thing created' : 'Thing updated');
      router.push(`/things/${encodeURIComponent(result.id)}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Save failed');
    } finally {
      setIsSubmitting(false);
    }
  }, [summary, mode, thingId, router]);

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
    if (!window.confirm(`Delete "${thing.title}"?`)) return;

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
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h1
            className={
              mode === 'create'
                ? 'text-2xl font-semibold text-foreground md:text-3xl'
                : 'truncate text-3xl font-semibold text-foreground md:text-4xl'
            }
          >
            {mode === 'create'
              ? 'Create thing'
              : thing?.title ||
                ('title' in summary ? summary.title : null) ||
                'Edit thing'}
          </h1>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleFormatDocument}>
            Format JSON
          </Button>
          {mode === 'edit' && thing && (
            <Button
              variant="destructive"
              size="sm"
              onClick={() => void handleDeleteThing()}
              disabled={isDeleting}
            >
              {isDeleting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
              Remove
            </Button>
          )}
          <Button
            size="sm"
            onClick={() => void handleSave()}
            disabled={isSubmitting || !canSave}
          >
            {isSubmitting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {mode === 'create' ? 'Create thing' : 'Save changes'}
          </Button>
        </div>
      </div>

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

        <div className="grid min-h-[720px] grid-cols-[56px_minmax(0,1fr)]">
          <div
            aria-hidden="true"
            className="overflow-hidden border-r bg-muted/10 px-2 py-4 font-mono text-xs leading-6 text-muted-foreground"
          >
            <div
              className="text-right"
              style={{ transform: `translateY(-${scrollTop}px)` }}
            >
              {lineNumbers.map((lineNumber) => (
                <div key={lineNumber}>{lineNumber}</div>
              ))}
            </div>
          </div>

          <Textarea
            ref={textareaRef}
            value={documentText}
            onChange={(event) => setDocumentText(event.target.value)}
            onKeyDown={handleEditorKeyDown}
            onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
            spellCheck={false}
            className="min-h-[720px] resize-none rounded-none border-0 bg-background px-4 py-4 font-mono text-[13px] leading-6 shadow-none focus-visible:ring-0"
          />
        </div>
      </Card>
    </div>
  );
}
