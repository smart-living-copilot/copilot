/**
 * Content-Security-Policy for generated WoT panel documents (ephemeral + pinned).
 *
 * Panels run in an opaque-origin sandboxed iframe. We deliberately allow loading
 * from an allowlist of CDNs (so the agent can build rich UIs with real charting/
 * icon/font libraries). `connect-src` is restricted to those same CDN hosts (not
 * `'none'`, so library source maps load without console noise, and not `*`): a
 * panel can only reach hosts whose code it is already allowed to run, none of
 * which is an attacker-controlled endpoint that could receive exfiltrated device
 * data. The `window.wot` bridge keeps working regardless because postMessage is
 * not a network connection and is not governed by CSP.
 *
 * `img-src` stays a closed allowlist because an image URL is itself an
 * exfiltration channel -- a panel can encode device readings into a path and
 * "load" it. Widening it to `*` or `https:` would hand a panel an attacker-
 * chosen endpoint. The listed hosts are safe for the same reason `connect-src`
 * is: the panel cannot pick the host, and none of them forwards a request
 * anywhere the author could read it. Bridge JS is inlined into the document, so
 * 'unsafe-inline' covers it (CSP 'self' would not match the opaque origin).
 */
const CDN_HOSTS = [
  'https://cdn.jsdelivr.net',
  'https://unpkg.com',
  'https://cdnjs.cloudflare.com',
  'https://fonts.googleapis.com',
  'https://fonts.gstatic.com',
];
const SCRIPT_CDNS = [
  'https://cdn.jsdelivr.net',
  'https://unpkg.com',
  'https://cdnjs.cloudflare.com',
];
// Styles and fonts track the script hosts: a panel may already execute
// arbitrary JS from these, so a stylesheet from the same host grants strictly
// less. Leaving unpkg out of style-src only broke libraries whose CSS ships
// beside the JS the agent is told it may load -- Leaflet, for one.
const STYLE_CDNS = ['https://fonts.googleapis.com', ...SCRIPT_CDNS];
const FONT_CDNS = ['https://fonts.gstatic.com', ...SCRIPT_CDNS];

/**
 * Map tile servers, so a panel can render a real map.
 *
 * Named hosts only, never a wildcard: a tile request leaks which tiles are on
 * screen to the tile provider and nothing more, because the panel cannot choose
 * where the request goes. Add a provider here to use it; a panel cannot reach
 * one that is not listed.
 */
const TILE_HOSTS = [
  'https://tile.openstreetmap.org',
  'https://*.tile.openstreetmap.org',
];

export const PANEL_CSP = [
  "default-src 'none'",
  `script-src 'unsafe-inline' ${SCRIPT_CDNS.join(' ')}`,
  `style-src 'unsafe-inline' ${STYLE_CDNS.join(' ')}`,
  `font-src ${FONT_CDNS.join(' ')}`,
  `img-src 'self' data: ${[...SCRIPT_CDNS, ...TILE_HOSTS].join(' ')}`,
  `connect-src ${CDN_HOSTS.join(' ')}`,
  "form-action 'none'",
  "base-uri 'none'",
  "frame-src 'none'",
].join('; ');
