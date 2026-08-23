import assert from 'node:assert/strict';
import test from 'node:test';

import { getPanelOrigin, isPanelHostname, toPanelLabel } from './panel-origin';

const local = { protocol: 'http:', hostname: 'localhost', port: '3000' };
const prod = { protocol: 'https:', hostname: 'wotbot.example.com', port: '' };

test('a panel id becomes its own subdomain', () => {
  assert.equal(
    getPanelOrigin('39ecb1f12b2146ffb42783f71d5e144a', local, undefined),
    'http://39ecb1f12b2146ffb42783f71d5e144a.panels.localhost:3000',
  );
});

test('each panel gets a different origin', () => {
  // The point of per-panel origins: a camera grant for one must not arm another.
  assert.notEqual(
    getPanelOrigin('panel-a', local, undefined),
    getPanelOrigin('panel-b', local, undefined),
  );
});

test('a filename collapses to a single DNS label', () => {
  // A wildcard certificate matches one label, so dots must not survive.
  const origin = getPanelOrigin('wot_interface.abc.html', prod, undefined);
  const label = origin.replace('https://', '').split('.panels.')[0];

  assert.ok(!label.includes('.'), `label still dotted: ${label}`);
  assert.match(label, /^[a-z0-9-]+$/);
});

test('labels stay within the 63-character DNS limit', () => {
  assert.ok(toPanelLabel('x'.repeat(200)).length <= 63);
  assert.ok(!toPanelLabel(`${'x'.repeat(62)}-.html`).endsWith('-'));
});

test('an unusable key still yields a valid label', () => {
  assert.equal(toPanelLabel('...'), 'panel');
  assert.equal(toPanelLabel(''), 'panel');
});

test('a configured template places the key and keeps the port', () => {
  assert.equal(
    getPanelOrigin('abc', prod, '{key}.panels.example.com'),
    'https://abc.panels.example.com',
  );
  assert.equal(
    getPanelOrigin('abc', local, '{key}.sandbox.test'),
    'http://abc.sandbox.test:3000',
  );
});

test('server rendering yields no origin rather than a wrong one', () => {
  assert.equal(getPanelOrigin('abc', undefined, undefined), '');
});

test('panel hosts are told apart from the app host', () => {
  assert.equal(isPanelHostname('abc.panels.localhost', undefined), true);
  assert.equal(isPanelHostname('localhost', undefined), false);
  assert.equal(isPanelHostname('wotbot.example.com', undefined), false);
  // The bare suffix is not itself a panel host.
  assert.equal(
    isPanelHostname('panels.example.com', '{key}.panels.example.com'),
    false,
  );
  assert.equal(
    isPanelHostname('abc.panels.example.com', '{key}.panels.example.com'),
    true,
  );
});
