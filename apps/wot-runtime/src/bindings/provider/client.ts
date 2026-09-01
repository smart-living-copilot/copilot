import { Readable } from 'node:stream';

import wotCore from '@node-wot/core';
import type { Content, Form, ProtocolClient, SecurityScheme } from '@node-wot/core';
import { Subscription } from 'rxjs/Subscription.js';

import { config } from '../../config/env.js';
import { createRuntimeError } from '../../services/errors.js';
import { registryServiceHeaders } from '../../services/thing-catalog-client.js';
import { parseProviderActionTarget } from './form.js';

const { Content: ContentClass } = wotCore as any;
const MAX_RESPONSE_BYTES = 1024 * 1024;
const DOWNLOAD_PATH = /^\/api\/discovery\/downloads\/([A-Za-z0-9_-]{43})$/;

async function decodeInput(content: Content | undefined): Promise<unknown> {
  if (!content) return null;
  const body = await content.toBuffer();
  if (body.length === 0) return null;
  try {
    return JSON.parse(body.toString('utf8'));
  } catch {
    throw createRuntimeError('invalid_argument', 'Provider-backed action input must be JSON');
  }
}

function responseContentType(form: Form, upstream: Headers): string {
  const response = (form as unknown as Record<string, unknown>).response;
  if (response && typeof response === 'object') {
    const declared = (response as Record<string, unknown>).contentType;
    if (typeof declared === 'string' && declared.trim()) {
      return declared.trim();
    }
  }
  return upstream.get('content-type') || 'application/octet-stream';
}

function credentialChallenge(payload: unknown): Record<string, string> {
  const fallback = {
    status: 'credential_required',
    message: 'This source requires credentials.',
  };
  if (!payload || typeof payload !== 'object') return fallback;
  const detail = (payload as Record<string, unknown>).detail;
  if (!detail || typeof detail !== 'object') return fallback;
  const safe: Record<string, string> = {};
  for (const key of ['status', 'owner_kind', 'source_id', 'security_name', 'scheme', 'message']) {
    const value = (detail as Record<string, unknown>)[key];
    if (typeof value === 'string') safe[key] = value;
  }
  return safe.status ? safe : fallback;
}

/** Routes provider-backed Thing actions through wotbot's internal dispatcher. */
export class ProviderClient implements ProtocolClient {
  /** Provider resources are described during onboarding, not from this binding. */
  public async requestThingDescription(_uri: string): Promise<Content> {
    throw createRuntimeError(
      'unimplemented',
      'Provider-backed Things are created by onboarding, not endpoint description',
    );
  }

  /** Provider-backed properties are not part of the current contract. */
  public async readResource(_form: Form): Promise<Content> {
    throw createRuntimeError('unimplemented', 'Provider-backed properties are not implemented');
  }

  /** Provider-backed properties are not writable. */
  public async writeResource(_form: Form, _content?: Content): Promise<void> {
    throw createRuntimeError('unimplemented', 'Provider-backed properties are read-only');
  }

  /** Invokes the action through the fixed, service-authenticated dispatcher. */
  public async invokeResource(form: Form, content?: Content): Promise<Content> {
    const target = parseProviderActionTarget(form);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), config.providerActionTimeoutMs);
    let streaming = false;
    try {
      const response = await fetch(`${config.registryUrl}/api/discovery/runtime/invoke`, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          ...(registryServiceHeaders() || {}),
        },
        body: JSON.stringify({
          thing_id: target.thingId,
          action: target.action,
          input: await decodeInput(content),
          uri_variables: target.uriVariables,
        }),
        signal: controller.signal,
      });
      const raw = Buffer.from(await response.arrayBuffer());
      if (raw.length > MAX_RESPONSE_BYTES) {
        throw createRuntimeError('resource_exhausted', 'Provider action returned an oversized response');
      }
      let payload: unknown;
      try {
        payload = JSON.parse(raw.toString('utf8'));
      } catch {
        throw createRuntimeError('unknown', `Provider action returned HTTP ${response.status}`);
      }
      if (response.status === 428) {
        const challenge = credentialChallenge(payload);
        return new ContentClass('application/json', Readable.from(Buffer.from(JSON.stringify(challenge))));
      }
      if (!response.ok) {
        const detail =
          payload && typeof payload === 'object' && typeof (payload as Record<string, unknown>).detail === 'string'
            ? String((payload as Record<string, unknown>).detail)
            : `Provider action returned HTTP ${response.status}`;
        throw createRuntimeError(response.status === 422 ? 'invalid_argument' : 'unknown', detail);
      }
      const kind =
        payload && typeof payload === 'object' && typeof (payload as Record<string, unknown>).kind === 'string'
          ? String((payload as Record<string, unknown>).kind)
          : '';
      if (kind === 'response') {
        const encoded =
          typeof (payload as Record<string, unknown>).body_base64 === 'string'
            ? String((payload as Record<string, unknown>).body_base64)
            : '';
        const contentTypeValue = (payload as Record<string, unknown>).content_type;
        const contentType =
          typeof contentTypeValue === 'string' && contentTypeValue.length <= 200 && !/[\r\n]/.test(contentTypeValue)
            ? contentTypeValue
            : 'application/octet-stream';
        if (!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(encoded)) {
          throw createRuntimeError('unknown', 'Provider action returned an invalid response body');
        }
        const body = Buffer.from(encoded, 'base64');
        if (body.toString('base64') !== encoded) {
          throw createRuntimeError('unknown', 'Provider action returned an invalid response body');
        }
        return new ContentClass(contentType, Readable.from(body));
      }
      if (kind !== 'download') {
        throw createRuntimeError('unknown', 'Provider action returned an invalid result kind');
      }
      const downloadUrl =
        payload && typeof payload === 'object' && typeof (payload as Record<string, unknown>).download_url === 'string'
          ? String((payload as Record<string, unknown>).download_url)
          : '';
      const match = DOWNLOAD_PATH.exec(downloadUrl);
      if (!match) {
        throw createRuntimeError('unknown', 'Provider action returned an invalid download capability');
      }
      const download = await fetch(`${config.registryUrl}/api/discovery/runtime/downloads/${match[1]}`, {
        headers: {
          Accept: '*/*',
          ...(registryServiceHeaders() || {}),
        },
        signal: controller.signal,
      });
      if (!download.ok || !download.body) {
        await download.body?.cancel();
        throw createRuntimeError('unknown', `Provider download returned HTTP ${download.status}`);
      }
      const stream = Readable.from(download.body as any);
      const clearTimer = () => clearTimeout(timer);
      stream.once('close', clearTimer);
      stream.once('error', clearTimer);
      stream.once('end', clearTimer);
      streaming = true;
      return new ContentClass(responseContentType(form, download.headers), stream);
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        throw createRuntimeError('deadline_exceeded', 'Provider action timed out');
      }
      throw error;
    } finally {
      if (!streaming) clearTimeout(timer);
    }
  }

  /** There is no linked resource state to remove. */
  public async unlinkResource(_form: Form): Promise<void> {
    return undefined;
  }

  /** Provider-backed subscriptions are not implemented. */
  public async subscribeResource(
    _form: Form,
    _next: (content: Content) => void,
    _error?: (error: Error) => void,
    _complete?: () => void,
  ): Promise<Subscription> {
    throw createRuntimeError('unimplemented', 'Provider-backed subscriptions are not implemented');
  }

  /** The client has no eager resources to start. */
  public async start(): Promise<void> {
    return undefined;
  }

  /** The client has no persistent resources to stop. */
  public async stop(): Promise<void> {
    return undefined;
  }

  /** Provider resources use source credentials internally; TD credentials are never forwarded here. */
  public setSecurity(metadata: SecurityScheme[]): boolean {
    const scheme = metadata?.[0]?.scheme?.toLowerCase() || 'nosec';
    return ['nosec', 'apikey', 'bearer', 'basic', 'oauth2'].includes(scheme);
  }
}
