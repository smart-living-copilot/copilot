import assert from 'node:assert/strict';
import test from 'node:test';

import { parseCredentialChallenge } from './credential-interrupt-card';
import { parseSourceRegistrationInterrupt } from './source-registration-interrupt-card';

test('credential interrupts expose only the secure dialog routing fields', () => {
  assert.deepEqual(
    parseCredentialChallenge({
      kind: 'credential',
      status: 'credential_required',
      thing_id: 'urn:source',
      security_name: 'source_sc',
      scheme: 'apikey',
      message: 'Credentials required.',
    }),
    {
      kind: 'credential',
      status: 'credential_required',
      owner_kind: 'thing',
      thing_id: 'urn:source',
      security_name: 'source_sc',
      scheme: 'apikey',
      message: 'Credentials required.',
    },
  );
  assert.deepEqual(
    parseCredentialChallenge({
      kind: 'credential',
      status: 'credential_rejected',
      owner_kind: 'source',
      source_id: 'urn:source',
      security_name: 'source_sc',
      scheme: 'bearer',
      token: 'must-not-escape',
    }),
    {
      kind: 'credential',
      status: 'credential_rejected',
      owner_kind: 'source',
      source_id: 'urn:source',
      security_name: 'source_sc',
      scheme: 'bearer',
    },
  );
  assert.equal(
    parseCredentialChallenge({ kind: 'credential', token: 'secret' }),
    null,
  );
});

test('source registration interrupts expose no credential values', () => {
  assert.deepEqual(
    parseSourceRegistrationInterrupt({
      kind: 'source_registration',
      draft: {
        url: 'http://localhost:8080',
        provider: 'toolhive',
        tags: ['MCP'],
        token: 'must-not-escape',
      },
    }),
    {
      kind: 'source_registration',
      draft: {
        url: 'http://localhost:8080',
        provider: 'toolhive',
        tags: ['MCP'],
      },
    },
  );
});
