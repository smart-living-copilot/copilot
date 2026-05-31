import type { NextConfig } from 'next';

const pollIntervalMs = Number(process.env.NEXT_POLL_INTERVAL_MS ?? 0);

const nextConfig: NextConfig = {
  turbopack: {
    root: process.cwd(),
  },
  watchOptions:
    Number.isFinite(pollIntervalMs) && pollIntervalMs > 0
      ? { pollIntervalMs }
      : undefined,
};

export default nextConfig;
