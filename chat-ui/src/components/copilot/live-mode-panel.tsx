'use client';

import {
  ArrowLeft,
  AudioLines,
  ImageIcon,
  LineChart,
  LoaderCircle,
  Mic,
  MicOff,
  RotateCcw,
  Video,
  VideoOff,
  X,
} from 'lucide-react';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from 'react';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type { MediaIngressSession } from '@/hooks/use-media-ingress-session';
import { ArtifactPreview } from './chat-tool-call-cards';
import type { RunCodeArtifact } from './chat-tool-call-model';
import { MediaStreamAura } from './media-stream-aura';

function useAttachMediaStream<TElement extends HTMLMediaElement>(
  mediaRef: RefObject<TElement | null>,
  stream: MediaStream | null,
) {
  useEffect(() => {
    const media = mediaRef.current;
    if (!media) {
      return;
    }

    media.srcObject = stream;
    if (stream) {
      void media.play().catch(() => {
        // Autoplay can be browser-policy dependent; live media remains connected.
      });
    }

    return () => {
      media.srcObject = null;
    };
  }, [stream, mediaRef]);
}

type MarkdownBlock =
  | { text: string; type: 'paragraph' }
  | { level: 1 | 2 | 3; text: string; type: 'heading' }
  | { items: string[]; type: 'ordered-list' | 'unordered-list' }
  | { code: string; type: 'code' };

function isMarkdownBlockStart(line: string) {
  return (
    /^#{1,3}\s+/.test(line) ||
    /^[-*]\s+/.test(line) ||
    /^\d+\.\s+/.test(line) ||
    /^```/.test(line)
  );
}

function parseMarkdownBlocks(text: string): MarkdownBlock[] {
  const lines = text.replace(/\r\n/g, '\n').split('\n');
  const blocks: MarkdownBlock[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index] ?? '';
    const trimmed = line.trim();

    if (!trimmed) {
      index += 1;
      continue;
    }

    if (/^```/.test(trimmed)) {
      index += 1;
      const codeLines: string[] = [];
      while (index < lines.length && !/^```/.test(lines[index]?.trim() ?? '')) {
        codeLines.push(lines[index] ?? '');
        index += 1;
      }
      if (index < lines.length) {
        index += 1;
      }
      blocks.push({ code: codeLines.join('\n'), type: 'code' });
      continue;
    }

    const heading = /^(#{1,3})\s+(.+)$/.exec(trimmed);
    if (heading) {
      blocks.push({
        level: heading[1].length as 1 | 2 | 3,
        text: heading[2],
        type: 'heading',
      });
      index += 1;
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (index < lines.length) {
        const match = /^[-*]\s+(.+)$/.exec(lines[index]?.trim() ?? '');
        if (!match) {
          break;
        }
        items.push(match[1]);
        index += 1;
      }
      blocks.push({ items, type: 'unordered-list' });
      continue;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      const items: string[] = [];
      while (index < lines.length) {
        const match = /^\d+\.\s+(.+)$/.exec(lines[index]?.trim() ?? '');
        if (!match) {
          break;
        }
        items.push(match[1]);
        index += 1;
      }
      blocks.push({ items, type: 'ordered-list' });
      continue;
    }

    const paragraphLines: string[] = [];
    while (index < lines.length) {
      const candidate = lines[index]?.trim() ?? '';
      if (
        !candidate ||
        (paragraphLines.length > 0 && isMarkdownBlockStart(candidate))
      ) {
        break;
      }
      paragraphLines.push(candidate);
      index += 1;
    }
    blocks.push({ text: paragraphLines.join(' '), type: 'paragraph' });
  }

  return blocks;
}

function safeHref(href: string) {
  return /^(https?:\/\/|\/|#)/i.test(href) ? href : undefined;
}

function renderInlineMarkdown(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const tokenPattern = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g;
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = tokenPattern.exec(text)) !== null) {
    if (match.index > cursor) {
      nodes.push(text.slice(cursor, match.index));
    }

    const token = match[0];
    const key = `${keyPrefix}-${match.index}`;
    if (token.startsWith('`')) {
      nodes.push(
        <code className="rounded bg-muted px-1 py-0.5 text-sm" key={key}>
          {token.slice(1, -1)}
        </code>,
      );
    } else if (token.startsWith('**')) {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith('*')) {
      nodes.push(<em key={key}>{token.slice(1, -1)}</em>);
    } else {
      const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
      const href = link ? safeHref(link[2]) : undefined;
      nodes.push(
        href ? (
          <a
            className="text-primary underline underline-offset-4"
            href={href}
            key={key}
            rel="noreferrer"
            target={href.startsWith('http') ? '_blank' : undefined}
          >
            {link?.[1]}
          </a>
        ) : (
          token
        ),
      );
    }

    cursor = match.index + token.length;
  }

  if (cursor < text.length) {
    nodes.push(text.slice(cursor));
  }

  return nodes;
}

function LiveResponseMarkdown({ text }: { text: string }) {
  const blocks = useMemo(() => parseMarkdownBlocks(text), [text]);

  return (
    <div className="mx-auto max-w-2xl space-y-4 text-left text-base leading-7 text-foreground md:text-lg">
      {blocks.map((block, index) => {
        const key = `${block.type}-${index}`;
        if (block.type === 'heading') {
          const Heading = `h${block.level}` as 'h1' | 'h2' | 'h3';
          return (
            <Heading
              className="text-xl font-semibold tracking-tight text-foreground md:text-2xl"
              key={key}
            >
              {renderInlineMarkdown(block.text, key)}
            </Heading>
          );
        }
        if (block.type === 'code') {
          return (
            <pre
              className="overflow-auto rounded-lg border border-border bg-muted p-3 text-sm leading-6"
              key={key}
            >
              <code>{block.code}</code>
            </pre>
          );
        }
        if (block.type === 'unordered-list') {
          return (
            <ul className="list-disc space-y-1 pl-6" key={key}>
              {block.items.map((item, itemIndex) => (
                <li key={`${key}-${itemIndex}`}>
                  {renderInlineMarkdown(item, `${key}-${itemIndex}`)}
                </li>
              ))}
            </ul>
          );
        }
        if (block.type === 'ordered-list') {
          return (
            <ol className="list-decimal space-y-1 pl-6" key={key}>
              {block.items.map((item, itemIndex) => (
                <li key={`${key}-${itemIndex}`}>
                  {renderInlineMarkdown(item, `${key}-${itemIndex}`)}
                </li>
              ))}
            </ol>
          );
        }
        if (block.type === 'paragraph') {
          return <p key={key}>{renderInlineMarkdown(block.text, key)}</p>;
        }
        return null;
      })}
    </div>
  );
}

function AssistantThinkingDots() {
  return (
    <div
      aria-label="Waiting for assistant response"
      className="flex justify-start"
      role="status"
    >
      <div className="flex h-9 items-center gap-1.5 rounded-full border border-border bg-muted/50 px-3">
        <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground" />
        <span
          className="size-1.5 animate-bounce rounded-full bg-muted-foreground"
          style={{ animationDelay: '120ms' }}
        />
        <span
          className="size-1.5 animate-bounce rounded-full bg-muted-foreground"
          style={{ animationDelay: '240ms' }}
        />
      </div>
    </div>
  );
}

type ReopenChipInfo = { icon: ReactNode; label: string };

type ArtifactViewerMode = {
  inViewer: boolean;
  dismissViewer: () => void;
  reopenViewer: () => void;
  showReopenChip: boolean;
  reopenChipInfo: ReopenChipInfo | null;
};

function useArtifactViewerMode({
  artifacts,
  latestAssistantText,
  latestUserTranscript,
}: {
  artifacts: RunCodeArtifact[];
  latestAssistantText: string | null;
  latestUserTranscript: string | null;
}): ArtifactViewerMode {
  const artifactSignature = useMemo(
    () => artifacts.map((a) => `${a.kind}:${a.filename}`).join('|'),
    [artifacts],
  );
  const hasArtifact = !!artifactSignature && !!latestAssistantText;
  const [trackedSignature, setTrackedSignature] = useState<string | null>(null);
  const [transcriptAtArrival, setTranscriptAtArrival] = useState<string | null>(
    null,
  );
  const [manuallyDismissedSignature, setManuallyDismissedSignature] = useState<
    string | null
  >(null);
  const nextTrackedSignature = hasArtifact ? artifactSignature : null;
  if (nextTrackedSignature !== trackedSignature) {
    setTrackedSignature(nextTrackedSignature);
    setTranscriptAtArrival(nextTrackedSignature ? latestUserTranscript : null);
  }
  const transcriptAdvanced =
    hasArtifact && latestUserTranscript !== transcriptAtArrival;
  const inViewer =
    hasArtifact &&
    !transcriptAdvanced &&
    artifactSignature !== manuallyDismissedSignature;

  const dismissViewer = useCallback(() => {
    setManuallyDismissedSignature(artifactSignature);
  }, [artifactSignature]);

  const reopenViewer = useCallback(() => {
    setManuallyDismissedSignature(null);
    setTranscriptAtArrival(latestUserTranscript);
  }, [latestUserTranscript]);

  const showReopenChip = hasArtifact && !inViewer;
  const reopenChipInfo = useMemo<ReopenChipInfo | null>(() => {
    if (artifacts.length === 0) return null;
    const onlyImages = artifacts.every((a) => a.kind === 'image');
    const noun = onlyImages
      ? artifacts.length > 1
        ? 'images'
        : 'image'
      : artifacts.length > 1
        ? 'charts'
        : 'chart';
    return {
      icon: onlyImages ? (
        <ImageIcon className="size-4" />
      ) : (
        <LineChart className="size-4" />
      ),
      label: `View ${artifacts.length > 1 ? `${artifacts.length} ` : ''}${noun}`,
    };
  }, [artifacts]);

  return {
    inViewer,
    dismissViewer,
    reopenViewer,
    showReopenChip,
    reopenChipInfo,
  };
}

export function LiveModePanel({
  artifacts = [],
  session,
}: {
  artifacts?: RunCodeArtifact[];
  session: MediaIngressSession;
}) {
  const previewRef = useRef<HTMLVideoElement | null>(null);
  const remoteAudioRef = useRef<HTMLAudioElement | null>(null);
  useAttachMediaStream(previewRef, session.localStream);
  useAttachMediaStream(remoteAudioRef, session.remoteStream);

  const status = useMemo(() => {
    if (session.state === 'requesting') {
      return {
        detail: 'Waiting for camera and microphone access',
        icon: <LoaderCircle className="size-5 animate-spin" />,
      };
    }
    if (session.state === 'connecting') {
      return {
        detail: 'Opening the live media channel',
        icon: <LoaderCircle className="size-5 animate-spin" />,
      };
    }
    if (session.state === 'error') {
      return {
        detail: session.error || 'The live media channel could not be opened',
        icon: <Video className="size-5" />,
      };
    }
    if (session.isMicrophoneMuted) {
      return {
        detail: 'Microphone is off',
        icon: <MicOff className="size-5" />,
      };
    }
    return {
      detail: 'Ready when you are',
      icon: <AudioLines className="size-5" />,
    };
  }, [session.error, session.isMicrophoneMuted, session.state]);

  const mediaControlsDisabled =
    !session.localStream ||
    session.state === 'requesting' ||
    session.state === 'error';
  const {
    inViewer,
    dismissViewer,
    reopenViewer,
    showReopenChip,
    reopenChipInfo,
  } = useArtifactViewerMode({
    artifacts,
    latestAssistantText: session.latestAssistantText,
    latestUserTranscript: session.latestUserTranscript,
  });

  const isConnected = session.state === 'connected';
  const { setMicrophoneMuted, setCameraEnabled } = session;
  const isMicrophoneMuted = session.isMicrophoneMuted;
  const isCameraEnabled = session.isCameraEnabled;

  useEffect(() => {
    if (!isConnected && !inViewer) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target;
      if (target instanceof HTMLElement) {
        const tag = target.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || target.isContentEditable) {
          return;
        }
      }

      if (event.key === 'Escape' && inViewer) {
        event.preventDefault();
        dismissViewer();
        return;
      }

      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (!isConnected || mediaControlsDisabled) return;

      const key = event.key.toLowerCase();
      if (key === 'm') {
        event.preventDefault();
        setMicrophoneMuted(!isMicrophoneMuted);
      } else if (key === 'v') {
        event.preventDefault();
        setCameraEnabled(!isCameraEnabled);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [
    dismissViewer,
    inViewer,
    isCameraEnabled,
    isConnected,
    isMicrophoneMuted,
    mediaControlsDisabled,
    setCameraEnabled,
    setMicrophoneMuted,
  ]);

  const showAssistantPending =
    session.isAssistantResponsePending && !session.latestAssistantText;
  const hasAnyContent =
    !!session.latestAssistantText ||
    !!session.latestUserTranscript ||
    showAssistantPending;

  return (
    <section className="relative flex min-h-0 flex-1 flex-col overflow-hidden bg-background">
      <audio ref={remoteAudioRef} autoPlay />

      {inViewer ? (
        <div className="flex min-h-0 flex-1 items-center justify-center px-4 pb-28 pt-14 md:px-8">
          {artifacts.length === 1 ? (
            <ArtifactPreview artifact={artifacts[0]} fill />
          ) : (
            <div className="grid h-full w-full max-w-6xl grid-cols-1 gap-3 sm:grid-cols-2">
              {artifacts.map((artifact) => (
                <div
                  className="min-h-0 overflow-hidden rounded-xl border border-border bg-background/70 p-2 shadow-sm"
                  key={`${artifact.kind}:${artifact.filename}`}
                >
                  <ArtifactPreview artifact={artifact} />
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col items-center overflow-y-auto px-6 pb-36 pt-16 text-center">
          <MediaStreamAura
            icon={status.icon}
            size={hasAnyContent ? 'md' : 'lg'}
            state={session.state}
            stream={session.localStream}
          />

          {!hasAnyContent ? (
            <p className="mt-6 max-w-md text-balance text-sm font-medium text-muted-foreground md:text-base">
              {status.detail}
            </p>
          ) : null}

          <div className="mt-8 w-full max-w-2xl space-y-6">
            {session.latestUserTranscript ? (
              <div className="text-left">
                <div className="mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  You said
                </div>
                <p className="text-base italic leading-7 text-muted-foreground md:text-lg">
                  &ldquo;{session.latestUserTranscript}&rdquo;
                </p>
              </div>
            ) : null}

            {showReopenChip && reopenChipInfo ? (
              <div className="flex justify-start">
                <Button
                  className="gap-2"
                  onClick={reopenViewer}
                  size="sm"
                  type="button"
                  variant="outline"
                >
                  {reopenChipInfo.icon}
                  {reopenChipInfo.label}
                </Button>
              </div>
            ) : null}

            {session.latestAssistantText ? (
              <LiveResponseMarkdown text={session.latestAssistantText} />
            ) : null}

            {showAssistantPending ? <AssistantThinkingDots /> : null}
          </div>
        </div>
      )}

      {session.localStream ? (
        <div
          className={
            inViewer
              ? 'absolute right-3 top-3 z-10 h-12 w-16 overflow-hidden rounded-lg border border-border bg-muted shadow-md md:right-4 md:top-4 md:h-14 md:w-20'
              : 'absolute right-3 top-3 z-10 h-20 w-28 overflow-hidden rounded-xl border border-border bg-muted shadow-lg md:right-4 md:top-4 md:h-24 md:w-36'
          }
        >
          <video
            ref={previewRef}
            autoPlay
            className={
              session.isCameraEnabled
                ? 'h-full w-full object-cover'
                : 'h-full w-full object-cover opacity-0'
            }
            muted
            playsInline
          />
          {!session.isCameraEnabled ? (
            <div className="absolute inset-0 flex items-center justify-center text-muted-foreground">
              <VideoOff className={inViewer ? 'size-3.5' : 'size-5'} />
            </div>
          ) : null}
        </div>
      ) : null}

      {inViewer ? (
        <div className="absolute left-3 top-3 z-20 md:left-4 md:top-4">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                aria-label="Back to conversation"
                className="rounded-full bg-background/85 shadow-sm backdrop-blur"
                onClick={dismissViewer}
                size="icon"
                type="button"
                variant="outline"
              >
                <ArrowLeft className="size-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent className="flex items-center gap-2" side="right">
              Back to conversation
              <kbd className="rounded border border-border/60 bg-background/50 px-1 text-[0.65rem] font-medium">
                Esc
              </kbd>
            </TooltipContent>
          </Tooltip>
        </div>
      ) : null}

      <div className="pointer-events-none absolute inset-x-0 bottom-6 z-20 flex justify-center px-4">
        <div className="pointer-events-auto flex items-center gap-2 rounded-full border border-border bg-background/85 px-3 py-2 shadow-lg backdrop-blur">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                aria-label={
                  session.isMicrophoneMuted
                    ? 'Unmute microphone'
                    : 'Mute microphone'
                }
                aria-pressed={session.isMicrophoneMuted}
                className="rounded-full"
                disabled={mediaControlsDisabled}
                onClick={() =>
                  session.setMicrophoneMuted(!session.isMicrophoneMuted)
                }
                size="icon-lg"
                type="button"
                variant={session.isMicrophoneMuted ? 'secondary' : 'outline'}
              >
                {session.isMicrophoneMuted ? (
                  <MicOff className="size-4" />
                ) : (
                  <Mic className="size-4" />
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent className="flex items-center gap-2" side="top">
              {session.isMicrophoneMuted
                ? 'Unmute microphone'
                : 'Mute microphone'}
              <kbd className="rounded border border-border/60 bg-background/50 px-1 text-[0.65rem] font-medium">
                M
              </kbd>
            </TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                aria-label={
                  session.isCameraEnabled ? 'Turn camera off' : 'Turn camera on'
                }
                aria-pressed={!session.isCameraEnabled}
                className="rounded-full"
                disabled={mediaControlsDisabled}
                onClick={() =>
                  session.setCameraEnabled(!session.isCameraEnabled)
                }
                size="icon-lg"
                type="button"
                variant={session.isCameraEnabled ? 'outline' : 'secondary'}
              >
                {session.isCameraEnabled ? (
                  <Video className="size-4" />
                ) : (
                  <VideoOff className="size-4" />
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent className="flex items-center gap-2" side="top">
              {session.isCameraEnabled ? 'Turn camera off' : 'Turn camera on'}
              <kbd className="rounded border border-border/60 bg-background/50 px-1 text-[0.65rem] font-medium">
                V
              </kbd>
            </TooltipContent>
          </Tooltip>

          {session.state === 'error' ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  aria-label="Try again"
                  className="rounded-full"
                  onClick={() => void session.start()}
                  size="icon-lg"
                  type="button"
                  variant="default"
                >
                  <RotateCcw className="size-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="top">Try again</TooltipContent>
            </Tooltip>
          ) : null}

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                aria-label={
                  session.state === 'error' ? 'Back to chat' : 'Exit live mode'
                }
                className="rounded-full"
                onClick={session.stop}
                size="icon-lg"
                type="button"
                variant="outline"
              >
                <X className="size-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="top">
              {session.state === 'error' ? 'Back to chat' : 'Exit live mode'}
            </TooltipContent>
          </Tooltip>
        </div>
      </div>
    </section>
  );
}
