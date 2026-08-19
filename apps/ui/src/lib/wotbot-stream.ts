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
  content?: string;
  messageId?: string;
  toolCallId?: string;
  toolCallName?: string;
  delta?: string;
  messages?: unknown;
  code?: string;
  stepName?: string;
  threadId?: string;
  runId?: string;
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

function stripRawEvent(event: ParsedSseEvent): ParsedSseEvent {
  const rest = { ...event };
  delete rest.rawEvent;
  return rest;
}

/** Minimum interval (ms) between flushing buffered text deltas. */
const TEXT_THROTTLE_MS = 80;

const TERMINAL_EVENT_TYPES = new Set(['RUN_ERROR', 'RUN_FINISHED']);

/** RUN_ERROR codes that mean "the user stopped this run", not "something
 * broke". The runtime proxy reports the aborted upstream fetch as
 * code "abort"; the stop handler's own interrupt uses "STOPPED". */
const ABORT_ERROR_CODES = new Set(['abort', 'STOPPED']);

export function filterWotbotEventStream(
  stream: ReadableStream<string | Uint8Array>,
): ReadableStream<Uint8Array> {
  let buffer = '';
  // Buffer accumulated tool call args per toolCallId. We emit the complete
  // argument payload once, so tool details are inspectable without streaming
  // partial JSON fragments into the UI.
  const toolCallArgs = new Map<string, string>();
  // Throttle TEXT_MESSAGE_CONTENT deltas
  let pendingTextDelta = '';
  let pendingTextEvent: ParsedSseEvent | null = null;
  let textFlushTimer: ReturnType<typeof setTimeout> | null = null;
  // Once RUN_ERROR/RUN_FINISHED has been forwarded, the run is over as far
  // as the client's own event-ordering validator is concerned -- it rejects
  // every event type unconditionally once it's seen one, including a
  // perfectly legitimate late-arriving TEXT_MESSAGE_END. wotbot's abort path
  // can genuinely emit one after RUN_ERROR: the upstream fetch aborts and
  // the runtime proxy injects a terminal RUN_ERROR immediately, but a
  // TEXT_MESSAGE_END closing out whatever text had already streamed can
  // still be in flight through the pipe at that moment. Drop everything
  // after the terminal event rather than let that race surface as
  // "Agent execution failed: AGUIError: Cannot send event type
  // 'TEXT_MESSAGE_END' ...".
  let runEnded = false;
  // Open scopes, tracked so an aborted run can be closed out cleanly (see
  // the abort handling in processBlock). The client's validator rejects
  // RUN_FINISHED while any text message, tool call, or step is still open.
  const openTextMessages = new Set<string>();
  const openToolCalls = new Set<string>();
  const openSteps: string[] = [];
  let runThreadId: string | undefined;
  let runId: string | undefined;

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
              ...stripRawEvent(pendingTextEvent),
              delta: pendingTextDelta,
            }),
          ),
        );
        pendingTextDelta = '';
        pendingTextEvent = null;
      };

      const processBlock = (block: string): void => {
        if (runEnded) {
          return;
        }

        const parsed = parseSseBlock(block);

        if (!parsed) {
          controller.enqueue(encoder.encode(block));
          return;
        }

        // Drop RAW events
        if (parsed.type === 'RAW') {
          return;
        }

        // Track open scopes so an abort can close them out (see below).
        switch (parsed.type) {
          case 'RUN_STARTED':
            runThreadId = parsed.threadId ?? runThreadId;
            runId = parsed.runId ?? runId;
            break;
          case 'TEXT_MESSAGE_START':
            if (parsed.messageId) openTextMessages.add(parsed.messageId);
            break;
          case 'TEXT_MESSAGE_END':
            if (parsed.messageId) openTextMessages.delete(parsed.messageId);
            break;
          case 'TOOL_CALL_START':
            if (parsed.toolCallId) openToolCalls.add(parsed.toolCallId);
            break;
          case 'TOOL_CALL_END':
            if (parsed.toolCallId) openToolCalls.delete(parsed.toolCallId);
            break;
          case 'STEP_STARTED':
            if (parsed.stepName) openSteps.push(parsed.stepName);
            break;
          case 'STEP_FINISHED': {
            const index = parsed.stepName
              ? openSteps.indexOf(parsed.stepName)
              : -1;
            if (index !== -1) openSteps.splice(index, 1);
            break;
          }
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

        // A user-initiated stop is a normal end of the run, not a failure.
        // Left as RUN_ERROR it surfaces to the user as an error ("This
        // operation was aborted"), so rewrite it into a clean RUN_FINISHED.
        // The client's validator refuses RUN_FINISHED while any text
        // message / tool call / step is still open, so close those out
        // first -- which also leaves whatever partial text had already
        // streamed rendered as a normal (if truncated) assistant message,
        // matching what the backend persists for the interrupted turn.
        if (
          parsed.type === 'RUN_ERROR' &&
          ABORT_ERROR_CODES.has(parsed.code ?? '')
        ) {
          for (const messageId of openTextMessages) {
            controller.enqueue(
              encoder.encode(
                makeSseBlock({ type: 'TEXT_MESSAGE_END', messageId }),
              ),
            );
          }
          openTextMessages.clear();

          for (const toolCallId of openToolCalls) {
            const accumulated = toolCallArgs.get(toolCallId);
            if (accumulated) {
              controller.enqueue(
                encoder.encode(
                  makeSseBlock({
                    type: 'TOOL_CALL_ARGS',
                    toolCallId,
                    delta: accumulated,
                  }),
                ),
              );
              toolCallArgs.delete(toolCallId);
            }
            controller.enqueue(
              encoder.encode(
                makeSseBlock({ type: 'TOOL_CALL_END', toolCallId }),
              ),
            );
          }
          openToolCalls.clear();

          // Innermost step first, mirroring how they were opened.
          for (const stepName of [...openSteps].reverse()) {
            controller.enqueue(
              encoder.encode(makeSseBlock({ type: 'STEP_FINISHED', stepName })),
            );
          }
          openSteps.length = 0;

          controller.enqueue(
            encoder.encode(
              makeSseBlock({
                type: 'RUN_FINISHED',
                ...(runThreadId ? { threadId: runThreadId } : {}),
                ...(runId ? { runId } : {}),
              }),
            ),
          );
          runEnded = true;
          return;
        }

        if (TERMINAL_EVENT_TYPES.has(parsed.type ?? '')) {
          controller.enqueue(
            encoder.encode(makeSseBlock(stripRawEvent(parsed))),
          );
          runEnded = true;
          return;
        }

        // Buffer TOOL_CALL_ARGS — don't emit partial argument fragments.
        if (parsed.type === 'TOOL_CALL_ARGS' && parsed.toolCallId) {
          const existing = toolCallArgs.get(parsed.toolCallId) ?? '';
          toolCallArgs.set(parsed.toolCallId, existing + (parsed.delta ?? ''));
          return;
        }

        // AG-UI clients can use TOOL_CALL_CHUNK as the only representation of a
        // tool call, so preserve it while stripping raw provider metadata.
        if (parsed.type === 'TOOL_CALL_CHUNK') {
          controller.enqueue(
            encoder.encode(makeSseBlock(stripRawEvent(parsed))),
          );
          return;
        }

        // On TOOL_CALL_END, flush the buffered args as a single complete event.
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

        controller.enqueue(encoder.encode(makeSseBlock(stripRawEvent(parsed))));
      };

      const pump = async (): Promise<void> => {
        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            // Flush any remaining text delta -- unless the run already
            // ended, in which case forwarding it would hit the same
            // rejected-by-the-client race this filter exists to avoid.
            if (textFlushTimer) {
              clearTimeout(textFlushTimer);
              textFlushTimer = null;
            }
            if (pendingTextDelta && !runEnded) {
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
