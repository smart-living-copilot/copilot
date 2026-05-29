import fs from 'node:fs';

import wotCoap from '@node-wot/binding-coap';
import wotFile from '@node-wot/binding-file';
import wotHttp from '@node-wot/binding-http';
import wotMBus from '@node-wot/binding-mbus';
import wotModbus from '@node-wot/binding-modbus';
import wotMqtt from '@node-wot/binding-mqtt';
import wotCore from '@node-wot/core';

import { config } from '../config/env.js';
import log from '../logger/index.js';
import { formatError } from '../services/errors.js';
import SWSBBase10 from './codecs/swsb_base10.js';
import { applyRuntimeSecrets, installClientCredentialPatch } from './credentials.js';

const { Servient, ContentSerdes } = wotCore as any;
const { HttpClient, HttpClientFactory, HttpsClientFactory } = wotHttp as any;
const { CoapClientFactory, CoapsClient, CoapsClientFactory } = wotCoap as any;
const { FileClientFactory } = wotFile as any;
const { MBusClientFactory } = wotMBus as any;
const { ModbusClientFactory } = wotModbus as any;
const { MqttClient, MqttClientFactory, MqttsClientFactory } = wotMqtt as any;

/**
 * List of protocols supported by the wot_runtime.
 */
const supportedProtocols = [
  'http',
  'https',
  'coap',
  'coaps',
  'file',
  'mbus+tcp',
  'modbus+tcp',
  'mqtt',
  'mqtts',
] as const;

let wotInstancePromise: Promise<any> | null = null;
let servientReady = false;
let startedAt: string | null = null;
let servientInstance: any = null;
let refreshTimer: ReturnType<typeof setInterval> | null = null;

/**
 * Generates registry service headers for authentication with the central registry.
 */
function registryServiceHeaders(): Record<string, string> | undefined {
  if (!config.registryServiceToken) {
    return undefined;
  }

  return {
    'X-Registry-Service': config.registryServiceName,
    'X-Registry-Service-Token': config.registryServiceToken,
  };
}

/**
 * Fetches runtime secrets (credentials) from the central registry.
 */
async function fetchSecretsFromRegistry(): Promise<Record<string, any> | null> {
  try {
    const url = `${config.registryUrl}/api/runtime/secrets`;
    const res = await fetch(url, {
      headers: {
        Accept: 'application/json',
        ...(registryServiceHeaders() || {}),
      },
    });
    if (!res.ok) {
      log.warn(`Registry secrets endpoint returned ${res.status}`);
      return null;
    }
    const secrets = await res.json();
    return secrets as Record<string, any>;
  } catch (error) {
    log.warn('Failed to fetch secrets from registry:', formatError(error));
    return null;
  }
}

/**
 * Loads runtime secrets from a local JSON file.
 */
function loadSecretsFromFile(): Record<string, any> | null {
  try {
    if (fs.existsSync(config.secretsPath)) {
      const data = fs.readFileSync(config.secretsPath, 'utf8');
      return JSON.parse(data);
    }
    return null;
  } catch (error) {
    log.error('Error loading secrets file:', formatError(error));
    return null;
  }
}

/**
 * Loads secrets from registry or file and applies them to the servient.
 */
async function loadAndApplySecrets(servient: any): Promise<void> {
  // Try the registry first, fall back to file
  let secrets = await fetchSecretsFromRegistry();
  let source = 'registry';

  if (secrets === null) {
    secrets = loadSecretsFromFile();
    source = 'file';
  }

  if (secrets !== null) {
    applyRuntimeSecrets(servient, secrets);
    if (Object.keys(secrets).length > 0) {
      log.info(`Loaded secrets from ${source} for: ${Object.keys(secrets).join(', ')}`);
    } else {
      log.info(`Loaded empty secret set from ${source}`);
    }
  } else {
    log.info('No secrets available from registry or file');
  }
}

/**
 * Refreshes secrets from the registry.
 */
async function refreshSecrets(): Promise<void> {
  if (!servientInstance) return;

  try {
    const secrets = await fetchSecretsFromRegistry();
    if (secrets !== null) {
      applyRuntimeSecrets(servientInstance, secrets);
      if (Object.keys(secrets).length > 0) {
        log.info(`Refreshed secrets from registry for: ${Object.keys(secrets).join(', ')}`);
      } else {
        log.info('Refreshed secrets from registry: no Thing credentials configured');
      }
    }
  } catch (error) {
    log.error('Failed to refresh runtime secrets:', formatError(error));
  }
}

/**
 * Installs credential resolution patches for node-wot protocol clients.
 * This allows wot_runtime to use its custom credential mapping logic.
 */
function installCredentialPatches(): void {
  // Only patch clients that actually need the resolved credential object and
  // expose `setSecurity` on the prototype in a stable way.
  installClientCredentialPatch(HttpClient);
  installClientCredentialPatch(CoapsClient);
  installClientCredentialPatch(MqttClient);
}

/**
 * Registers all supported protocol client factories with the servient.
 */
function registerClientFactories(servient: any): void {
  servient.addClientFactory(new HttpClientFactory());
  servient.addClientFactory(new HttpsClientFactory());
  servient.addClientFactory(new CoapClientFactory());
  servient.addClientFactory(new CoapsClientFactory());
  servient.addClientFactory(new FileClientFactory());
  servient.addClientFactory(new MBusClientFactory());
  servient.addClientFactory(new ModbusClientFactory());
  servient.addClientFactory(new MqttClientFactory());
  servient.addClientFactory(new HttpsClientFactory());
  servient.addClientFactory(new MqttsClientFactory());
}

/**
 * Initializes and starts the node-wot servient.
 */
async function startWot(): Promise<any> {
  const codec = new SWSBBase10('application/json');
  ContentSerdes.get().addCodec(codec);

  installCredentialPatches();

  const servient = new Servient();
  registerClientFactories(servient);

  await loadAndApplySecrets(servient);

  const wot = await servient.start();
  servientInstance = servient;
  servientReady = true;
  startedAt = new Date().toISOString();
  log.info(`Node-WoT initialized for wot_runtime (${supportedProtocols.join(', ')})`);

  // Start periodic refresh
  if (config.secretsRefreshIntervalMs > 0) {
    refreshTimer = setInterval(() => {
      void refreshSecrets();
    }, config.secretsRefreshIntervalMs);
    log.debug(`Scheduled secrets refresh every ${config.secretsRefreshIntervalMs}ms`);
  }

  return wot;
}

/**
 * Returns a promise that resolves to the singleton WoT client instance.
 * Initializes the servient on first call.
 */
export async function getWotClient(): Promise<any> {
  if (!wotInstancePromise) {
    wotInstancePromise = startWot().catch((error) => {
      wotInstancePromise = null;
      servientReady = false;
      throw error;
    });
  }

  return wotInstancePromise;
}

/**
 * Ensures that the WoT servient is initialized and ready.
 */
export async function ensureWotReady(): Promise<void> {
  await getWotClient();
}

/**
 * Cleans up the node-wot servient, stopping periodic tasks.
 */
export async function shutdownWot(): Promise<void> {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
}

/**
 * Returns a snapshot of the current runtime state for health checks.
 */
export function getRuntimeSnapshot(): {
  servientReady: boolean;
  startedAt: string | null;
  protocols: string[];
} {
  return {
    servientReady,
    startedAt,
    protocols: [...supportedProtocols],
  };
}
