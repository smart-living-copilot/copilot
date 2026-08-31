import type { ProtocolClient, ProtocolClientFactory } from '@node-wot/core';

import { ProviderClient } from './client.js';
import { PROVIDER_SCHEME } from './form.js';

/** Creates clients for local provider-backed action forms. */
export class ProviderClientFactory implements ProtocolClientFactory {
  public readonly scheme = PROVIDER_SCHEME;

  /** Returns a stateless provider client. */
  public getClient(): ProtocolClient {
    return new ProviderClient();
  }

  /** No eager initialization is required. */
  public init(): boolean {
    return true;
  }

  /** No shared resources require cleanup. */
  public destroy(): boolean {
    return true;
  }
}
