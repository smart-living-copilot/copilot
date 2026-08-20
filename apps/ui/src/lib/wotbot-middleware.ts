import {
  AbstractAgent,
  BaseEvent,
  EventType,
  Middleware,
  RunAgentInput,
  RunErrorEvent,
  StepFinishedEvent,
  StepStartedEvent,
  TextMessageContentEvent,
  TextMessageEndEvent,
  TextMessageStartEvent,
  ToolCallArgsEvent,
  ToolCallEndEvent,
  ToolCallStartEvent,
} from '@ag-ui/client';
import { Observable } from 'rxjs';

/** Minimum interval between streamed text batches. */
export const TEXT_THROTTLE_MS = 80;

const ABORT_ERROR_CODES = new Set(['abort', 'STOPPED']);

interface BufferedToolArgs {
  event: ToolCallArgsEvent;
  delta: string;
}

/**
 * Normalizes wotbot's typed AG-UI events before the agent verifier and the
 * runtime's event store see them.
 *
 * State intentionally lives inside run(): AbstractAgent.clone() shares
 * middleware instances between request-scoped agent clones, so instance state
 * would allow concurrent runs to corrupt one another's buffers.
 */
export class WotbotEventMiddleware extends Middleware {
  constructor(private readonly textThrottleMs = TEXT_THROTTLE_MS) {
    super();
  }

  run(input: RunAgentInput, next: AbstractAgent): Observable<BaseEvent> {
    return new Observable<BaseEvent>((subscriber) => {
      const openTextMessages = new Set<string>();
      const openToolCalls = new Set<string>();
      const openSteps: string[] = [];
      const toolCallArgs = new Map<string, BufferedToolArgs>();

      let pendingTextEvent: TextMessageContentEvent | null = null;
      let pendingTextDelta = '';
      let textFlushTimer: ReturnType<typeof setTimeout> | null = null;
      let terminated = false;

      const emit = (event: BaseEvent): void => {
        if (!subscriber.closed) {
          subscriber.next(event);
        }
      };

      const clearTextTimer = (): void => {
        if (textFlushTimer !== null) {
          clearTimeout(textFlushTimer);
          textFlushTimer = null;
        }
      };

      const flushText = (): void => {
        clearTextTimer();
        const event = pendingTextEvent;
        const delta = pendingTextDelta;
        pendingTextEvent = null;
        pendingTextDelta = '';

        if (!event || !delta) {
          return;
        }

        emit({
          ...event,
          delta,
        });
      };

      const bufferText = (event: TextMessageContentEvent): void => {
        if (
          pendingTextEvent &&
          pendingTextEvent.messageId !== event.messageId
        ) {
          flushText();
        }

        pendingTextEvent = event;
        pendingTextDelta += event.delta;
        if (textFlushTimer === null) {
          textFlushTimer = setTimeout(flushText, this.textThrottleMs);
        }
      };

      const bufferToolArgs = (event: ToolCallArgsEvent): void => {
        const buffered = toolCallArgs.get(event.toolCallId);
        toolCallArgs.set(event.toolCallId, {
          event: buffered?.event ?? event,
          delta: (buffered?.delta ?? '') + event.delta,
        });
      };

      const flushToolArgs = (toolCallId: string): void => {
        const buffered = toolCallArgs.get(toolCallId);
        if (!buffered) {
          return;
        }

        emit({
          ...buffered.event,
          delta: buffered.delta,
        });
        toolCallArgs.delete(toolCallId);
      };

      const flushAllToolArgs = (): void => {
        for (const toolCallId of [...toolCallArgs.keys()]) {
          flushToolArgs(toolCallId);
        }
      };

      const closeOpenSteps = (): void => {
        for (const stepName of [...openSteps].reverse()) {
          emit({ type: EventType.STEP_FINISHED, stepName });
        }
        openSteps.length = 0;
      };

      const closeTrackedScopes = (): void => {
        for (const messageId of openTextMessages) {
          emit({ type: EventType.TEXT_MESSAGE_END, messageId });
        }
        openTextMessages.clear();

        for (const toolCallId of openToolCalls) {
          flushToolArgs(toolCallId);
          emit({ type: EventType.TOOL_CALL_END, toolCallId });
        }
        openToolCalls.clear();

        closeOpenSteps();
      };

      const flushBuffers = (): void => {
        flushText();
        flushAllToolArgs();
      };

      const complete = (): void => {
        if (terminated) {
          return;
        }
        terminated = true;
        clearTextTimer();
        subscriber.complete();
      };

      const prepareForSourceEnd = (): void => {
        if (terminated) {
          return;
        }
        flushBuffers();
        // CopilotKit's finalizeRunEvents closes text and tool-call scopes but
        // does not track steps. Close steps here so its synthesized terminal
        // event remains valid for downstream AG-UI clients.
        closeOpenSteps();
      };

      const terminateWith = (event: BaseEvent): void => {
        flushBuffers();
        closeTrackedScopes();
        emit(event);
        complete();
      };

      const sourceSubscription = this.runNext(input, next).subscribe({
        next: (event) => {
          if (terminated) {
            return;
          }

          if (event.type === EventType.TEXT_MESSAGE_CONTENT) {
            bufferText(event as TextMessageContentEvent);
            return;
          }

          // Preserve event order: pending text always precedes the next
          // non-text event, even when its 80 ms timer has not fired yet.
          flushText();

          if (event.type === EventType.TOOL_CALL_ARGS) {
            bufferToolArgs(event as ToolCallArgsEvent);
            return;
          }

          if (event.type === EventType.RUN_ERROR) {
            const runError = event as RunErrorEvent;

            if (ABORT_ERROR_CODES.has(runError.code ?? '')) {
              // Suppress HttpAgent's synthetic abort terminal. The runner has
              // stopRequested=true and will now use finalizeRunEvents to close
              // text/tool scopes, add missing results, and emit RUN_FINISHED.
              flushBuffers();
              closeOpenSteps();
              complete();
              return;
            }

            terminateWith(event);
            return;
          }

          if (event.type === EventType.RUN_FINISHED) {
            terminateWith(event);
            return;
          }

          switch (event.type) {
            case EventType.TEXT_MESSAGE_START: {
              const { messageId } = event as TextMessageStartEvent;
              openTextMessages.add(messageId);
              break;
            }
            case EventType.TEXT_MESSAGE_END: {
              const { messageId } = event as TextMessageEndEvent;
              openTextMessages.delete(messageId);
              break;
            }
            case EventType.TOOL_CALL_START: {
              const { toolCallId } = event as ToolCallStartEvent;
              openToolCalls.add(toolCallId);
              break;
            }
            case EventType.TOOL_CALL_END: {
              const { toolCallId } = event as ToolCallEndEvent;
              flushToolArgs(toolCallId);
              openToolCalls.delete(toolCallId);
              break;
            }
            case EventType.STEP_STARTED: {
              const { stepName } = event as StepStartedEvent;
              openSteps.push(stepName);
              break;
            }
            case EventType.STEP_FINISHED: {
              const { stepName } = event as StepFinishedEvent;
              const index = openSteps.indexOf(stepName);
              if (index !== -1) {
                openSteps.splice(index, 1);
              }
              break;
            }
          }

          emit(event);
        },
        error: (error) => {
          prepareForSourceEnd();
          if (!terminated) {
            terminated = true;
            subscriber.error(error);
          }
        },
        complete: () => {
          prepareForSourceEnd();
          complete();
        },
      });

      return () => {
        terminated = true;
        clearTextTimer();
        sourceSubscription.unsubscribe();
      };
    });
  }
}
