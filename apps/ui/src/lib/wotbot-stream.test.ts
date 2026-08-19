import test from 'node:test';
import assert from 'node:assert/strict';

import { filterWotbotEventStream } from './wotbot-stream';

function sse(event: Record<string, unknown>): string {
  return `data: ${JSON.stringify(event)}\n\n`;
}

async function readStream(stream: ReadableStream<Uint8Array>): Promise<string> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let output = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      return output;
    }

    output += decoder.decode(value, { stream: true });
  }
}

function makeSource(input: string): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(input));
      controller.close();
    },
  });
}

test('drops RAW events and keeps renderable ones', async () => {
  const input =
    sse({ type: 'RAW', event: { event: 'on_chain_start' } }) +
    sse({ type: 'TEXT_MESSAGE_START', messageId: 'm1', role: 'assistant' }) +
    sse({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm1', delta: 'Hello' }) +
    sse({ type: 'TEXT_MESSAGE_END', messageId: 'm1' });

  const output = await readStream(filterWotbotEventStream(makeSource(input)));

  assert.doesNotMatch(output, /"type":"RAW"/);
  assert.match(output, /"type":"TEXT_MESSAGE_START"/);
  assert.match(output, /Hello/);
  assert.match(output, /"type":"TEXT_MESSAGE_END"/);
});

test('preserves partial SSE chunks split across reads', async () => {
  const chunks = [
    'data: {"type":"RAW","event":{"event":"on_chain_start"}}\n',
    '\ndata: {"type":"RUN_STARTED"}\n\n',
  ];

  const source = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });

  const output = await readStream(filterWotbotEventStream(source));
  assert.match(output, /"type":"RUN_STARTED"/);
  assert.doesNotMatch(output, /RAW/);
});

test('handles string chunks from the runtime', async () => {
  const source = new ReadableStream<string>({
    start(controller) {
      controller.enqueue(
        sse({ type: 'RUN_STARTED' }) +
          sse({ type: 'RAW', event: { event: 'on_chain_end' } }),
      );
      controller.close();
    },
  });

  const output = await readStream(filterWotbotEventStream(source));
  assert.match(output, /"type":"RUN_STARTED"/);
  assert.doesNotMatch(output, /RAW/);
});

test('batches TOOL_CALL_ARGS into a single complete event at TOOL_CALL_END', async () => {
  const input =
    sse({
      type: 'TOOL_CALL_START',
      toolCallId: 'tc1',
      toolCallName: 'run_code',
    }) +
    sse({ type: 'TOOL_CALL_ARGS', toolCallId: 'tc1', delta: '{"co' }) +
    sse({ type: 'TOOL_CALL_ARGS', toolCallId: 'tc1', delta: 'de":"' }) +
    sse({ type: 'TOOL_CALL_ARGS', toolCallId: 'tc1', delta: 'x"}' }) +
    sse({ type: 'TOOL_CALL_END', toolCallId: 'tc1' });

  const output = await readStream(filterWotbotEventStream(makeSource(input)));

  const argsMatches = output.match(/"type":"TOOL_CALL_ARGS"/g);
  assert.equal(argsMatches?.length, 1);
  assert.match(output, /\{\\"code\\":\\"x\\"\}/);
  assert.match(output, /"type":"TOOL_CALL_START"/);
  assert.match(output, /"type":"TOOL_CALL_END"/);
});

test('forwards complete TOOL_CALL_RESULT content but strips rawEvent', async () => {
  const input =
    sse({
      type: 'TOOL_CALL_START',
      toolCallId: 'tc1',
      toolCallName: 'run_code',
    }) +
    sse({
      type: 'TOOL_CALL_RESULT',
      messageId: 'tool-1',
      toolCallId: 'tc1',
      content: '{"stdout":"complete output"}',
      rawEvent: { hidden: 'raw payload' },
    });

  const output = await readStream(filterWotbotEventStream(makeSource(input)));

  assert.match(output, /"type":"TOOL_CALL_RESULT"/);
  assert.match(output, /complete output/);
  assert.doesNotMatch(output, /raw payload/);
});

test('preserves TOOL_CALL_CHUNK when it is the sole tool call carrier', async () => {
  const input =
    sse({
      type: 'TOOL_CALL_CHUNK',
      toolCallId: 'tc1',
      toolCallName: 'things_search',
      parentMessageId: 'assistant-1',
      delta: '{"query"',
      rawEvent: { hidden: 'raw chunk' },
    }) +
    sse({
      type: 'TOOL_CALL_CHUNK',
      toolCallId: 'tc1',
      delta: ':"temperature"}',
    });

  const output = await readStream(filterWotbotEventStream(makeSource(input)));

  const chunkMatches = output.match(/"type":"TOOL_CALL_CHUNK"/g);
  assert.equal(chunkMatches?.length, 2);
  assert.match(output, /things_search/);
  assert.match(output, /assistant-1/);
  assert.match(output, /\{\\"query\\"/);
  assert.match(output, /:\\"temperature\\"\}/);
  assert.doesNotMatch(output, /raw chunk/);
});

test('throttles TEXT_MESSAGE_CONTENT deltas into batches', async () => {
  const input =
    sse({ type: 'TEXT_MESSAGE_START', messageId: 'm1', role: 'assistant' }) +
    sse({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm1', delta: 'Hello' }) +
    sse({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm1', delta: ' world' }) +
    sse({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm1', delta: '!' }) +
    sse({ type: 'TEXT_MESSAGE_END', messageId: 'm1' });

  const output = await readStream(filterWotbotEventStream(makeSource(input)));

  // All text deltas delivered synchronously should be merged into one
  // (the TEXT_MESSAGE_END forces a flush of pending text)
  const contentMatches = output.match(/"type":"TEXT_MESSAGE_CONTENT"/g);
  assert.equal(contentMatches?.length, 1);
  assert.match(output, /Hello world!/);
});

test('flushes pending text before non-text events to preserve ordering', async () => {
  const input =
    sse({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm1', delta: 'partial' }) +
    sse({ type: 'TOOL_CALL_START', toolCallId: 'tc1', toolCallName: 'foo' }) +
    sse({ type: 'TOOL_CALL_END', toolCallId: 'tc1' });

  const output = await readStream(filterWotbotEventStream(makeSource(input)));

  // Text should appear before tool call start
  const textIdx = output.indexOf('"TEXT_MESSAGE_CONTENT"');
  const toolIdx = output.indexOf('"TOOL_CALL_START"');
  assert.ok(
    textIdx < toolIdx,
    'text content should come before tool call start',
  );
  assert.match(output, /partial/);
});

function eventTypes(output: string): string[] {
  return output
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => {
      try {
        return (JSON.parse(line.slice(5)) as { type?: string }).type ?? '?';
      } catch {
        return '?';
      }
    });
}

test('rewrites a user-initiated abort into a clean RUN_FINISHED', async () => {
  // A stop is a normal end of the run, not a failure -- left as RUN_ERROR
  // the user gets an error toast ("This operation was aborted"). The open
  // text message and step must be closed first, since the client's own
  // validator refuses RUN_FINISHED while either is still active.
  const input =
    sse({ type: 'RUN_STARTED', threadId: 't1', runId: 'r1' }) +
    sse({ type: 'STEP_STARTED', stepName: 'respond' }) +
    sse({ type: 'TEXT_MESSAGE_START', messageId: 'm1', role: 'assistant' }) +
    sse({
      type: 'TEXT_MESSAGE_CONTENT',
      messageId: 'm1',
      delta: 'partial answer',
    }) +
    sse({
      type: 'RUN_ERROR',
      message: 'This operation was aborted',
      code: 'abort',
    });

  const output = await readStream(filterWotbotEventStream(makeSource(input)));

  assert.doesNotMatch(output, /"type":"RUN_ERROR"/);
  assert.doesNotMatch(output, /This operation was aborted/);
  assert.match(
    output,
    /partial answer/,
    'text streamed before the stop should be kept',
  );
  assert.deepEqual(eventTypes(output), [
    'RUN_STARTED',
    'STEP_STARTED',
    'TEXT_MESSAGE_START',
    'TEXT_MESSAGE_CONTENT',
    'TEXT_MESSAGE_END',
    'STEP_FINISHED',
    'RUN_FINISHED',
  ]);
  assert.match(output, /"threadId":"t1"/);
  assert.match(output, /"runId":"r1"/);
});

test('closes an open tool call when the run is aborted', async () => {
  const input =
    sse({ type: 'RUN_STARTED', threadId: 't1', runId: 'r1' }) +
    sse({
      type: 'TOOL_CALL_START',
      toolCallId: 'tc1',
      toolCallName: 'run_code',
    }) +
    sse({ type: 'TOOL_CALL_ARGS', toolCallId: 'tc1', delta: '{"code":"x"}' }) +
    sse({ type: 'RUN_ERROR', message: 'aborted', code: 'abort' });

  const output = await readStream(filterWotbotEventStream(makeSource(input)));

  assert.deepEqual(eventTypes(output), [
    'RUN_STARTED',
    'TOOL_CALL_START',
    'TOOL_CALL_ARGS',
    'TOOL_CALL_END',
    'RUN_FINISHED',
  ]);
  assert.match(
    output,
    /\{\\"code\\":\\"x\\"\}/,
    'buffered args should be flushed',
  );
});

test('closes a dangling tool call before forwarding the upstream RUN_FINISHED', async () => {
  // ag_ui_langgraph's event loop exits early (its error branch breaks, or the
  // graph stream just ends) and then falls through to emit
  // STEP_FINISHED/snapshots/RUN_FINISHED without ever closing a tool call
  // that was still mid-flight. The client rejects that with "Cannot send
  // 'RUN_FINISHED' while tool calls are still active: <id>".
  const input =
    sse({ type: 'RUN_STARTED', threadId: 't1', runId: 'r1' }) +
    sse({ type: 'STEP_STARTED', stepName: 'analysis' }) +
    sse({
      type: 'TOOL_CALL_START',
      toolCallId: 'call_dRJ9G4ShZFy02bqVa9X5GXyC',
      toolCallName: 'run_code',
    }) +
    sse({
      type: 'TOOL_CALL_ARGS',
      toolCallId: 'call_dRJ9G4ShZFy02bqVa9X5GXyC',
      delta: '{"code":"pri',
    }) +
    sse({ type: 'RUN_FINISHED', threadId: 't1', runId: 'r1' });

  const output = await readStream(filterWotbotEventStream(makeSource(input)));

  assert.deepEqual(eventTypes(output), [
    'RUN_STARTED',
    'STEP_STARTED',
    'TOOL_CALL_START',
    'TOOL_CALL_ARGS',
    'TOOL_CALL_END',
    'STEP_FINISHED',
    'RUN_FINISHED',
  ]);
  const finishedIdx = output.indexOf('"RUN_FINISHED"');
  const toolEndIdx = output.indexOf('"TOOL_CALL_END"');
  assert.ok(
    toolEndIdx < finishedIdx,
    'tool call must be closed before RUN_FINISHED',
  );
});

test('keeps replaying runs after the first one finishes', async () => {
  // A replayed thread history is several complete runs back to back; the
  // end-of-run bookkeeping must not swallow everything after run one.
  const input =
    sse({ type: 'RUN_STARTED', threadId: 't1', runId: 'r1' }) +
    sse({ type: 'TEXT_MESSAGE_START', messageId: 'm1', role: 'assistant' }) +
    sse({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm1', delta: 'first' }) +
    sse({ type: 'TEXT_MESSAGE_END', messageId: 'm1' }) +
    sse({ type: 'RUN_FINISHED', threadId: 't1', runId: 'r1' }) +
    sse({ type: 'RUN_STARTED', threadId: 't1', runId: 'r2' }) +
    sse({ type: 'TEXT_MESSAGE_START', messageId: 'm2', role: 'assistant' }) +
    sse({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm2', delta: 'second' }) +
    sse({ type: 'TEXT_MESSAGE_END', messageId: 'm2' }) +
    sse({ type: 'RUN_FINISHED', threadId: 't1', runId: 'r2' });

  const output = await readStream(filterWotbotEventStream(makeSource(input)));

  assert.match(output, /first/);
  assert.match(output, /second/, 'the second run must not be dropped');
  assert.equal(eventTypes(output).filter((t) => t === 'RUN_STARTED').length, 2);
  assert.equal(
    eventTypes(output).filter((t) => t === 'RUN_FINISHED').length,
    2,
  );
});

test('leaves a genuine (non-abort) RUN_ERROR as an error', async () => {
  const input =
    sse({ type: 'RUN_STARTED', threadId: 't1', runId: 'r1' }) +
    sse({ type: 'RUN_ERROR', message: 'Unknown error' }) +
    sse({ type: 'STEP_FINISHED', stepName: 'respond' });

  const output = await readStream(filterWotbotEventStream(makeSource(input)));

  assert.match(output, /"type":"RUN_ERROR"/);
  assert.match(output, /Unknown error/);
  assert.doesNotMatch(output, /"type":"RUN_FINISHED"/);
  assert.doesNotMatch(output, /"type":"STEP_FINISHED"/);
});

test('drops events split across separate reads after RUN_FINISHED', async () => {
  const chunks = [
    sse({ type: 'RUN_FINISHED' }),
    sse({ type: 'TEXT_MESSAGE_END', messageId: 'm1' }),
  ];

  const source = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });

  const output = await readStream(filterWotbotEventStream(source));

  assert.match(output, /"type":"RUN_FINISHED"/);
  assert.doesNotMatch(output, /"type":"TEXT_MESSAGE_END"/);
});
