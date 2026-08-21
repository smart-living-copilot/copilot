import assert from 'node:assert/strict';
import test from 'node:test';

import type { LangChainMessage } from '@/lib/thread-messages';

import {
  buildToolCallProps,
  getGroupedToolCalls,
  isFirstToolOnlyMessageInGroup,
} from './grouped-tool-call-model';

type ToolCall = NonNullable<LangChainMessage['tool_calls']>[number] & {
  id: string;
  name: string;
};

function toolCall(id: string, name = 'things_search'): ToolCall {
  return {
    id,
    args: {},
    name,
  };
}

function toolOnlyAssistant(id: string, call: ToolCall) {
  return {
    id,
    content: '',
    type: 'ai' as const,
    tool_calls: [call],
  } satisfies LangChainMessage;
}

test('groups consecutive tool-only assistant messages into one run', () => {
  const first = toolOnlyAssistant('assistant-1', toolCall('call-1'));
  const second = toolOnlyAssistant(
    'assistant-2',
    toolCall('call-2', 'run_code'),
  );
  const third = toolOnlyAssistant(
    'assistant-3',
    toolCall('call-3', 'run_code'),
  );
  const messages: LangChainMessage[] = [
    { id: 'user-1', content: 'show temperature', type: 'human' },
    first,
    {
      id: 'tool-1',
      content: '{}',
      type: 'tool',
      tool_call_id: 'call-1',
    },
    second,
    {
      id: 'tool-2',
      content: '{}',
      type: 'tool',
      tool_call_id: 'call-2',
    },
    third,
    {
      id: 'tool-3',
      content: '{}',
      type: 'tool',
      tool_call_id: 'call-3',
    },
    { id: 'assistant-final', content: 'done', type: 'ai' },
  ];

  assert.equal(
    isFirstToolOnlyMessageInGroup({ message: first, messages }),
    true,
  );
  assert.equal(
    isFirstToolOnlyMessageInGroup({ message: second, messages }),
    false,
  );
  assert.equal(
    isFirstToolOnlyMessageInGroup({ message: third, messages }),
    false,
  );

  assert.deepEqual(
    getGroupedToolCalls({ message: first, messages }).map((call) => call.id),
    ['call-1', 'call-2', 'call-3'],
  );
});

test('keeps complete tool args and results in renderer props', () => {
  const call = toolCall('call-1');
  call.args = { query: 'temperature' };

  const props = buildToolCallProps({
    executingToolCallIds: new Set(),
    toolCall: call,
    toolMessage: {
      id: 'tool-1',
      content: '{"result":"22 C"}',
      type: 'tool',
      tool_call_id: call.id,
    },
  });

  assert.deepEqual(props.args, { query: 'temperature' });
  assert.equal(props.result, '{"result":"22 C"}');
  assert.equal(props.status, 'complete');
});
