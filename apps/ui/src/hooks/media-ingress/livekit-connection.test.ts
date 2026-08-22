import assert from 'node:assert/strict';
import test from 'node:test';

import {
  CAMERA_SNAPSHOT_TOPIC,
  handleCameraSnapshotDataEvent,
  INITIAL_VOICE_MEDIA_CONSTRAINTS,
} from './livekit-connection';

const encoder = new TextEncoder();

test('voice sessions request microphone access without enabling the camera', () => {
  assert.equal(INITIAL_VOICE_MEDIA_CONSTRAINTS.video, false);
  assert.notEqual(INITIAL_VOICE_MEDIA_CONSTRAINTS.audio, false);
});

function snapshotPayload(value: unknown) {
  return encoder.encode(JSON.stringify(value));
}

test('camera snapshot data event triggers the snapshot cue callback', () => {
  let cueCount = 0;

  const handled = handleCameraSnapshotDataEvent({
    payload: snapshotPayload({
      type: 'camera_snapshot_sent',
      capturedAt: '2026-06-16T09:00:00+00:00',
    }),
    participantInfo: { identity: 'agent-wotbot' },
    topic: CAMERA_SNAPSHOT_TOPIC,
    onCameraSnapshotSent: () => {
      cueCount += 1;
    },
  });

  assert.equal(handled, true);
  assert.equal(cueCount, 1);
});

test('camera snapshot data event ignores wrong topic', () => {
  let cueCount = 0;

  const handled = handleCameraSnapshotDataEvent({
    payload: snapshotPayload({
      type: 'camera_snapshot_sent',
      capturedAt: '2026-06-16T09:00:00+00:00',
    }),
    participantInfo: { identity: 'agent-wotbot' },
    topic: 'wotbot.other',
    onCameraSnapshotSent: () => {
      cueCount += 1;
    },
  });

  assert.equal(handled, false);
  assert.equal(cueCount, 0);
});

test('camera snapshot data event ignores malformed JSON', () => {
  let cueCount = 0;

  const handled = handleCameraSnapshotDataEvent({
    payload: encoder.encode('{nope'),
    participantInfo: { identity: 'agent-wotbot' },
    topic: CAMERA_SNAPSHOT_TOPIC,
    onCameraSnapshotSent: () => {
      cueCount += 1;
    },
  });

  assert.equal(handled, false);
  assert.equal(cueCount, 0);
});

test('camera snapshot data event ignores non-agent senders', () => {
  let cueCount = 0;

  const handled = handleCameraSnapshotDataEvent({
    payload: snapshotPayload({
      type: 'camera_snapshot_sent',
      capturedAt: '2026-06-16T09:00:00+00:00',
    }),
    participantInfo: { identity: 'web-user' },
    topic: CAMERA_SNAPSHOT_TOPIC,
    onCameraSnapshotSent: () => {
      cueCount += 1;
    },
  });

  assert.equal(handled, false);
  assert.equal(cueCount, 0);
});
