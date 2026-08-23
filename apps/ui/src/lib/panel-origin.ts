/**
 * Panels are served from an origin of their own, one per panel.
 *
 * A panel is LLM-authored code. Served from the app's origin it could only be
 * contained by a sandbox without `allow-same-origin`, which forces an opaque
 * origin -- and an opaque origin is denied every permission-gated API, so no
 * panel could ever use a camera, persist anything, or record audio.
 *
 * Giving each panel its own origin inverts that. `allow-same-origin` then means
 * "your own real origin", which is still cross-origin to the app and still
 * walled off from its DOM, storage and cookies by ordinary same-origin policy --
 * while the panel gets the whole platform back. Per panel rather than one shared
 * panel host, so a camera grant for one panel does not arm every later one.
 *
 * Locally this needs no configuration: Chrome resolves any `*.localhost` to
 * loopback and treats it as a secure context. In production it needs a wildcard
 * host, hence `NEXT_PUBLIC_PANEL_HOST_TEMPLATE`.
 */

/** Placeholder replaced with the panel's own label. */
const KEY_TOKEN = '{key}';

/**
 * Reduce an id or filename to a single DNS label.
 *
 * Single, deliberately: a wildcard certificate for `*.panels.example.com`
 * matches one label only, so a dotted filename must not become `a.b.panels…`.
 */
export function toPanelLabel(key: string): string {
  const label = key
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 63)
    .replace(/-+$/g, '');
  return label || 'panel';
}

/**
 * The origin a given panel is served from.
 *
 * Returns an empty string during server rendering, where there is no location
 * to derive from; callers build a relative URL until hydration supplies one.
 */
export function getPanelOrigin(
  key: string,
  location: { protocol: string; hostname: string; port: string } | undefined =
    typeof window === 'undefined' ? undefined : window.location,
  template: string | undefined = process.env.NEXT_PUBLIC_PANEL_HOST_TEMPLATE,
): string {
  if (!location) {
    return '';
  }

  const label = toPanelLabel(key);
  const port = location.port ? `:${location.port}` : '';

  if (template) {
    return `${location.protocol}//${template.replace(KEY_TOKEN, label)}${port}`;
  }

  return `${location.protocol}//${label}.panels.${location.hostname}${port}`;
}

/** Whether a request arrived on a panel host rather than the app's own. */
export function isPanelHostname(
  hostname: string,
  template: string | undefined = process.env.NEXT_PUBLIC_PANEL_HOST_TEMPLATE,
): boolean {
  if (template) {
    const suffix = template.slice(template.indexOf(KEY_TOKEN) + KEY_TOKEN.length);
    return hostname !== suffix && hostname.endsWith(suffix);
  }
  return /^[a-z0-9-]+\.panels\./.test(hostname);
}
