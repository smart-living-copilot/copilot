import assert from 'node:assert/strict';
import test from 'node:test';

import { parseProviderActionTarget } from './form.js';

test('provider action forms carry only a local encoded Thing target', () => {
  const thingId = 'urn:wotbot:external:edc-v3:abc';
  const encoded = Buffer.from(thingId).toString('base64url');
  assert.deepEqual(
    parseProviderActionTarget({ href: `wotbot+provider://runtime/things/${encoded}/actions/acquire` } as any),
    { thingId, action: 'acquire' },
  );
});

test('provider action forms cannot choose an HTTP destination', () => {
  assert.throws(
    () => parseProviderActionTarget({ href: 'wotbot+provider://attacker.example/things/a/actions/acquire' } as any),
    /local runtime/,
  );
});

test('provider action forms reject extra authority and routing components', () => {
  const encoded = Buffer.from('urn:test:thing').toString('base64url');
  for (const href of [
    `wotbot+provider://runtime:1234/things/${encoded}/actions/acquire`,
    `wotbot+provider://user@runtime/things/${encoded}/actions/acquire`,
    `wotbot+provider://runtime/things/${encoded}/actions/acquire?target=elsewhere`,
    `wotbot+provider://runtime/things/${encoded}/actions/acquire#target`,
  ]) {
    assert.throws(() => parseProviderActionTarget({ href } as any), /unsupported URL components/);
  }
});
