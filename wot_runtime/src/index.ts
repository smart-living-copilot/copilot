import http from 'node:http';

import express from 'express';

import { requestHasRuntimeApiToken } from './auth/runtime-auth.js';
import { config } from './config/env.js';
import { createRuntimeRouter } from './http/runtime-routes.js';
import log from './logger/index.js';
import { ensureWotReady, shutdownWot } from './runtime/servient.js';
import { getRuntimeHealth } from './services/runtime-health.js';
import { closeValkeyClient } from './services/valkey-client.js';
import { stopAllSubscriptions } from './services/subscriptions.js';

/**
 * Initializes and starts the wot_runtime Express server.
 * Sets up health endpoints, middleware, routes, and graceful shutdown handlers.
 *
 * @returns A promise that resolves when the server has started.
 */
async function start(): Promise<void> {
  await ensureWotReady();

  const app = express();
  app.use(express.json({ limit: config.requestBodyLimit }));

  app.get('/', (_request, response) => {
    response.json({
      name: 'wot_runtime',
      health: '/health',
      ready: '/health/ready',
      stream: config.streamName,
    });
  });

  app.get(['/health', '/health/live'], async (_request, response) => {
    const health = await getRuntimeHealth();
    response.status(200).json(health);
  });

  app.get(['/health/ready'], async (_request, response) => {
    const health = await getRuntimeHealth();
    response.status(health.status === 'ok' ? 200 : 503).json(health);
  });

  app.use('/runtime', (request, response, next) => {
    if (!requestHasRuntimeApiToken(request)) {
      response.status(401).json({
        detail: 'wot_runtime requires a bearer runtime API token',
      });
      return;
    }

    next();
  });
  app.use('/runtime', createRuntimeRouter());

  const httpServer = http.createServer(app);

  await new Promise<void>((resolve) => {
    httpServer.listen(config.port, config.host, () => {
      log.info(`wot_runtime HTTP server listening on ${config.host}:${config.port}`);
      resolve();
    });
  });

  /**
   * Gracefully shuts down the runtime by stopping subscriptions and closing connections.
   */
  const shutdown = (signal: NodeJS.Signals): void => {
    log.info(`Received ${signal}, shutting down wot_runtime`);
    httpServer.close(() => {
      void stopAllSubscriptions()
        .catch(() => undefined)
        .then(() => shutdownWot())
        .catch(() => undefined)
        .then(() => closeValkeyClient())
        .catch(() => undefined)
        .finally(() => {
          process.exit(0);
        });
    });
  };

  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
}

start().catch((error) => {
  const message = error instanceof Error ? error.stack || error.message : String(error);
  log.error(`Failed to start wot_runtime: ${message}`);
  process.exit(1);
});
