import assert from 'node:assert/strict';
import test from 'node:test';

import {
  getFirstSearchParam,
  getLocalReturnTo,
  isCollectionReturnTo,
  withReturnTo,
} from './return-to';

test('getFirstSearchParam reads scalar and array values', () => {
  assert.equal(getFirstSearchParam('value'), 'value');
  assert.equal(getFirstSearchParam(['first', 'second']), 'first');
  assert.equal(getFirstSearchParam(undefined), undefined);
});

test('getLocalReturnTo only accepts local paths', () => {
  assert.equal(getLocalReturnTo('/jobs/123', '/jobs'), '/jobs/123');
  assert.equal(getLocalReturnTo('https://example.test', '/jobs'), '/jobs');
  assert.equal(getLocalReturnTo('//example.test/jobs', '/jobs'), '/jobs');
  assert.equal(getLocalReturnTo(undefined, '/jobs'), '/jobs');
});

test('withReturnTo appends an encoded return path', () => {
  assert.equal(
    withReturnTo('/jobs/123/edit', '/jobs?tab=paused'),
    '/jobs/123/edit?returnTo=%2Fjobs%3Ftab%3Dpaused',
  );
  assert.equal(withReturnTo('/jobs/123/edit', undefined), '/jobs/123/edit');
});

test('isCollectionReturnTo matches collection pages', () => {
  assert.equal(isCollectionReturnTo('/jobs', '/jobs'), true);
  assert.equal(isCollectionReturnTo('/jobs?tab=paused', '/jobs'), true);
  assert.equal(isCollectionReturnTo('/jobs/123', '/jobs'), false);
});
