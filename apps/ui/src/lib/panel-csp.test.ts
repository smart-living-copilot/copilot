import assert from 'node:assert/strict';
import test from 'node:test';

import { PANEL_CSP } from './panel-csp';

function directive(name: string): string {
  const found = PANEL_CSP.split('; ').find((part) => part.startsWith(`${name} `));
  assert.ok(found, `expected a ${name} directive`);
  return found;
}

test('nothing loads by default', () => {
  assert.ok(PANEL_CSP.startsWith("default-src 'none'"));
});

test('no directive opens up to any host', () => {
  // The whole containment story rests on a panel never choosing its own host.
  // `*`, bare `https:`, or `data:` for scripts would each undo that.
  for (const part of PANEL_CSP.split('; ')) {
    assert.ok(!/\s\*/.test(part), `wildcard host in: ${part}`);
    assert.ok(!/\shttps:(\s|$)/.test(part), `scheme-wide source in: ${part}`);
  }
  assert.ok(!directive('script-src').includes('data:'));
});

test('styles and fonts may come from every host scripts may', () => {
  // A stylesheet from a host that can already serve executable JS grants
  // strictly less, and libraries ship their CSS beside their JS.
  for (const host of [
    'https://cdn.jsdelivr.net',
    'https://unpkg.com',
    'https://cdnjs.cloudflare.com',
  ]) {
    assert.ok(directive('script-src').includes(host), `script-src ${host}`);
    assert.ok(directive('style-src').includes(host), `style-src ${host}`);
    assert.ok(directive('font-src').includes(host), `font-src ${host}`);
  }
});

test('images are restricted to named hosts', () => {
  const imgSrc = directive('img-src');

  assert.ok(imgSrc.includes("'self'"));
  assert.ok(imgSrc.includes('data:'));
  assert.ok(imgSrc.includes('https://*.tile.openstreetmap.org'));
  // An arbitrary image URL is an exfiltration channel, so every source here
  // must be one the panel could not have chosen.
  for (const source of imgSrc.replace('img-src ', '').split(' ')) {
    assert.ok(
      source === "'self'" ||
        source === 'data:' ||
        // Captured camera stills are blob: URLs, which never leave the page.
        source === 'blob:' ||
        source.startsWith('https://'),
      `unexpected img-src source: ${source}`,
    );
  }
});

test('panels cannot navigate, post, or nest frames', () => {
  assert.ok(PANEL_CSP.includes("form-action 'none'"));
  assert.ok(PANEL_CSP.includes("base-uri 'none'"));
  assert.ok(PANEL_CSP.includes("frame-src 'none'"));
});
