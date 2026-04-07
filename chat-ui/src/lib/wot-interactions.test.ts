import assert from 'node:assert/strict';
import test from 'node:test';

import type { Message } from '@ag-ui/core';

import {
  getLastTurnWotInteractions,
  parseWotInteractionList,
} from './wot-interactions';

test('parseWotInteractionList reads stringified run_code output', () => {
  const interactions = parseWotInteractionList(
    JSON.stringify({
      stdout: 'done',
      wot_calls: [
        {
          type: 'write_property',
          thing_id: 'urn:smart-living:thing:kitchen-thermometer',
          name: 'targetTemperature',
          ok: true,
          uri_variables: { zone: 'north' },
          value: 22,
        },
      ],
    }),
  );

  assert.deepEqual(interactions, [
    {
      affordanceName: 'targetTemperature',
      ok: true,
      thingId: 'urn:smart-living:thing:kitchen-thermometer',
      type: 'write_property',
      uriVariables: { zone: 'north' },
      value: 22,
    },
  ]);
});

test('getLastTurnWotInteractions preserves direct tool inputs and uri variables', () => {
  const messages: Message[] = [
    {
      id: 'user-1',
      role: 'user',
      content: 'Toggle the hallway light',
    },
    {
      id: 'assistant-1',
      role: 'assistant',
      content: '',
      toolCalls: [
        {
          id: 'tool-1',
          type: 'function',
          function: {
            name: 'wot_invoke_action',
            arguments: JSON.stringify({
              action_name: 'setState',
              input: { on: true },
              thing_id: 'urn:smart-living:thing:hallway-light',
              uri_variables: { channel: 2 },
            }),
          },
        },
      ],
    },
    {
      id: 'tool-result-1',
      role: 'tool',
      toolCallId: 'tool-1',
      content: '{"ok":true}',
    },
  ];

  assert.deepEqual(getLastTurnWotInteractions(messages), [
    {
      affordanceName: 'setState',
      input: { on: true },
      ok: true,
      thingId: 'urn:smart-living:thing:hallway-light',
      type: 'invoke_action',
      uriVariables: { channel: 2 },
    },
  ]);
});

test('getLastTurnWotInteractions returns only the latest turn interactions', () => {
  const messages: Message[] = [
    {
      id: 'user-1',
      role: 'user',
      content: 'Turn on the hallway light',
    },
    {
      id: 'assistant-1',
      role: 'assistant',
      content: '',
      toolCalls: [
        {
          id: 'tool-1',
          type: 'function',
          function: {
            name: 'wot_invoke_action',
            arguments: JSON.stringify({
              thing_id: 'urn:smart-living:thing:hallway-light',
              action_name: 'toggle',
            }),
          },
        },
      ],
    },
    {
      id: 'tool-result-1',
      role: 'tool',
      toolCallId: 'tool-1',
      content: '{"ok":true}',
    },
    {
      id: 'user-2',
      role: 'user',
      content: 'What data did you use?',
    },
    {
      id: 'assistant-2',
      role: 'assistant',
      content: '',
      toolCalls: [
        {
          id: 'tool-2',
          type: 'function',
          function: {
            name: 'run_code',
            arguments: JSON.stringify({ code: 'print("ok")' }),
          },
        },
      ],
    },
    {
      id: 'tool-result-2',
      role: 'tool',
      toolCallId: 'tool-2',
      content: JSON.stringify({
        stdout: 'ok',
        wot_calls: [
          {
            type: 'read_property',
            thing_id: 'urn:smart-living:thing:kitchen-thermometer',
            name: 'temperature',
            ok: true,
          },
          {
            type: 'write_property',
            thing_id: 'urn:smart-living:thing:living-room-lamp',
            name: 'brightness',
            ok: false,
            uri_variables: { channel: 1 },
            value: 40,
          },
        ],
      }),
    },
  ];

  assert.deepEqual(getLastTurnWotInteractions(messages), [
    {
      affordanceName: 'temperature',
      ok: true,
      thingId: 'urn:smart-living:thing:kitchen-thermometer',
      type: 'read_property',
    },
    {
      affordanceName: 'brightness',
      ok: false,
      thingId: 'urn:smart-living:thing:living-room-lamp',
      type: 'write_property',
      uriVariables: { channel: 1 },
      value: 40,
    },
  ]);
});
