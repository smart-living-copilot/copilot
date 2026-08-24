/**
 * window.wot — bridge client injected into generated WoT mini-interfaces.
 *
 * Generated HTML/JS runs in an opaque-origin sandboxed iframe with no access to
 * cookies or credentialed same-origin fetch. Its ONLY channel to the outside is
 * postMessage to the trusted parent, which enforces a per-interface capability
 * allowlist before forwarding to the runtime proxy. This script never talks to
 * the network itself.
 *
 * This file is the single canonical source. It is inlined into every generated
 * panel document by `wrap_panel_document` (panels/render.py), so a strict CSP
 * (which can't match `'self'` for an opaque origin) still allows it and pinned
 * panels stay self-contained.
 *
 * Protocol (this iframe <-> parent host):
 *   request : { source: 'wot-bridge', id, op, thingId, name, value?, input?, uriVariables? }
 *   reply   : { source: 'wot-bridge-host', id, ok, result?, error? }
 *   event   : { source: 'wot-bridge-host', kind: 'event', subscriptionId, value, eventType, name, thingId, timestamp }
 *
 * Binary read/action results use:
 *   { kind: 'binary', contentType, bodyBase64, sizeBytes? }
 * Use binaryToBytes/binaryToBlob/binaryToObjectUrl to consume them, and
 * binaryFromBase64/binaryFromBytes to send binary write/action inputs.
 */
(function () {
  'use strict';


  /**
   * The window hosting this panel, or null when there is none.
   *
   * Only the parent frame. A panel opened as a top-level page is deliberately
   * not hosted: as a top-level document it could navigate itself to any URL,
   * and navigation is not governed by CSP -- so the egress containment the rest
   * of this file relies on would not hold. Such a panel gets a clear failure
   * from `send` rather than a device connection.
   */
  function hostWindow() {
    return window.parent !== window ? window.parent : null;
  }
  var REQUEST_SOURCE = 'wot-bridge';
  var HOST_SOURCE = 'wot-bridge-host';

  var pending = {}; // id -> { resolve, reject }
  var callbacks = {}; // subscriptionId -> fn(value, event)
  var nextId = 0;

  function send(op, payload) {
    var id = REQUEST_SOURCE + ':' + nextId++;
    var message = Object.assign(
      { source: REQUEST_SOURCE, id: id, op: op },
      payload || {},
    );
    return new Promise(function (resolve, reject) {
      pending[id] = { resolve: resolve, reject: reject };
      try {
        var host = hostWindow();
        if (!host) {
          // Silently dropping the message would leave this promise pending and
          // the panel spinning with nothing to explain it.
          delete pending[id];
          reject(
            new Error(
              'This panel has no host. Open it from the chat rather than directly.',
            ),
          );
          return;
        }
        host.postMessage(message, '*');
      } catch (err) {
        delete pending[id];
        reject(err);
      }
    });
  }

  window.addEventListener('message', function (event) {
    // Only trust the parent frame. Origin is opaque ("null") for a sandboxed
    // document, so match on the source window instead of the origin string.
    if (event.source !== hostWindow()) {
      return;
    }
    var data = event.data;
    if (!data || data.source !== HOST_SOURCE) {
      return;
    }

    if (data.kind === 'event') {
      var cb = callbacks[data.subscriptionId];
      if (typeof cb === 'function') {
        try {
          cb(data.value, data);
        } catch {
          /* swallow callback errors so one widget can't break the bridge */
        }
      }
      return;
    }

    var entry = pending[data.id];
    if (!entry) {
      return;
    }
    delete pending[data.id];
    if (data.ok) {
      entry.resolve(data.result);
    } else {
      entry.reject(new Error(data.error || 'wot bridge request failed'));
    }
  });

  function options(opts) {
    opts = opts || {};
    return { uriVariables: opts.uriVariables };
  }

  function isBinaryPayload(value) {
    return (
      value &&
      typeof value === 'object' &&
      value.kind === 'binary' &&
      typeof value.bodyBase64 === 'string'
    );
  }

  function binaryToBytes(payload) {
    if (!isBinaryPayload(payload)) {
      throw new Error('Expected a binary payload from window.wot');
    }
    var raw = atob(payload.bodyBase64);
    var bytes = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) {
      bytes[i] = raw.charCodeAt(i);
    }
    return bytes;
  }

  function binaryToBlob(payload) {
    return new Blob([binaryToBytes(payload)], {
      type: payload.contentType || 'application/octet-stream',
    });
  }

  function binaryToObjectUrl(payload) {
    return URL.createObjectURL(binaryToBlob(payload));
  }

  function binaryFromBase64(bodyBase64, contentType) {
    if (typeof bodyBase64 !== 'string') {
      throw new Error('bodyBase64 is required');
    }
    return {
      kind: 'binary',
      contentType: contentType || 'application/octet-stream',
      bodyBase64: bodyBase64,
    };
  }

  function binaryFromBytes(bytes, contentType) {
    if (!(bytes instanceof Uint8Array)) {
      bytes = new Uint8Array(bytes);
    }
    var binary = '';
    var chunkSize = 0x8000;
    for (var i = 0; i < bytes.length; i += chunkSize) {
      var chunk = bytes.subarray(i, i + chunkSize);
      binary += String.fromCharCode.apply(null, Array.from(chunk));
    }
    return {
      kind: 'binary',
      contentType: contentType || 'application/octet-stream',
      bodyBase64: btoa(binary),
      sizeBytes: bytes.length,
    };
  }

  async function subscribe(op, thingId, name, callback, opts) {
    if (typeof callback !== 'function') {
      throw new Error('A callback is required for ' + op);
    }
    var result = await send(
      op,
      Object.assign({ thingId: thingId, name: name }, options(opts)),
    );
    var subscriptionId = result && result.subscriptionId;
    if (!subscriptionId) {
      throw new Error(op + ' did not return a subscription id');
    }
    callbacks[subscriptionId] = callback;
    return { subscriptionId: subscriptionId };
  }

  var wot = {
    readProperty: function (thingId, name, opts) {
      return send(
        'readProperty',
        Object.assign({ thingId: thingId, name: name }, options(opts)),
      );
    },
    writeProperty: function (thingId, name, value, opts) {
      return send(
        'writeProperty',
        Object.assign(
          { thingId: thingId, name: name, value: value },
          options(opts),
        ),
      );
    },
    invokeAction: function (thingId, name, input, opts) {
      return send(
        'invokeAction',
        Object.assign(
          { thingId: thingId, name: name, input: input },
          options(opts),
        ),
      );
    },
    observeProperty: function (thingId, name, callback, opts) {
      return subscribe('observeProperty', thingId, name, callback, opts);
    },
    subscribeEvent: function (thingId, name, callback, opts) {
      return subscribe('subscribeEvent', thingId, name, callback, opts);
    },
    isBinaryPayload: isBinaryPayload,
    binaryToBytes: binaryToBytes,
    binaryToBlob: binaryToBlob,
    binaryToObjectUrl: binaryToObjectUrl,
    binaryFromBase64: binaryFromBase64,
    binaryFromBytes: binaryFromBytes,
    unsubscribe: function (handle) {
      var subscriptionId =
        handle && handle.subscriptionId ? handle.subscriptionId : handle;
      if (!subscriptionId) {
        return Promise.resolve();
      }
      delete callbacks[subscriptionId];
      return send('unsubscribe', { subscriptionId: subscriptionId }).catch(
        function () {},
      );
    },
  };

  // Best-effort cleanup so subscriptions don't linger after the panel is gone.
  window.addEventListener('pagehide', function () {
    var ids = Object.keys(callbacks);
    callbacks = {};
    for (var i = 0; i < ids.length; i++) {
      try {
        if (hostWindow()) hostWindow().postMessage(
          {
            source: REQUEST_SOURCE,
            id: REQUEST_SOURCE + ':cleanup',
            op: 'unsubscribe',
            subscriptionId: ids[i],
          },
          '*',
        );
      } catch {
        /* ignore */
      }
    }
  });

  window.wot = wot;
})();
