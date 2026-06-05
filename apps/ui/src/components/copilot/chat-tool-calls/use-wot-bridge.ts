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

type RuntimeOp = {
  path: string;
  body: (req: BridgeRequest) => Record<string, unknown>;
  subscription?: boolean;
};

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
      value: r.value,
      uri_variables: r.uriVariables,
    }),
  },
  invokeAction: {
    path: 'invoke-action',
    body: (r) => ({
      thing_id: r.thingId,
      action_name: r.name,
      input: r.input,
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
 * The runtime returns `{ thing_id, property_name, result: { success, payload: {
 * kind: 'inline', data } } }`. We hand back `payload.data` so generated code can
 * use the value directly (e.g. `temp.value`), instead of leaking transport
 * details. Non-inline payloads or output-less writes resolve to `undefined`.
 */
function unwrapRuntimeResult(data: unknown): {
  ok: boolean;
  value?: unknown;
  error?: string;
} {
  if (!data || typeof data !== 'object') {
    return { ok: true, value: data };
  }
  const result = (data as Record<string, unknown>).result;
  if (!result || typeof result !== 'object') {
    return { ok: true, value: data };
  }
  const envelope = result as Record<string, unknown>;
  if (envelope.success === false) {
    const error =
      typeof envelope.status_text === 'string'
        ? envelope.status_text
        : 'Interaction failed';
    return { ok: false, error };
  }
  const payload = envelope.payload;
  if (payload && typeof payload === 'object' && 'data' in payload) {
    return { ok: true, value: (payload as Record<string, unknown>).data };
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
 * Wires the trusted parent side of the WoT bridge for a generated interface.
 *
 * Listens for postMessage requests from the specific sandboxed iframe, enforces
 * the per-interface capability allowlist, forwards permitted calls to the
 * runtime proxy, and relays observe/subscribe deliveries (over SSE) back into
 * the iframe.
 */
export function useWotBridge(
  iframeRef: RefObject<HTMLIFrameElement | null>,
  capabilities: WotCapability[],
) {
  const capsRef = useRef(capabilities);

  useEffect(() => {
    capsRef.current = capabilities;
  }, [capabilities]);

  useEffect(() => {
    const activeSubscriptions = new Set<string>();
    let eventSource: EventSource | null = null;
    let closed = false;

    function postToFrame(message: Record<string, unknown>) {
      iframeRef.current?.contentWindow?.postMessage(
        { source: HOST_SOURCE, ...message },
        '*',
      );
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
        return;
      }
      activeSubscriptions.delete(subscriptionId);
      syncEventSource();
      await callRuntime('remove-subscription', {
        subscription_id: subscriptionId,
      });
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
      const frame = iframeRef.current;
      // Trust only this specific iframe. Sandboxed docs have a "null" origin,
      // so match the source window rather than the origin string.
      if (!frame || event.source !== frame.contentWindow) {
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
  }, [iframeRef]);
}
