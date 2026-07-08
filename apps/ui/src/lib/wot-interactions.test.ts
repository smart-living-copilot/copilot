import assert from 'node:assert/strict';
import test from 'node:test';

import {
  DEVICE_INTERACTION_SUMMARY_TYPE,
  parseDeviceInteractionSummaryContent,
  parseWotInteractionList,
} from './wot-interactions';

test('parseWotInteractionList reads stringified run_code output', () => {
  const interactions = parseWotInteractionList(
    JSON.stringify({
      stdout: 'done',
      wot_calls: [
        {
          type: 'write_property',
          thing_id: 'urn:wotbot:thing:kitchen-thermometer',
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
      thingId: 'urn:wotbot:thing:kitchen-thermometer',
      type: 'write_property',
      uriVariables: { zone: 'north' },
      value: 22,
    },
  ]);
});

test('parseDeviceInteractionSummaryContent reads graph summary marker content', () => {
  assert.deepEqual(
    parseDeviceInteractionSummaryContent(
      JSON.stringify({
        type: DEVICE_INTERACTION_SUMMARY_TYPE,
        interactions: [
          {
            type: 'write_property',
            thingId: 'urn:wotbot:thing:living-room-lamp',
            affordanceName: 'brightness',
            ok: true,
            uriVariables: { channel: 1 },
            value: 40,
          },
        ],
      }),
    ),
    [
      {
        affordanceName: 'brightness',
        ok: true,
        thingId: 'urn:wotbot:thing:living-room-lamp',
        type: 'write_property',
        uriVariables: { channel: 1 },
        value: 40,
      },
    ],
  );
});
