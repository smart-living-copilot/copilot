import wotCoap from "@node-wot/binding-coap";
import wotFile from "@node-wot/binding-file";
import wotHttp from "@node-wot/binding-http";
import wotMBus from "@node-wot/binding-mbus";
import wotModbus from "@node-wot/binding-modbus";
import wotMqtt from "@node-wot/binding-mqtt";
import wotCore from "@node-wot/core";

import { config } from "./config.js";
import log from "./logger.js";

const { Servient } = wotCore as any;
const { HttpClientFactory, HttpsClientFactory, HttpServer } = wotHttp as any;
const { CoapClientFactory, CoapsClientFactory } = wotCoap as any;
const { FileClientFactory } = wotFile as any;
const { MBusClientFactory } = wotMBus as any;
const { ModbusClientFactory } = wotModbus as any;
const { MqttClientFactory, MqttsClientFactory } = wotMqtt as any;

let wotPromise: Promise<any> | null = null;
let servientInstance: any = null;

function registerFactories(servient: any): void {
  servient.addClientFactory(new HttpClientFactory());
  servient.addClientFactory(new HttpsClientFactory());
  servient.addClientFactory(new CoapClientFactory());
  servient.addClientFactory(new CoapsClientFactory());
  servient.addClientFactory(new FileClientFactory());
  servient.addClientFactory(new MBusClientFactory());
  servient.addClientFactory(new ModbusClientFactory());
  servient.addClientFactory(new MqttClientFactory());
  servient.addClientFactory(new MqttsClientFactory());
}

/** Starts or returns the shared node-wot producer runtime. */
export async function getWot(): Promise<any> {
  if (!wotPromise) {
    wotPromise = (async () => {
      const servient = new Servient();
      registerFactories(servient);
      const serverOptions: Record<string, unknown> = {
        port: config.wotPort,
        address: config.wotHost,
      };
      if (config.publicBaseUrl) {
        serverOptions.baseUri = config.publicBaseUrl;
      }
      servient.addServer(new HttpServer(serverOptions));
      const wot = await servient.start();
      servientInstance = servient;
      log.info(
        `virtual-servient WoT producer listening on ${config.wotHost}:${config.wotPort}`,
      );
      return wot;
    })().catch((error) => {
      wotPromise = null;
      throw error;
    });
  }
  return wotPromise;
}

/** Shuts down the node-wot producer runtime. */
export async function shutdownWot(): Promise<void> {
  await servientInstance?.shutdown?.().catch(() => undefined);
}
