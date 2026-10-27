import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  buildTriggerFilter,
  readTriggerFields,
  sourceFieldOf,
} from '../../src/client/trigger-fields.ts'

test('trigger fields: reads filter locations', () => {
  assert.equal(sourceFieldOf('filewatch'), 'path')
  assert.equal(sourceFieldOf('webhook'), 'path')
  assert.equal(sourceFieldOf('exec'), 'command')
  assert.equal(sourceFieldOf('docker'), 'regex')

  assert.deepEqual(readTriggerFields({ filter: { path: 'app.log', regex: 'ERROR' } }), {
    path: 'app.log',
    regex: 'ERROR',
  })
  assert.deepEqual(readTriggerFields({ filter: { command: 'echo hi' } }, 'exec'), {
    path: 'echo hi',
    regex: '',
  })
  assert.deepEqual(readTriggerFields({ filter: { container: 'web-*' } }), {
    path: '',
    regex: 'web-*',
  })
})

test('trigger fields: builds filter.path for filewatch and webhook', () => {
  assert.deepEqual(
    buildTriggerFilter(
      'filewatch',
      { path: 'logs/app.log', regex: 'ERROR' },
      { glob: '*.log', recursive: true },
    ),
    { glob: '*.log', recursive: true, path: 'logs/app.log', regex: 'ERROR' },
  )
  assert.deepEqual(
    buildTriggerFilter('webhook', { path: '', regex: '' }, { token: 'secret' }),
    { token: 'secret' },
  )
})

test('trigger fields: builds filter.command for exec and preserves other filters', () => {
  assert.deepEqual(
    buildTriggerFilter('exec', { path: 'df -h', regex: '' }, { timeoutSeconds: 30 }),
    { timeoutSeconds: 30, command: 'df -h' },
  )
  assert.deepEqual(
    buildTriggerFilter('docker', { path: '', regex: 'web-*' }, { events: ['die'] }),
    { events: ['die'], container: 'web-*' },
  )
  assert.deepEqual(
    buildTriggerFilter('journald', { path: '', regex: 'boom' }, { unit: 'api.service', priority: 3 }),
    { unit: 'api.service', priority: 3, regex: 'boom' },
  )
})

test('trigger fields: an empty edited field removes the old selector', () => {
  assert.deepEqual(
    buildTriggerFilter('filewatch', { path: '', regex: '' }, { path: 'old.log', glob: '*.log' }),
    { glob: '*.log' },
  )
})
