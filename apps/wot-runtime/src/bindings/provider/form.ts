import type { Form } from '@node-wot/core';

import { createRuntimeError } from '../../services/errors.js';

export const PROVIDER_SCHEME = 'wotbot+provider';

export type ProviderActionTarget = {
  thingId: string;
  action: string;
};

/** Parses the local Thing id and action from a provider-backed TD form. */
export function parseProviderActionTarget(form: Form): ProviderActionTarget {
  if (typeof form.href !== 'string' || !form.href.trim()) {
    throw createRuntimeError('invalid_argument', 'Provider-backed form is missing an href');
  }
  let parsed: URL;
  try {
    parsed = new URL(form.href);
  } catch {
    throw createRuntimeError('invalid_argument', 'Provider-backed form has an invalid href');
  }
  if (parsed.protocol !== `${PROVIDER_SCHEME}:` || parsed.hostname !== 'runtime') {
    throw createRuntimeError('invalid_argument', 'Provider-backed form must target the local runtime');
  }
  if (parsed.username || parsed.password || parsed.port || parsed.search || parsed.hash) {
    throw createRuntimeError('invalid_argument', 'Provider-backed form contains unsupported URL components');
  }
  const segments = parsed.pathname.split('/').filter(Boolean);
  if (segments.length !== 4 || segments[0] !== 'things' || segments[2] !== 'actions') {
    throw createRuntimeError('invalid_argument', 'Provider-backed action form has an invalid path');
  }
  let thingId: string;
  try {
    thingId = Buffer.from(segments[1] || '', 'base64url')
      .toString('utf8')
      .trim();
  } catch {
    throw createRuntimeError('invalid_argument', 'Provider-backed form has an invalid Thing id');
  }
  const action = decodeURIComponent(segments[3] || '').trim();
  if (!thingId || !action) {
    throw createRuntimeError('invalid_argument', 'Provider-backed form is missing its target');
  }
  return { thingId, action };
}
