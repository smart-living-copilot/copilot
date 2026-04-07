const encoder = new TextEncoder();
const decoder = new TextDecoder();

function decodeChunk(value: string | ArrayBuffer | ArrayBufferView): string {
  if (typeof value === 'string') {
    return value;
  }
  return decoder.decode(value, { stream: true });
}

interface ParsedSseEvent {
  type?: string;
  toolCallId?: string;
  delta?: string;
  [key: string]: unknown;
}

function parseSseBlock(block: string): ParsedSseEvent | null {
  const trimmed = block.trim();
  if (!trimmed) {
    return null;
  }

  const dataLines = trimmed
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart());

  if (dataLines.length === 0) {
    return null;
  }

  try {
    return JSON.parse(dataLines.join('\n')) as ParsedSseEvent;
  } catch {
    return null;
  }
}

function makeSseBlock(event: ParsedSseEvent): string {
  return `data: ${JSON.stringify(event)}\n\n`;
}

/** Minimum interval (ms) between flushing buffered text deltas. */
const TEXT_THROTTLE_MS = 80;

export function filterCopilotEventStream(
  stream: ReadableStream<string | Uint8Array>,
): ReadableStream<Uint8Array> {
  let buffer = '';
  // Buffer accumulated tool call args per toolCallId
  const toolCallArgs = new Map<string, string>();
  // Throttle TEXT_MESSAGE_CONTENT deltas
  let pendingTextDelta = '';
  let pendingTextEvent: ParsedSseEvent | null = null;
  let textFlushTimer: ReturnType<typeof setTimeout> | null = null;

  return new ReadableStream<Uint8Array>({
    start(controller) {
      const reader = stream.getReader();

      const flushTextDelta = (): void => {
        textFlushTimer = null;
        if (!pendingTextDelta || !pendingTextEvent) {
          return;
        }
        controller.enqueue(
          encoder.encode(
            makeSseBlock({
              ...pendingTextEvent,
              delta: pendingTextDelta,
            }),
          ),
        );
        pendingTextDelta = '';
        pendingTextEvent = null;
      };

      const processBlock = (block: string): void => {
        const parsed = parseSseBlock(block);

        if (!parsed) {
          controller.enqueue(encoder.encode(block));
          return;
        }

        // Drop RAW events
        if (parsed.type === 'RAW') {
          return;
        }

        // Throttle TEXT_MESSAGE_CONTENT — batch deltas, flush on timer
        if (parsed.type === 'TEXT_MESSAGE_CONTENT') {
          pendingTextDelta += parsed.delta ?? '';
          pendingTextEvent = parsed;
          if (!textFlushTimer) {
            textFlushTimer = setTimeout(flushTextDelta, TEXT_THROTTLE_MS);
          }
          return;
        }

        // Any non-text event forces a flush of pending text first,
        // so message ordering is preserved.
        if (pendingTextDelta) {
          if (textFlushTimer) {
            clearTimeout(textFlushTimer);
            textFlushTimer = null;
          }
          flushTextDelta();
        }

        // Buffer TOOL_CALL_ARGS — don't emit them individually
        if (parsed.type === 'TOOL_CALL_ARGS' && parsed.toolCallId) {
          const existing = toolCallArgs.get(parsed.toolCallId) ?? '';
          toolCallArgs.set(parsed.toolCallId, existing + (parsed.delta ?? ''));
          return;
        }

        // On TOOL_CALL_END, flush the buffered args as a single event first
        if (parsed.type === 'TOOL_CALL_END' && parsed.toolCallId) {
          const accumulated = toolCallArgs.get(parsed.toolCallId);
          if (accumulated) {
            controller.enqueue(
              encoder.encode(
                makeSseBlock({
                  type: 'TOOL_CALL_ARGS',
                  toolCallId: parsed.toolCallId,
                  delta: accumulated,
                }),
              ),
            );
            toolCallArgs.delete(parsed.toolCallId);
          }
        }

        controller.enqueue(encoder.encode(block));
      };

      const pump = async (): Promise<void> => {
        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            // Flush any remaining text delta
            if (textFlushTimer) {
              clearTimeout(textFlushTimer);
              textFlushTimer = null;
            }
            if (pendingTextDelta) {
              flushTextDelta();
            }
            if (buffer) {
              processBlock(buffer);
            }
            controller.close();
            return;
          }

          buffer += decodeChunk(value);

          let separatorIndex = buffer.indexOf('\n\n');
          while (separatorIndex !== -1) {
            const block = buffer.slice(0, separatorIndex + 2);
            buffer = buffer.slice(separatorIndex + 2);
            processBlock(block);
            separatorIndex = buffer.indexOf('\n\n');
          }
        }
      };

      void pump().catch((error) => controller.error(error));
    },
  });
}
