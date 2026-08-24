'use client';

import { type RefObject, useEffect, useRef } from 'react';

import {
  isInteractionAllowed,
  type WotCapability,
} from './web-interface-model';

const REQUEST_SOURCE = 'wot-bridge';
const HOST_SOURCE = 'wot-bridge-host';
const RUNTIME_BASE = '/api/wot/runtime';

type BridgeRequest = {
  source: string;
  id: string;
  op: string;
  thingId?: string;
  name?: string;
  value?: unknown;
  input?: unknown;
  uriVariables?: Record<string, unknown>;
  subscriptionId?: string;
};

export type WotBinaryPayload = {
  kind: 'binary';
  contentType: string;
  bodyBase64: string;
  sizeBytes?: number;
};

type RuntimeOp = {
  path: string;
  body: (req: BridgeRequest) => Record<string, unknown>;
  subscription?: boolean;
};

function normalizeBinaryPayload(value: unknown): WotBinaryPayload | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  const record = value as Record<string, unknown>;
  if (record.kind !== 'binary') {
    return null;
  }
  const bodyBase64 =
    typeof record.bodyBase64 === 'string'
      ? record.bodyBase64
      : typeof record.body_base64 === 'string'
        ? record.body_base64
        : undefined;
  if (bodyBase64 === undefined) {
    return null;
  }
  const contentType =
    typeof record.contentType === 'string'
      ? record.contentType
      : typeof record.content_type === 'string'
        ? record.content_type
        : 'application/octet-stream';
  const rawSizeBytes =
    typeof record.sizeBytes === 'number'
      ? record.sizeBytes
      : typeof record.size_bytes === 'number'
        ? record.size_bytes
        : undefined;
  return {
    kind: 'binary',
    contentType,
    bodyBase64,
    ...(rawSizeBytes === undefined ? {} : { sizeBytes: rawSizeBytes }),
  };
}

function payloadInputFields(
  value: unknown,
  keys: {
    inlineKey: string;
    base64Key: string;
    contentTypeKey: string;
  },
): Record<string, unknown> {
  const binary = normalizeBinaryPayload(value);
  if (!binary) {
    return { [keys.inlineKey]: value };
  }
  return {
    [keys.base64Key]: binary.bodyBase64,
    [keys.contentTypeKey]: binary.contentType,
  };
}

const RUNTIME_OPS: Record<string, RuntimeOp> = {
  readProperty: {
    path: 'read-property',
    body: (r) => ({
      thing_id: r.thingId,
      property_name: r.name,
      uri_variables: r.uriVariables,
    }),
  },
  writeProperty: {
    path: 'write-property',
    body: (r) => ({
      thing_id: r.thingId,
      property_name: r.name,
      ...payloadInputFields(r.value, {
        inlineKey: 'value',
        base64Key: 'value_base64',
        contentTypeKey: 'value_content_type',
      }),
      uri_variables: r.uriVariables,
    }),
  },
  invokeAction: {
    path: 'invoke-action',
    body: (r) => ({
      thing_id: r.thingId,
      action_name: r.name,
      ...payloadInputFields(r.input, {
        inlineKey: 'input',
        base64Key: 'input_base64',
        contentTypeKey: 'input_content_type',
      }),
      uri_variables: r.uriVariables,
    }),
  },
  observeProperty: {
    path: 'observe-property',
    subscription: true,
    body: (r) => ({
      thing_id: r.thingId,
      property_name: r.name,
      uri_variables: r.uriVariables,
    }),
  },
  subscribeEvent: {
    path: 'subscribe-event',
    subscription: true,
    body: (r) => ({
      thing_id: r.thingId,
      event_name: r.name,
      uri_variables: r.uriVariables,
    }),
  },
};

/**
 * Unwraps the wot-runtime transport envelope into the decoded property/action
 * value the generated interface actually wants.
 *
 * The runtime nests the result differently per op:
 *   read/write property : `{ result: { success, payload: { data } } }`
 *   invoke action       : `{ outcome: 'completed_result',
 *                            completed_result: { success, payload: { data } } }`
 *                         or `{ outcome: 'operation_handle', operation_handle }`
 *                         for async actions.
 * Inline payloads hand back `payload.data` so generated code uses the value
 * directly (e.g. `rows.map(...)`) instead of the transport wrapper. Binary
 * payloads hand back `{ kind: 'binary', contentType, bodyBase64, sizeBytes }`
 * so panel code can turn them into bytes, a Blob, or an object URL. Output-less
 * writes resolve to `undefined`; async actions resolve to the operation handle.
 */
export function unwrapRuntimeResult(data: unknown): {
  ok: boolean;
  value?: unknown;
  error?: string;
} {
  if (!data || typeof data !== 'object') {
    return { ok: true, value: data };
  }
  const record = data as Record<string, unknown>;
  const candidate = record.result ?? record.completed_result;
  if (!candidate || typeof candidate !== 'object') {
    // Async action with no inline result: surface the operation handle.
    if (record.outcome === 'operation_handle' && record.operation_handle) {
      return { ok: true, value: record.operation_handle };
    }
    return { ok: true, value: data };
  }
  const envelope = candidate as Record<string, unknown>;
  if (envelope.success === false) {
    const error =
      typeof envelope.status_text === 'string'
        ? envelope.status_text
        : 'Interaction failed';
    return { ok: false, error };
  }
  const payload = envelope.payload;
  if (payload && typeof payload === 'object') {
    const binary = normalizeBinaryPayload(payload);
    if (binary) {
      return { ok: true, value: binary };
    }
    if ('data' in payload) {
      return { ok: true, value: (payload as Record<string, unknown>).data };
    }
  }
  return { ok: true, value: undefined };
}

function extractSubscriptionId(result: unknown): string | undefined {
  if (!result || typeof result !== 'object') {
    return undefined;
  }
  const record = result as Record<string, unknown>;
  const subscription = record.subscription;
  if (subscription && typeof subscription === 'object') {
    const id = (subscription as Record<string, unknown>).subscriptionId;
    if (typeof id === 'string') {
      return id;
    }
  }
  return typeof record.subscriptionId === 'string'
    ? record.subscriptionId
    : undefined;
}

/**
 * What the bridge is talking to: a framed panel, or one opened as its own page.
 *
 * A popup's origin cannot be read back cross-origin, so callers that open one
 * pass the origin they navigated it to. For an iframe it is read from `src`.
 */
export type BridgeTarget = HTMLIFrameElement | Window | null;

function targetWindow(target: BridgeTarget): Window | null {
  if (!target) {
    return null;
  }
  return target instanceof HTMLIFrameElement ? target.contentWindow : target;
}

function targetOrigin(
  target: BridgeTarget,
  expectedOrigin?: string,
): string | null {
  if (expectedOrigin) {
    return expectedOrigin;
  }
  if (!(target instanceof HTMLIFrameElement) || !target.src) {
    return null;
  }
  try {
    return new URL(target.src, window.location.href).origin;
  } catch {
    return null;
  }
}

/**
 * Wires the trusted parent side of the WoT bridge for a generated interface.
 *
 * Listens for postMessage requests from the specific sandboxed iframe, enforces
 * the per-interface capability allowlist, forwards permitted calls to the
 * runtime proxy, and relays observe/subscribe deliveries (over SSE) back into
 * the iframe.
 */
export function useWotBridge(
  iframeRef: RefObject<BridgeTarget>,
  capabilities: WotCapability[],
  options: { enabled?: boolean; origin?: string } = {},
) {
  const enabled = options.enabled ?? true;
  // A popup's origin is not readable cross-origin, so its opener supplies it.
  const expectedOrigin = options.origin;
  const capsRef = useRef(capabilities);

  useEffect(() => {
    capsRef.current = capabilities;
  }, [capabilities]);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const activeSubscriptions = new Set<string>();
    let eventSource: EventSource | null = null;
    let closed = false;

    function postToFrame(message: Record<string, unknown>) {
      const target = iframeRef.current;
      const origin = targetOrigin(target, expectedOrigin);
      const win = targetWindow(target);
      if (!win || !origin) {
        return;
      }
      // Addressed rather than broadcast: the panel has a real origin now, so
      // there is no reason to hand these messages to whatever is loaded.
      win.postMessage({ source: HOST_SOURCE, ...message }, origin);
    }

    function syncEventSource() {
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }
      if (closed || activeSubscriptions.size === 0) {
        return;
      }
      const ids = Array.from(activeSubscriptions).join(',');
      eventSource = new EventSource(
        `${RUNTIME_BASE}/events?subscriptions=${encodeURIComponent(ids)}`,
      );
      eventSource.onmessage = (event) => {
        let payload: Record<string, unknown> | null = null;
        try {
          payload = JSON.parse(event.data);
        } catch {
          return;
        }
        if (!payload || typeof payload.subscriptionId !== 'string') {
          return;
        }
        postToFrame({
          kind: 'event',
          subscriptionId: payload.subscriptionId,
          value: payload.value,
          eventType: payload.eventType,
          name: payload.name,
          thingId: payload.thingId,
          timestamp: payload.timestamp,
        });
      };
    }

    async function callRuntime(
      path: string,
      body: Record<string, unknown>,
    ): Promise<{ ok: boolean; result?: unknown; error?: string }> {
      try {
        const res = await fetch(`${RUNTIME_BASE}/${path}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          const detail =
            (data as { detail?: string }).detail ||
            `Runtime request failed (${res.status})`;
          return { ok: false, error: detail };
        }
        return { ok: true, result: data };
      } catch (error) {
        return {
          ok: false,
          error: error instanceof Error ? error.message : 'Runtime unreachable',
        };
      }
    }

    async function handleUnsubscribe(req: BridgeRequest) {
      const subscriptionId = req.subscriptionId;
      if (!subscriptionId || !activeSubscriptions.has(subscriptionId)) {
        postToFrame({ id: req.id, ok: true });
        return;
      }
      activeSubscriptions.delete(subscriptionId);
      syncEventSource();
      const outcome = await callRuntime('remove-subscription', {
        subscription_id: subscriptionId,
      });
      if (!outcome.ok) {
        postToFrame({ id: req.id, ok: false, error: outcome.error });
        return;
      }
      postToFrame({ id: req.id, ok: true });
    }

    async function handleRequest(req: BridgeRequest) {
      if (req.op === 'unsubscribe') {
        await handleUnsubscribe(req);
        return;
      }

      const op = RUNTIME_OPS[req.op];
      const thingId = req.thingId ?? '';
      const name = req.name ?? '';

      if (!op) {
        postToFrame({ id: req.id, ok: false, error: `Unknown op: ${req.op}` });
        return;
      }

      if (!isInteractionAllowed(capsRef.current, req.op, thingId, name)) {
        postToFrame({
          id: req.id,
          ok: false,
          error: `Not permitted: ${req.op} ${thingId} ${name}`.trim(),
        });
        return;
      }

      const outcome = await callRuntime(op.path, op.body(req));
      if (!outcome.ok) {
        postToFrame({ id: req.id, ok: false, error: outcome.error });
        return;
      }

      if (op.subscription) {
        const subscriptionId = extractSubscriptionId(outcome.result);
        if (!subscriptionId) {
          postToFrame({
            id: req.id,
            ok: false,
            error: 'Runtime did not return a subscription id',
          });
          return;
        }
        activeSubscriptions.add(subscriptionId);
        syncEventSource();
        postToFrame({ id: req.id, ok: true, result: { subscriptionId } });
        return;
      }

      const unwrapped = unwrapRuntimeResult(outcome.result);
      if (!unwrapped.ok) {
        postToFrame({ id: req.id, ok: false, error: unwrapped.error });
        return;
      }
      postToFrame({ id: req.id, ok: true, result: unwrapped.value });
    }

    function onMessage(event: MessageEvent) {
      const target = iframeRef.current;
      // Trust only this specific panel, and only while it still is what it was:
      // the window identity check alone would survive it navigating elsewhere,
      // so the origin is checked too now that it is a real one.
      const win = targetWindow(target);
      if (!win || event.source !== win) {
        return;
      }
      if (event.origin !== targetOrigin(target, expectedOrigin)) {
        return;
      }
      const data = event.data as BridgeRequest | undefined;
      if (
        !data ||
        data.source !== REQUEST_SOURCE ||
        typeof data.op !== 'string'
      ) {
        return;
      }
      void handleRequest(data);
    }

    window.addEventListener('message', onMessage);

    return () => {
      closed = true;
      window.removeEventListener('message', onMessage);
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }
      // Best-effort teardown so the runtime doesn't keep dead subscriptions.
      for (const subscriptionId of activeSubscriptions) {
        void fetch(`${RUNTIME_BASE}/remove-subscription`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ subscription_id: subscriptionId }),
          keepalive: true,
        }).catch(() => {});
      }
      activeSubscriptions.clear();
    };
  }, [iframeRef, enabled, expectedOrigin]);
}
