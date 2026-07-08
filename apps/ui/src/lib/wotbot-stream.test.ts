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
