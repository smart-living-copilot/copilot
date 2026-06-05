/**
 * Content-Security-Policy for generated WoT panel documents (ephemeral + pinned).
 *
 * Panels run in an opaque-origin sandboxed iframe. We deliberately allow loading
 * from an allowlist of CDNs (so the agent can build rich UIs with real charting/
 * icon/font libraries) but set `connect-src 'none'` so a panel can never send
 * device data anywhere — fetch/XHR/beacon/WebSocket/EventSource are all blocked.
 * The `window.wot` bridge keeps working because postMessage is not a network
 * connection and is not governed by CSP.
 *
 * `img-src` is kept tight ('self' data:) because image URLs are themselves an
 * exfiltration channel. Bridge JS is inlined into the document, so 'unsafe-inline'
 * covers it (CSP 'self' would not match the opaque origin).
 */
const SCRIPT_CDNS = [
  'https://cdn.jsdelivr.net',
  'https://unpkg.com',
  'https://cdnjs.cloudflare.com',
];
const STYLE_CDNS = ['https://fonts.googleapis.com', 'https://cdn.jsdelivr.net'];
const FONT_CDNS = ['https://fonts.gstatic.com', 'https://cdn.jsdelivr.net'];

export const PANEL_CSP = [
  "default-src 'none'",
  `script-src 'unsafe-inline' ${SCRIPT_CDNS.join(' ')}`,
  `style-src 'unsafe-inline' ${STYLE_CDNS.join(' ')}`,
  `font-src ${FONT_CDNS.join(' ')}`,
  "img-src 'self' data:",
  "connect-src 'none'",
  "form-action 'none'",
  "base-uri 'none'",
  "frame-src 'none'",
].join('; ');
