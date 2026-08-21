import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import test from 'node:test';

import {
  AbstractAgent,
  BaseEvent,
  compactEvents,
  EventType,
  RunAgentInput,
  StepFinishedEvent,
  StepStartedEvent,
  TextMessageEndEvent,
  TextMessageStartEvent,
  ToolCallArgsEvent,
  ToolCallEndEvent,
  ToolCallResultEvent,
  ToolCallStartEvent,
} from '@ag-ui/client';
import { InMemoryAgentRunner } from '@copilotkit/runtime/v2';
import { Observable, of, ReplaySubject } from 'rxjs';

import { WotbotAgentRunner } from './wotbot-agent-runner';
import { WotbotEventMiddleware } from './wotbot-middleware';

function runStarted(threadId: string, runId: string): BaseEvent {
  return { type: EventType.RUN_STARTED, threadId, runId };
}

function runFinished(threadId: string, runId: string): BaseEvent {
  return { type: EventType.RUN_FINISHED, threadId, runId };
}

function runInput(threadId: string, runId: string): RunAgentInput {
  return {
    threadId,
    runId,
    messages: [],
    tools: [],
    context: [],
    state: {},
    forwardedProps: {},
  };
}

class ScriptedAgent extends AbstractAgent {
  constructor(
    threadId: string,
    private readonly makeEvents: (
      input: RunAgentInput,
    ) => Observable<BaseEvent>,
  ) {
    super({ threadId });
  }

  run(input: RunAgentInput): Observable<BaseEvent> {
    return this.makeEvents(input);
  }
}

class AbortableAgent extends AbstractAgent {
  readonly events = new ReplaySubject<BaseEvent>();

  constructor(threadId: string) {
    super({ threadId });
  }

  run(): Observable<BaseEvent> {
    return this.events.asObservable();
  }

  abortRun(): void {
    this.events.next({
      type: EventType.RUN_ERROR,
      message: 'This operation was aborted',
      code: 'abort',
    });
    this.events.complete();
  }
}

async function collectAgentRun(
  agent: AbstractAgent,
  runId: string,
): Promise<BaseEvent[]> {
  const events: BaseEvent[] = [];
  await agent.runAgent(
    { runId },
    {
      onEvent: ({ event }) => {
        events.push(event);
      },
    },
  );
  return events;
}

function eventTypes(events: BaseEvent[]): EventType[] {
  return events.map((event) => event.type);
}

function assertTerminalScopesClosed(events: BaseEvent[]): void {
  const textMessages = new Set<string>();
  const toolCalls = new Set<string>();
  const steps = new Set<string>();

  for (const event of events) {
    switch (event.type) {
      case EventType.TEXT_MESSAGE_START:
        textMessages.add((event as TextMessageStartEvent).messageId);
        break;
      case EventType.TEXT_MESSAGE_END:
        textMessages.delete((event as TextMessageEndEvent).messageId);
        break;
      case EventType.TOOL_CALL_START:
        toolCalls.add((event as ToolCallStartEvent).toolCallId);
        break;
      case EventType.TOOL_CALL_END:
        toolCalls.delete((event as ToolCallEndEvent).toolCallId);
        break;
      case EventType.STEP_STARTED:
        steps.add((event as StepStartedEvent).stepName);
        break;
      case EventType.STEP_FINISHED:
        steps.delete((event as StepFinishedEvent).stepName);
        break;
      case EventType.RUN_FINISHED:
        assert.deepEqual([...textMessages], [], 'text scopes at RUN_FINISHED');
        assert.deepEqual([...toolCalls], [], 'tool scopes at RUN_FINISHED');
        assert.deepEqual([...steps], [], 'step scopes at RUN_FINISHED');
        break;
    }
  }
}

test('runNext transforms TOOL_CALL_CHUNK and batches its arguments', async () => {
  const threadId = randomUUID();
  const runId = randomUUID();
  const agent = new ScriptedAgent(threadId, () =>
    of(
      runStarted(threadId, runId),
      {
        type: EventType.TOOL_CALL_CHUNK,
        toolCallId: 'tc1',
        toolCallName: 'things_search',
        parentMessageId: 'assistant-1',
        delta: '{"query"',
      },
      {
        type: EventType.TOOL_CALL_CHUNK,
        toolCallId: 'tc1',
        delta: ':"temperature"}',
      },
      runFinished(threadId, runId),
    ),
  ).use(new WotbotEventMiddleware());

  const events = await collectAgentRun(agent, runId);
  const args = events.filter(
    (event) => event.type === EventType.TOOL_CALL_ARGS,
  );

  assert.deepEqual(eventTypes(events), [
    EventType.RUN_STARTED,
    EventType.TOOL_CALL_START,
    EventType.TOOL_CALL_ARGS,
    EventType.TOOL_CALL_END,
    EventType.RUN_FINISHED,
  ]);
  assert.equal(args.length, 1);
  assert.equal(args[0]?.toolCallId, 'tc1');
  assert.equal(args[0]?.delta, '{"query":"temperature"}');
});

test('batches text and flushes it before a non-text event', async () => {
  const threadId = randomUUID();
  const runId = randomUUID();
  const agent = new ScriptedAgent(threadId, () =>
    of(
      runStarted(threadId, runId),
      {
        type: EventType.TEXT_MESSAGE_START,
        messageId: 'm1',
        role: 'assistant',
      },
      {
        type: EventType.TEXT_MESSAGE_CONTENT,
        messageId: 'm1',
        delta: 'Hello',
      },
      {
        type: EventType.TEXT_MESSAGE_CONTENT,
        messageId: 'm1',
        delta: ' world',
      },
      {
        type: EventType.TOOL_CALL_START,
        toolCallId: 'tc1',
        toolCallName: 'things_search',
      },
      { type: EventType.TOOL_CALL_END, toolCallId: 'tc1' },
      { type: EventType.TEXT_MESSAGE_END, messageId: 'm1' },
      runFinished(threadId, runId),
    ),
  ).use(new WotbotEventMiddleware());

  const events = await collectAgentRun(agent, runId);
  const contents = events.filter(
    (event) => event.type === EventType.TEXT_MESSAGE_CONTENT,
  );

  assert.equal(contents.length, 1);
  assert.equal(contents[0]?.delta, 'Hello world');
  assert.ok(
    eventTypes(events).indexOf(EventType.TEXT_MESSAGE_CONTENT) <
      eventTypes(events).indexOf(EventType.TOOL_CALL_START),
  );
});

test('flushes text on the throttle timer without waiting for a boundary', async () => {
  const threadId = randomUUID();
  const runId = randomUUID();
  const source = new ReplaySubject<BaseEvent>();
  const agent = new ScriptedAgent(threadId, () => source.asObservable()).use(
    new WotbotEventMiddleware(0),
  );

  let resolveContent: (() => void) | undefined;
  const contentReceived = new Promise<void>((resolve) => {
    resolveContent = resolve;
  });
  const events: BaseEvent[] = [];
  const runPromise = agent.runAgent(
    { runId },
    {
      onEvent: ({ event }) => {
        events.push(event);
        if (event.type === EventType.TEXT_MESSAGE_CONTENT) {
          resolveContent?.();
        }
      },
    },
  );

  source.next(runStarted(threadId, runId));
  source.next({
    type: EventType.TEXT_MESSAGE_START,
    messageId: 'm1',
    role: 'assistant',
  });
  source.next({
    type: EventType.TEXT_MESSAGE_CONTENT,
    messageId: 'm1',
    delta: 'timer flush',
  });

  await contentReceived;
  assert.equal(events.at(-1)?.type, EventType.TEXT_MESSAGE_CONTENT);

  source.next({ type: EventType.TEXT_MESSAGE_END, messageId: 'm1' });
  source.next(runFinished(threadId, runId));
  source.complete();
  await runPromise;
});

test('does not merge consecutive text events for different message IDs', async () => {
  const threadId = randomUUID();
  const runId = randomUUID();
  const agent = new ScriptedAgent(threadId, () =>
    of(
      runStarted(threadId, runId),
      {
        type: EventType.TEXT_MESSAGE_START,
        messageId: 'm1',
        role: 'assistant',
      },
      {
        type: EventType.TEXT_MESSAGE_START,
        messageId: 'm2',
        role: 'assistant',
      },
      {
        type: EventType.TEXT_MESSAGE_CONTENT,
        messageId: 'm1',
        delta: 'first',
      },
      {
        type: EventType.TEXT_MESSAGE_CONTENT,
        messageId: 'm2',
        delta: 'second',
      },
      { type: EventType.TEXT_MESSAGE_END, messageId: 'm1' },
      { type: EventType.TEXT_MESSAGE_END, messageId: 'm2' },
      runFinished(threadId, runId),
    ),
  ).use(new WotbotEventMiddleware());

  const contents = (await collectAgentRun(agent, runId)).filter(
    (event) => event.type === EventType.TEXT_MESSAGE_CONTENT,
  );

  assert.deepEqual(
    contents.map((event) => [event.messageId, event.delta]),
    [
      ['m1', 'first'],
      ['m2', 'second'],
    ],
  );
});

test('batches interleaved tool arguments by toolCallId', async () => {
  const threadId = randomUUID();
  const runId = randomUUID();
  const agent = new ScriptedAgent(threadId, () =>
    of(
      runStarted(threadId, runId),
      {
        type: EventType.TOOL_CALL_START,
        toolCallId: 'tc-a',
        toolCallName: 'things_search',
      },
      { type: EventType.TOOL_CALL_ARGS, toolCallId: 'tc-a', delta: '{"q"' },
      {
        type: EventType.TOOL_CALL_START,
        toolCallId: 'tc-b',
        toolCallName: 'registry_health',
      },
      { type: EventType.TOOL_CALL_ARGS, toolCallId: 'tc-b', delta: '{}' },
      { type: EventType.TOOL_CALL_ARGS, toolCallId: 'tc-a', delta: ':"a"}' },
      { type: EventType.TOOL_CALL_END, toolCallId: 'tc-b' },
      { type: EventType.TOOL_CALL_END, toolCallId: 'tc-a' },
      runFinished(threadId, runId),
    ),
  ).use(new WotbotEventMiddleware());

  const events = await collectAgentRun(agent, runId);
  const starts = new Set<string>();
  const argsById = new Map<string, string>();

  for (const event of events) {
    if (event.type === EventType.TOOL_CALL_START) {
      starts.add((event as ToolCallStartEvent).toolCallId);
    }
    if (event.type === EventType.TOOL_CALL_ARGS) {
      const argsEvent = event as ToolCallArgsEvent;
      assert.ok(starts.has(argsEvent.toolCallId));
      assert.equal(argsById.has(argsEvent.toolCallId), false);
      argsById.set(argsEvent.toolCallId, argsEvent.delta);
    }
  }

  assert.deepEqual(
    [...argsById],
    [
      ['tc-b', '{}'],
      ['tc-a', '{"q":"a"}'],
    ],
  );
});

test('repairs open scopes before a premature RUN_FINISHED and drops late events', async () => {
  const threadId = randomUUID();
  const runId = randomUUID();
  const agent = new ScriptedAgent(threadId, () =>
    of(
      runStarted(threadId, runId),
      { type: EventType.STEP_STARTED, stepName: 'analysis' },
      {
        type: EventType.TEXT_MESSAGE_START,
        messageId: 'm1',
        role: 'assistant',
      },
      {
        type: EventType.TEXT_MESSAGE_CONTENT,
        messageId: 'm1',
        delta: 'partial',
      },
      {
        type: EventType.TOOL_CALL_START,
        toolCallId: 'tc1',
        toolCallName: 'run_code',
      },
      { type: EventType.TOOL_CALL_ARGS, toolCallId: 'tc1', delta: '{"x":1}' },
      runFinished(threadId, runId),
      { type: EventType.TOOL_CALL_END, toolCallId: 'tc1' },
      { type: EventType.TEXT_MESSAGE_END, messageId: 'm1' },
      { type: EventType.STEP_FINISHED, stepName: 'analysis' },
    ),
  ).use(new WotbotEventMiddleware());

  const events = await collectAgentRun(agent, runId);

  assert.deepEqual(eventTypes(events), [
    EventType.RUN_STARTED,
    EventType.STEP_STARTED,
    EventType.TEXT_MESSAGE_START,
    EventType.TEXT_MESSAGE_CONTENT,
    EventType.TOOL_CALL_START,
    EventType.TOOL_CALL_ARGS,
    EventType.TEXT_MESSAGE_END,
    EventType.TOOL_CALL_END,
    EventType.STEP_FINISHED,
    EventType.RUN_FINISHED,
  ]);
  assertTerminalScopesClosed(events);
});

test('repairs scopes before a genuine RUN_ERROR and preserves the error', async () => {
  const threadId = randomUUID();
  const runId = randomUUID();
  const agent = new ScriptedAgent(threadId, () =>
    of(
      runStarted(threadId, runId),
      { type: EventType.STEP_STARTED, stepName: 'analysis' },
      {
        type: EventType.TEXT_MESSAGE_START,
        messageId: 'm1',
        role: 'assistant',
      },
      {
        type: EventType.TOOL_CALL_START,
        toolCallId: 'tc1',
        toolCallName: 'run_code',
      },
      { type: EventType.TOOL_CALL_ARGS, toolCallId: 'tc1', delta: '{"x":1}' },
      {
        type: EventType.RUN_ERROR,
        message: 'provider failed',
        code: 'UPSTREAM',
      },
      { type: EventType.TOOL_CALL_END, toolCallId: 'tc1' },
    ),
  ).use(new WotbotEventMiddleware());

  const events = await collectAgentRun(agent, runId);

  assert.deepEqual(eventTypes(events), [
    EventType.RUN_STARTED,
    EventType.STEP_STARTED,
    EventType.TEXT_MESSAGE_START,
    EventType.TOOL_CALL_START,
    EventType.TOOL_CALL_ARGS,
    EventType.TEXT_MESSAGE_END,
    EventType.TOOL_CALL_END,
    EventType.STEP_FINISHED,
    EventType.RUN_ERROR,
  ]);
  const error = events.at(-1);
  assert.equal(error?.type, EventType.RUN_ERROR);
  assert.equal(error?.message, 'provider failed');
  assert.equal(error?.code, 'UPSTREAM');
});

for (const abortCode of ['abort', 'STOPPED']) {
  test(`suppresses ${abortCode} terminals while flushing buffers and closing steps`, async () => {
    const threadId = randomUUID();
    const runId = randomUUID();
    const agent = new ScriptedAgent(threadId, () =>
      of(
        runStarted(threadId, runId),
        { type: EventType.STEP_STARTED, stepName: 'analysis' },
        {
          type: EventType.TEXT_MESSAGE_START,
          messageId: 'm1',
          role: 'assistant',
        },
        {
          type: EventType.TEXT_MESSAGE_CONTENT,
          messageId: 'm1',
          delta: 'partial',
        },
        {
          type: EventType.TOOL_CALL_START,
          toolCallId: 'tc1',
          toolCallName: 'run_code',
        },
        {
          type: EventType.TOOL_CALL_ARGS,
          toolCallId: 'tc1',
          delta: '{"x":1}',
        },
        { type: EventType.RUN_ERROR, message: 'aborted', code: abortCode },
      ),
    ).use(new WotbotEventMiddleware());

    const events = await collectAgentRun(agent, runId);

    assert.deepEqual(eventTypes(events), [
      EventType.RUN_STARTED,
      EventType.STEP_STARTED,
      EventType.TEXT_MESSAGE_START,
      EventType.TEXT_MESSAGE_CONTENT,
      EventType.TOOL_CALL_START,
      EventType.TOOL_CALL_ARGS,
      EventType.STEP_FINISHED,
    ]);
  });
}

test('keeps concurrent runs isolated when they share a middleware instance', async () => {
  const middleware = new WotbotEventMiddleware(10_000);
  const threadA = randomUUID();
  const threadB = randomUUID();
  const runA = randomUUID();
  const runB = randomUUID();
  const sourceA = new ReplaySubject<BaseEvent>();
  const sourceB = new ReplaySubject<BaseEvent>();
  const agentA = new ScriptedAgent(threadA, () => sourceA).use(middleware);
  const agentB = new ScriptedAgent(threadB, () => sourceB).use(middleware);

  const promiseA = collectAgentRun(agentA, runA);
  const promiseB = collectAgentRun(agentB, runB);

  sourceA.next(runStarted(threadA, runA));
  sourceA.next({
    type: EventType.TEXT_MESSAGE_START,
    messageId: 'm-a',
    role: 'assistant',
  });
  sourceA.next({
    type: EventType.TEXT_MESSAGE_CONTENT,
    messageId: 'm-a',
    delta: 'alpha',
  });
  sourceB.next(runStarted(threadB, runB));
  sourceB.next({
    type: EventType.TEXT_MESSAGE_START,
    messageId: 'm-b',
    role: 'assistant',
  });
  sourceB.next({
    type: EventType.TEXT_MESSAGE_CONTENT,
    messageId: 'm-b',
    delta: 'beta',
  });
  sourceB.next({ type: EventType.TEXT_MESSAGE_END, messageId: 'm-b' });
  sourceB.next(runFinished(threadB, runB));
  sourceB.complete();
  sourceA.next({ type: EventType.TEXT_MESSAGE_END, messageId: 'm-a' });
  sourceA.next(runFinished(threadA, runA));
  sourceA.complete();

  const [eventsA, eventsB] = await Promise.all([promiseA, promiseB]);
  assert.equal(
    eventsA.find((event) => event.type === EventType.TEXT_MESSAGE_CONTENT)
      ?.delta,
    'alpha',
  );
  assert.equal(
    eventsB.find((event) => event.type === EventType.TEXT_MESSAGE_CONTENT)
      ?.delta,
    'beta',
  );
});

test('InMemoryAgentRunner finalizes a stopped run and replays canonical history', async () => {
  const threadId = `middleware-stop-${randomUUID()}`;
  const runId = randomUUID();
  const agent = new AbortableAgent(threadId).use(
    new WotbotEventMiddleware(),
  ) as AbortableAgent;
  const runner = new InMemoryAgentRunner();
  const events: BaseEvent[] = [];

  const completed = new Promise<void>((resolve, reject) => {
    runner
      .run({ threadId, agent, input: runInput(threadId, runId) })
      .subscribe({
        next: (event) => events.push(event),
        error: reject,
        complete: resolve,
      });
  });

  agent.events.next(runStarted(threadId, runId));
  agent.events.next({ type: EventType.STEP_STARTED, stepName: 'analysis' });
  agent.events.next({
    type: EventType.TEXT_MESSAGE_START,
    messageId: 'm1',
    role: 'assistant',
  });
  agent.events.next({
    type: EventType.TEXT_MESSAGE_CONTENT,
    messageId: 'm1',
    delta: 'partial answer',
  });
  agent.events.next({
    type: EventType.TOOL_CALL_START,
    toolCallId: 'tc1',
    toolCallName: 'run_code',
  });
  agent.events.next({
    type: EventType.TOOL_CALL_ARGS,
    toolCallId: 'tc1',
    delta: '{"code":"print(1)"}',
  });

  assert.equal(await runner.stop({ threadId }), true);
  await completed;

  assert.equal(
    events.some((event) => event.type === EventType.RUN_ERROR),
    false,
  );
  assert.equal(events.at(-1)?.type, EventType.RUN_FINISHED);
  assert.equal(
    events.some((event) => {
      if (event.type !== EventType.TOOL_CALL_RESULT) {
        return false;
      }
      const result = event as ToolCallResultEvent;
      return (
        result.toolCallId === 'tc1' &&
        JSON.parse(result.content).status === 'stopped'
      );
    }),
    true,
  );
  assertTerminalScopesClosed(events);

  const replayed: BaseEvent[] = [];
  await new Promise<void>((resolve, reject) => {
    runner.connect({ threadId }).subscribe({
      next: (event) => replayed.push(event),
      error: reject,
      complete: resolve,
    });
  });
  assert.deepEqual(replayed, compactEvents(events));
});

test('WotbotAgentRunner keeps steps live and removes them from replay', async () => {
  const threadId = `runner-replay-${randomUUID()}`;
  const runId = randomUUID();
  const agent = new ScriptedAgent(threadId, () =>
    of(
      runStarted(threadId, runId),
      { type: EventType.STEP_STARTED, stepName: 'control_llm' },
      {
        type: EventType.TEXT_MESSAGE_START,
        messageId: 'm1',
        role: 'assistant',
      },
      {
        type: EventType.TEXT_MESSAGE_CONTENT,
        messageId: 'm1',
        delta: 'panel ready',
      },
      { type: EventType.TEXT_MESSAGE_END, messageId: 'm1' },
      { type: EventType.STEP_FINISHED, stepName: 'control_llm' },
      runFinished(threadId, runId),
    ),
  );
  const runner = new WotbotAgentRunner();
  const liveEvents: BaseEvent[] = [];

  await new Promise<void>((resolve, reject) => {
    runner
      .run({ threadId, agent, input: runInput(threadId, runId) })
      .subscribe({
        next: (event) => liveEvents.push(event),
        error: reject,
        complete: resolve,
      });
  });

  assert.equal(
    liveEvents.some((event) => event.type === EventType.STEP_STARTED),
    true,
  );
  assert.equal(
    liveEvents.some((event) => event.type === EventType.STEP_FINISHED),
    true,
  );

  const replayedEvents: BaseEvent[] = [];
  await new Promise<void>((resolve, reject) => {
    runner.connect({ threadId }).subscribe({
      next: (event) => replayedEvents.push(event),
      error: reject,
      complete: resolve,
    });
  });

  assert.equal(
    replayedEvents.some(
      (event) =>
        event.type === EventType.STEP_STARTED ||
        event.type === EventType.STEP_FINISHED,
    ),
    false,
  );
  assert.equal(replayedEvents[0]?.type, EventType.RUN_STARTED);
  assert.equal(replayedEvents.at(-1)?.type, EventType.RUN_FINISHED);
});

test('InMemoryAgentRunner turns terminal-free completion into a valid error', async () => {
  const threadId = `middleware-complete-${randomUUID()}`;
  const runId = randomUUID();
  const agent = new ScriptedAgent(threadId, () =>
    of(
      runStarted(threadId, runId),
      { type: EventType.STEP_STARTED, stepName: 'analysis' },
      {
        type: EventType.TEXT_MESSAGE_START,
        messageId: 'm1',
        role: 'assistant',
      },
      {
        type: EventType.TEXT_MESSAGE_CONTENT,
        messageId: 'm1',
        delta: 'partial',
      },
    ),
  ).use(new WotbotEventMiddleware());
  const runner = new InMemoryAgentRunner();
  const events: BaseEvent[] = [];

  await new Promise<void>((resolve, reject) => {
    runner
      .run({ threadId, agent, input: runInput(threadId, runId) })
      .subscribe({
        next: (event) => events.push(event),
        error: reject,
        complete: resolve,
      });
  });

  assert.deepEqual(eventTypes(events).slice(-3), [
    EventType.STEP_FINISHED,
    EventType.TEXT_MESSAGE_END,
    EventType.RUN_ERROR,
  ]);
  const terminal = events.at(-1);
  assert.equal(terminal?.type, EventType.RUN_ERROR);
  assert.equal(terminal?.code, 'INCOMPLETE_STREAM');
});

test('InMemoryAgentRunner finalizes a source error after buffered tool args', async (t) => {
  t.mock.method(console, 'error', () => undefined);
  const threadId = `middleware-error-${randomUUID()}`;
  const runId = randomUUID();
  const sourceError = new Error('socket failed');
  const agent = new ScriptedAgent(
    threadId,
    () =>
      new Observable<BaseEvent>((subscriber) => {
        subscriber.next(runStarted(threadId, runId));
        subscriber.next({
          type: EventType.TOOL_CALL_START,
          toolCallId: 'tc1',
          toolCallName: 'run_code',
        });
        subscriber.next({
          type: EventType.TOOL_CALL_ARGS,
          toolCallId: 'tc1',
          delta: '{"code":"x"}',
        });
        // Match the network stream's asynchronous failure. A synchronous
        // source error can cancel AbstractAgent's async event-application
        // queue before the preceding events reach the runner.
        const errorTimer = setTimeout(() => subscriber.error(sourceError), 0);
        return () => clearTimeout(errorTimer);
      }),
  ).use(new WotbotEventMiddleware());
  const runner = new InMemoryAgentRunner();
  const events: BaseEvent[] = [];

  await new Promise<void>((resolve, reject) => {
    runner
      .run({ threadId, agent, input: runInput(threadId, runId) })
      .subscribe({
        next: (event) => events.push(event),
        error: reject,
        complete: resolve,
      });
  });

  assert.deepEqual(eventTypes(events).slice(-4), [
    EventType.TOOL_CALL_ARGS,
    EventType.TOOL_CALL_END,
    EventType.TOOL_CALL_RESULT,
    EventType.RUN_ERROR,
  ]);
  const terminal = events.at(-1);
  assert.equal(terminal?.type, EventType.RUN_ERROR);
  assert.equal(terminal?.message, 'socket failed');
  assert.equal(terminal?.code, 'INCOMPLETE_STREAM');
});
