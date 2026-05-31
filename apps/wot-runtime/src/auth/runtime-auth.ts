import crypto from 'node:crypto';

import { config } from '../config/env.js';

/**
 * Extracts a Bearer token from an Authorization header value.
 *
 * @param headerValue The raw Authorization header string.
 * @returns The extracted token or null if not found/invalid.
 */
function extractBearerToken(headerValue: string | undefined): string | null {
  if (!headerValue) {
    return null;
  }

  const match = headerValue.trim().match(/^Bearer\s+(.+)$/i);
  if (!match) {
    return null;
  }

  const token = match[1]?.trim();
  return token ? token : null;
}

/**
 * Performs a timing-safe comparison between a candidate token and the configured runtime API token.
 *
 * @param candidate The token to validate.
 * @returns True if the tokens match, false otherwise.
 */
function tokensMatch(candidate: string | null): boolean {
  if (!candidate) {
    return false;
  }

  const left = Buffer.from(candidate, 'utf8');
  const right = Buffer.from(config.runtimeApiToken, 'utf8');
  if (left.length !== right.length) {
    return false;
  }

  return crypto.timingSafeEqual(left, right);
}

/**
 * Checks if an Express request contains a valid Bearer token in its Authorization header.
 *
 * @param request The Express request object (minimal interface for testing).
 * @returns True if a valid runtime API token is present.
 */
export function requestHasRuntimeApiToken(request: { get(name: string): string | undefined }): boolean {
  return tokensMatch(extractBearerToken(request.get('authorization')));
}
