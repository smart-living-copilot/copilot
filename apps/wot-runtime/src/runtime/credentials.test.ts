import assert from 'node:assert/strict';
import test from 'node:test';

import {
  applyRuntimeSecrets,
  annotateThingDescriptionSecurityNames,
  resolveRuntimeCredentials,
  RUNTIME_SECURITY_NAME_FIELD,
} from './credentials.js';

test('annotateThingDescriptionSecurityNames tags definitions with their names', () => {
  const document: Record<string, unknown> = {
    securityDefinitions: {
      basic_sc: { scheme: 'basic' },
      token_sc: { scheme: 'bearer' },
    },
  };

  annotateThingDescriptionSecurityNames(document);

  const definitions = document.securityDefinitions as Record<string, Record<string, unknown>>;
  assert.equal(definitions.basic_sc[RUNTIME_SECURITY_NAME_FIELD], 'basic_sc');
  assert.equal(definitions.token_sc[RUNTIME_SECURITY_NAME_FIELD], 'token_sc');
});

test('resolveRuntimeCredentials prefers security-name matches', () => {
  const secrets = {
    entries: [
      {
        security_name: 'basic_sc',
        scheme: 'basic',
        credentials: {
          username: 'demo-user',
          password: 'demo-pass',
        },
      },
      {
        security_name: 'token_sc',
        scheme: 'bearer',
        credentials: {
          token: 'demo-token',
        },
      },
    ],
  };

  assert.deepEqual(
    resolveRuntimeCredentials(
      [
        {
          scheme: 'bearer',
          [RUNTIME_SECURITY_NAME_FIELD]: 'token_sc',
        },
      ],
      [secrets],
    ),
    { token: 'demo-token' },
  );
});

test('resolveRuntimeCredentials falls back to an unambiguous scheme match', () => {
  const secrets = {
    entries: [
      {
        security_name: 'basic_sc',
        scheme: 'basic',
        credentials: {
          username: 'demo-user',
          password: 'demo-pass',
        },
      },
      {
        security_name: 'token_sc',
        scheme: 'bearer',
        credentials: {
          token: 'demo-token',
        },
      },
    ],
  };

  assert.deepEqual(resolveRuntimeCredentials([{ scheme: 'basic' }], secrets), {
    username: 'demo-user',
    password: 'demo-pass',
  });
});

test('resolveRuntimeCredentials rejects ambiguous scheme-only matches', () => {
  const secrets = {
    entries: [
      {
        security_name: 'basic_primary',
        scheme: 'basic',
        credentials: {
          username: 'demo-user',
          password: 'demo-pass',
        },
      },
      {
        security_name: 'basic_secondary',
        scheme: 'basic',
        credentials: {
          username: 'other-user',
          password: 'other-pass',
        },
      },
    ],
  };

  assert.throws(
    () => resolveRuntimeCredentials([{ scheme: 'basic' }], secrets),
    /Multiple credentials match security scheme 'basic'/,
  );
});

test('applyRuntimeSecrets replaces the existing credential store on refresh', () => {
  const credentialStore = new Map<string, unknown[]>([
    [
      'urn:thing:stale',
      [
        {
          entries: [
            {
              security_name: 'stale_sc',
              scheme: 'bearer',
              credentials: { token: 'stale-token' },
            },
          ],
        },
      ],
    ],
  ]);

  const target = {
    credentialStore,
    addCredentials(credentials: Record<string, unknown>) {
      for (const [thingId, value] of Object.entries(credentials)) {
        const current = credentialStore.get(thingId) ?? [];
        if (!credentialStore.has(thingId)) {
          credentialStore.set(thingId, current);
        }
        current.push(value);
      }
    },
  };

  applyRuntimeSecrets(target, {
    'urn:thing:fresh': {
      entries: [
        {
          security_name: 'fresh_sc',
          scheme: 'basic',
          credentials: {
            username: 'demo-user',
            password: 'demo-pass',
          },
        },
      ],
    },
  });

  assert.deepEqual([...credentialStore.keys()], ['urn:thing:fresh']);
  assert.deepEqual(credentialStore.get('urn:thing:fresh'), [
    {
      entries: [
        {
          security_name: 'fresh_sc',
          scheme: 'basic',
          credentials: {
            username: 'demo-user',
            password: 'demo-pass',
          },
        },
      ],
    },
  ]);
});
