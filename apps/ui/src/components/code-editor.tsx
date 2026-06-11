'use client';

import CodeMirror from '@uiw/react-codemirror';
import { Loader2 } from 'lucide-react';
import { type ComponentProps, useSyncExternalStore } from 'react';

import { useTheme } from '@/components/theme-provider';
import { cn } from '@/lib/utils';

const noopSubscribe = () => () => {};

// `false` on the server and during the first client render (hydration), then
// `true` once mounted — without calling setState in an effect.
function useHydrated() {
  return useSyncExternalStore(
    noopSubscribe,
    () => true,
    () => false,
  );
}

export type CodeEditorExtensions = ComponentProps<
  typeof CodeMirror
>['extensions'];

export function CodeEditor({
  className,
  disabled,
  extensions,
  height = '100%',
  loading = false,
  loadingLabel = 'Loading source',
  onChange,
  value,
}: {
  className?: string;
  disabled?: boolean;
  extensions: CodeEditorExtensions;
  height?: string;
  loading?: boolean;
  loadingLabel?: string;
  onChange: (value: string) => void;
  value: string;
}) {
  const { resolvedTheme } = useTheme();
  // CodeMirror bakes the resolved theme into its DOM, but the theme is only
  // known on the client (localStorage / matchMedia). Defer mounting it until
  // after hydration so the server and first client render agree.
  const mounted = useHydrated();

  const editorClassName = cn(
    'h-full overflow-hidden rounded-md border border-border/70 bg-background text-[12px] [&_.cm-activeLine]:bg-muted/50 [&_.cm-activeLineGutter]:bg-muted/70 [&_.cm-editor]:h-full [&_.cm-gutters]:border-border/70 [&_.cm-gutters]:bg-muted/30 [&_.cm-gutters]:text-muted-foreground [&_.cm-scroller]:overflow-auto',
    className,
  );

  return (
    <div className="relative min-h-0 flex-1">
      {mounted ? (
        <CodeMirror
          basicSetup={{
            foldGutter: true,
            highlightActiveLine: true,
            lineNumbers: true,
          }}
          className={editorClassName}
          editable={!disabled}
          extensions={extensions}
          height={height}
          onChange={onChange}
          readOnly={disabled}
          theme={resolvedTheme}
          value={value}
        />
      ) : (
        <div aria-hidden className={editorClassName} style={{ height }} />
      )}
      {loading ? (
        <div className="absolute inset-0 flex items-center justify-center rounded-md bg-background/70 text-sm text-muted-foreground backdrop-blur-[1px]">
          <Loader2 className="mr-2 size-4 animate-spin" />
          {loadingLabel}
        </div>
      ) : null}
    </div>
  );
}
