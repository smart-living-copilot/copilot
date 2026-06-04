import assert from 'node:assert/strict';
import test from 'node:test';

import {
  type AssistantMessage,
  type Message,
  type ToolCall,
} from '@ag-ui/core';

import {
  getGroupedToolCalls,
  isFirstToolOnlyMessageInGroup,
} from './grouped-tool-call-model';

function toolCall(id: string, name = 'things_search'): ToolCall {
  return {
    id,
    function: {
      arguments: '{}',
      name,
    },
    type: 'function',
  };
}

function toolOnlyAssistant(id: string, call: ToolCall): AssistantMessage {
  return {
    id,
    content: '',
    role: 'assistant',
    toolCalls: [call],
  };
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
  const messages: Message[] = [
    { id: 'user-1', content: 'show temperature', role: 'user' },
    first,
    {
      id: 'tool-1',
      content: '{}',
      role: 'tool',
      toolCallId: 'call-1',
    },
    second,
    {
      id: 'tool-2',
      content: '{}',
      role: 'tool',
      toolCallId: 'call-2',
    },
    third,
    {
      id: 'tool-3',
      content: '{}',
      role: 'tool',
      toolCallId: 'call-3',
    },
    { id: 'assistant-final', content: 'done', role: 'assistant' },
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
