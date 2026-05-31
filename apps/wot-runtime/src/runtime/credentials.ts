/**
 * Field name used to store the original security name in WoT security definitions.
 */
export const RUNTIME_SECURITY_NAME_FIELD = '__wotRegistrySecurityName';

type PlainObject = Record<string, unknown>;

/**
 * A single credential entry for a specific security scheme.
 */
export type RuntimeCredentialEntry = {
  security_name: string;
  scheme: string;
  credentials: PlainObject;
};

/**
 * Wrapper for all credentials associated with a single Thing.
 */
export type RuntimeThingSecrets = {
  entries: RuntimeCredentialEntry[];
};

/**
 * Interface for targets (like node-wot Servient) that can store credentials.
 */
type RuntimeSecretsTarget = {
  addCredentials: (credentials: Record<string, RuntimeThingSecrets>) => void;
  credentialStore?: Map<string, unknown[]>;
};

/**
 * Interface for node-wot protocol clients that can be patched to support custom credential resolution.
 */
type ClientSecurityPatchTarget = {
  prototype: {
    setSecurity?: (metadata: unknown, credentials: unknown) => unknown;
  };
};

/**
 * WoT security metadata found in InteractionOutput or Thing Description.
 */
type SecurityMetadata = PlainObject & {
  scheme?: string;
};

/**
 * Tracks which prototypes have already been patched to avoid double patching.
 */
const patchedSecurityTargets = new WeakSet<object>();

/**
 * Checks if a value is a plain object.
 */
function isPlainObject(value: unknown): value is PlainObject {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

/**
 * Checks if a value matches the RuntimeCredentialEntry structure.
 */
function isRuntimeCredentialEntry(value: unknown): value is RuntimeCredentialEntry {
  return (
    isPlainObject(value) &&
    typeof value.security_name === 'string' &&
    typeof value.scheme === 'string' &&
    isPlainObject(value.credentials)
  );
}

/**
 * Checks if a value matches the RuntimeThingSecrets structure.
 */
function isRuntimeThingSecrets(value: unknown): value is RuntimeThingSecrets {
  return (
    isPlainObject(value) &&
    Array.isArray(value.entries) &&
    value.entries.every((entry) => isRuntimeCredentialEntry(entry))
  );
}

/**
 * Unwraps runtime secrets from their storage envelope.
 * Secrets are sometimes stored as a single-element array in node-wot's credential store.
 */
function unwrapRuntimeThingSecrets(value: unknown): RuntimeThingSecrets | undefined {
  if (isRuntimeThingSecrets(value)) {
    return value;
  }

  if (Array.isArray(value) && value.length === 1 && isRuntimeThingSecrets(value[0])) {
    return value[0];
  }

  return undefined;
}

/**
 * Extracts the primary security definition from an interaction's security metadata array.
 */
function getPrimarySecurityMetadata(metadata: unknown): SecurityMetadata | undefined {
  if (!Array.isArray(metadata) || metadata.length === 0) {
    return undefined;
  }

  const security = metadata[0];
  if (!isPlainObject(security)) {
    return undefined;
  }

  return security as SecurityMetadata;
}

/**
 * Resolves the correct credential entry for a given security metadata.
 * Uses the security name (if annotated) or the scheme as a fallback.
 *
 * @param metadata The security metadata from the interaction.
 * @param secrets The secrets associated with the target Thing.
 * @returns The matched credential entry or undefined.
 */
function resolveCredentialEntry(metadata: unknown, secrets: RuntimeThingSecrets): RuntimeCredentialEntry | undefined {
  const security = getPrimarySecurityMetadata(metadata);
  const securityName =
    typeof security?.[RUNTIME_SECURITY_NAME_FIELD] === 'string' ? security[RUNTIME_SECURITY_NAME_FIELD] : undefined;

  if (securityName) {
    const matchingEntry = secrets.entries.find((entry) => entry.security_name === securityName);
    if (matchingEntry) {
      return matchingEntry;
    }
  }

  const scheme = typeof security?.scheme === 'string' ? security.scheme : undefined;
  if (scheme) {
    const matchingEntries = secrets.entries.filter((entry) => entry.scheme === scheme);
    if (matchingEntries.length === 1) {
      return matchingEntries[0];
    }
    if (matchingEntries.length > 1) {
      throw new Error(
        `Multiple credentials match security scheme '${scheme}' and no security-name match was available`,
      );
    }
  }

  if (secrets.entries.length === 1) {
    return secrets.entries[0];
  }

  return undefined;
}

/**
 * Resolves runtime credentials from the stored secrets based on the interaction's security metadata.
 * This function bridges the gap between node-wot's expected credential format and wot_runtime's dynamic multi-credential support.
 *
 * @param metadata The security metadata from the interaction.
 * @param storedCredentials The raw secrets retrieved from node-wot's credential store.
 * @returns The resolved credentials object (e.g., { username: '...', password: '...' }).
 * @throws {Error} if no matching credentials can be found.
 */
export function resolveRuntimeCredentials(metadata: unknown, storedCredentials: unknown): PlainObject | undefined {
  const secrets = unwrapRuntimeThingSecrets(storedCredentials);
  if (!secrets) {
    if (storedCredentials === undefined) {
      return undefined;
    }
    throw new Error('wot_runtime expected runtime secrets in envelope format');
  }

  const entry = resolveCredentialEntry(metadata, secrets);
  if (entry) {
    return entry.credentials;
  }

  const security = getPrimarySecurityMetadata(metadata);
  const securityName =
    typeof security?.[RUNTIME_SECURITY_NAME_FIELD] === 'string' ? security[RUNTIME_SECURITY_NAME_FIELD] : undefined;
  const scheme = typeof security?.scheme === 'string' ? security.scheme : undefined;

  const requestedSecurity =
    securityName || scheme
      ? securityName
        ? `security definition '${securityName}'`
        : `security scheme '${scheme}'`
      : 'the requested Thing security metadata';

  throw new Error(`No credentials matched ${requestedSecurity}`);
}

/**
 * Patches a node-wot protocol client class to use wot_runtime's custom credential resolution logic.
 * This allows the runtime to provide multiple credentials for a single Thing and select the correct one at runtime.
 *
 * @param clientClass The client class (e.g., HttpClient, CoapsClient) to patch.
 */
export function installClientCredentialPatch(clientClass: ClientSecurityPatchTarget): void {
  const prototype = clientClass.prototype;
  if (patchedSecurityTargets.has(prototype)) {
    return;
  }

  const originalSetSecurity = prototype.setSecurity;
  if (typeof originalSetSecurity !== 'function') {
    throw new Error('Unable to install runtime credential patch for node-wot client');
  }

  prototype.setSecurity = function patchedSetSecurity(metadata: unknown, credentials: unknown): unknown {
    return originalSetSecurity.call(this, metadata, resolveRuntimeCredentials(metadata, credentials));
  };

  patchedSecurityTargets.add(prototype);
}

/**
 * Applies a set of runtime secrets to a target Servient.
 * Clears existing credentials and adds the new ones in the expected envelope format.
 *
 * @param target The target Servient or credential store.
 * @param secrets A map of thingId to RuntimeThingSecrets.
 */
export function applyRuntimeSecrets(target: RuntimeSecretsTarget, secrets: Record<string, unknown>): void {
  if (target.credentialStore instanceof Map) {
    target.credentialStore.clear();
  }

  for (const [thingId, value] of Object.entries(secrets)) {
    if (!isRuntimeThingSecrets(value)) {
      throw new Error(`Invalid runtime secret payload for Thing '${thingId}'`);
    }

    target.addCredentials({ [thingId]: value });
  }
}

/**
 * Annotates a Thing Description with original security definition names.
 * This is necessary because node-wot loses the security name during its normalization process,
 * which wot_runtime needs to disambiguate multiple credentials for the same scheme.
 *
 * @param document The raw Thing Description object.
 */
export function annotateThingDescriptionSecurityNames(document: Record<string, unknown>): void {
  const securityDefinitions = document.securityDefinitions;
  if (!isPlainObject(securityDefinitions)) {
    return;
  }

  for (const [securityName, definition] of Object.entries(securityDefinitions)) {
    if (!isPlainObject(definition)) {
      continue;
    }

    definition[RUNTIME_SECURITY_NAME_FIELD] = securityName;
  }
}
