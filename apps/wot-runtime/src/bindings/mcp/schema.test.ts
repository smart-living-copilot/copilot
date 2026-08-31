import assert from 'node:assert/strict';
import test from 'node:test';

import { toDataSchema } from './schema.js';

test('a plain object schema survives with its properties and required list', () => {
  const result = toDataSchema({
    type: 'object',
    properties: { name: { type: 'string', description: 'Who to greet' } },
    required: ['name'],
  });

  assert.deepEqual(result, {
    type: 'object',
    properties: { name: { type: 'string', description: 'Who to greet' } },
    required: ['name'],
  });
});

test('a local $ref is resolved against $defs', () => {
  const result = toDataSchema({
    type: 'object',
    properties: { point: { $ref: '#/$defs/Point' } },
    $defs: { Point: { type: 'object', properties: { x: { type: 'number' } } } },
  });

  assert.deepEqual(result.properties, {
    point: { type: 'object', properties: { x: { type: 'number' } } },
  });
});

test('the older definitions keyword resolves too', () => {
  const result = toDataSchema({
    type: 'object',
    properties: { item: { $ref: '#/definitions/Item' } },
    definitions: { Item: { type: 'string' } },
  });

  assert.deepEqual(result.properties, { item: { type: 'string' } });
});

test('an optional field written as anyOf with null collapses to its real type', () => {
  const result = toDataSchema({
    type: 'object',
    properties: { nickname: { anyOf: [{ type: 'string' }, { type: 'null' }] } },
  });

  assert.deepEqual(result.properties, { nickname: { type: 'string' } });
});

test('a description on the union survives the collapse', () => {
  const result = toDataSchema({
    type: 'object',
    properties: {
      nickname: { anyOf: [{ type: 'string' }, { type: 'null' }], description: 'Optional name' },
    },
  });

  assert.deepEqual(result.properties, { nickname: { type: 'string', description: 'Optional name' } });
});

test('a nullable type array collapses the same way', () => {
  assert.deepEqual(toDataSchema({ type: ['string', 'null'] }), { type: 'string' });
});

test('a genuine union of two types has no WoT equivalent and drops its type', () => {
  const result = toDataSchema({ anyOf: [{ type: 'string' }, { type: 'number' }] });

  assert.deepEqual(result, {});
});

test('constraints WoT can express are preserved', () => {
  const result = toDataSchema({
    type: 'string',
    enum: ['New York', 'Chicago'],
    minLength: 2,
    pattern: '^[A-Z]',
  });

  assert.deepEqual(result, { type: 'string', enum: ['New York', 'Chicago'], minLength: 2, pattern: '^[A-Z]' });
});

test('keywords WoT cannot express are dropped rather than passed through', () => {
  const result = toDataSchema({
    type: 'object',
    properties: { a: { type: 'string' } },
    additionalProperties: false,
    patternProperties: { '^x-': { type: 'string' } },
    allOf: [{ type: 'object' }],
    $schema: 'https://json-schema.org/draft/2020-12/schema',
  });

  assert.deepEqual(Object.keys(result).sort(), ['properties', 'type']);
});

test('arrays carry their item schema', () => {
  const result = toDataSchema({ type: 'array', items: { $ref: '#/$defs/T' }, $defs: { T: { type: 'integer' } } });

  assert.deepEqual(result, { type: 'array', items: { type: 'integer' } });
});

test('an unresolvable remote $ref yields an untyped value instead of failing', () => {
  assert.deepEqual(toDataSchema({ $ref: 'https://example.com/schema.json#/Thing' }), {});
});

test('a recursive $ref terminates instead of looping', () => {
  const result = toDataSchema({
    $defs: { Node: { type: 'object', properties: { child: { $ref: '#/$defs/Node' } } } },
    $ref: '#/$defs/Node',
  });

  assert.equal(result.type, 'object');
});

test('a non-object schema yields nothing translatable', () => {
  assert.deepEqual(toDataSchema(undefined), {});
  assert.deepEqual(toDataSchema('string'), {});
  assert.deepEqual(toDataSchema(null), {});
});
