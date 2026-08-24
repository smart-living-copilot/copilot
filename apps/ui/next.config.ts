import type { NextConfig } from 'next';

const pollIntervalMs = Number(process.env.NEXT_POLL_INTERVAL_MS ?? 0);

const nextConfig: NextConfig = {
  output: 'standalone',
  // Panels render on their own `*.panels.<host>` origin, which is cross-origin
  // to the dev server; without this Next blocks their dev-asset requests.
  allowedDevOrigins: ['*.panels.localhost'],
  turbopack: {
    root: process.cwd(),
  },
  watchOptions:
    Number.isFinite(pollIntervalMs) && pollIntervalMs > 0
      ? { pollIntervalMs }
      : undefined,
};

export default nextConfig;
