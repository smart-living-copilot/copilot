import assert from 'node:assert/strict';
import { createServer, type Server } from 'node:http';
import { after, before, test } from 'node:test';

import wotHttp from '@node-wot/binding-http';
import wotCore from '@node-wot/core';

const { Servient } = wotCore as any;
const { HttpClientFactory } = wotHttp as any;

let server: Server;
let servient: any;
let thing: any;
let receivedBody: unknown;

before(async () => {
  server = createServer((request, response) => {
    const chunks: Buffer[] = [];
    request.on('data', (chunk: Buffer) => chunks.push(chunk));
    request.on('end', () => {
      response.setHeader('Content-Type', 'application/json');
      if (request.method === 'GET') {
        response.end(
          JSON.stringify({
            path: request.url?.split('?')[0],
            query: new URL(request.url || '/', 'http://localhost').searchParams.get('verbose'),
          }),
        );
        return;
      }
      receivedBody = JSON.parse(Buffer.concat(chunks).toString('utf-8'));
      response.end(JSON.stringify({ created: true }));
    });
  });
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  const port = typeof address === 'object' && address ? address.port : 0;
  const base = `http://127.0.0.1:${port}`;

  servient = new Servient();
  servient.addClientFactory(new HttpClientFactory());
  const wot = await servient.start();
  thing = await wot.consume({
    '@context': 'https://www.w3.org/2022/wot/td/v1.1',
    id: 'urn:test:generated-openapi',
    title: 'Generated OpenAPI Thing',
    security: ['nosec_sc'],
    securityDefinitions: { nosec_sc: { scheme: 'nosec' } },
    actions: {
      getPet: {
        safe: true,
        idempotent: true,
        uriVariables: {
          petId: { type: 'string' },
          verbose: { type: 'boolean' },
        },
        output: {
          type: 'object',
          properties: { path: { type: 'string' }, query: { type: 'string' } },
        },
        forms: [
          {
            href: `${base}/pets/{petId}{?verbose}`,
            op: ['invokeaction'],
            'htv:methodName': 'GET',
            contentType: 'application/json',
          },
        ],
      },
      createPet: {
        input: {
          type: 'object',
          required: ['name'],
          properties: { name: { type: 'string' } },
        },
        output: {
          type: 'object',
          properties: { created: { type: 'boolean' } },
        },
        forms: [
          {
            href: `${base}/pets`,
            op: ['invokeaction'],
            'htv:methodName': 'POST',
            contentType: 'application/json',
          },
        ],
      },
    },
  });
});

after(async () => {
  await servient.shutdown();
  await new Promise<void>((resolve) => server.close(() => resolve()));
});

test('generated GET actions expand path and query uriVariables without a body', async () => {
  const output = await thing.invokeAction('getPet', undefined, {
    uriVariables: { petId: '42', verbose: true },
  });
  assert.deepEqual(await output.value(), { path: '/pets/42', query: 'true' });
});

test('generated POST actions send and decode JSON', async () => {
  const output = await thing.invokeAction('createPet', { name: 'Ada' });
  assert.deepEqual(receivedBody, { name: 'Ada' });
  assert.deepEqual(await output.value(), { created: true });
});
