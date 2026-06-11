import http from 'node:http';

import express from 'express';

import { config } from './config.js';
import { startDefinitionEventLoop, stopDefinitionEventLoop } from './events.js';
import log from './logger.js';
import { activeCount, reconcileAll, stopAll } from './manager.js';
import { closeRedisClient } from './redis.js';
import { getWot, shutdownWot } from './servient.js';

async function start(): Promise<void> {
  await getWot();

  const app = express();
  app.get('/', (_request, response) => {
    response.json({ name: 'virtual-servient', health: '/health', activeThings: activeCount() });
  });
  app.get(['/health', '/health/live', '/health/ready'], (_request, response) => {
    response.json({ status: 'ok', activeThings: activeCount() });
  });

  const server = http.createServer(app);
  await new Promise<void>((resolve) => {
    server.listen(config.port, config.host, () => {
      log.info(`virtual-servient HTTP server listening on ${config.host}:${config.port}`);
      resolve();
    });
  });

  await startDefinitionEventLoop();
  const reconcile = () => {
    void reconcileAll().catch((error) => log.warn(`Periodic reconciliation failed: ${error}`));
  };
  reconcile();
  const reconcileTimer = setInterval(reconcile, config.reconcileIntervalMs);

  const shutdown = (signal: NodeJS.Signals): void => {
    log.info(`Received ${signal}, shutting down virtual-servient`);
    clearInterval(reconcileTimer);
    stopDefinitionEventLoop();
    server.close(() => {
      void stopAll()
        .then(() => shutdownWot())
        .then(() => closeRedisClient())
        .finally(() => process.exit(0));
    });
  };

  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
}

start().catch((error) => {
  log.error(`Failed to start virtual-servient: ${error instanceof Error ? error.stack || error.message : String(error)}`);
  process.exit(1);
});
