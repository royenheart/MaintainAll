import { test } from 'node:test'
import assert from 'node:assert/strict'

import { normalizeTriggerFilter } from '../../src/core/triggers/normalize.ts'
import type { TaskTrigger } from '../../src/core/contract.ts'

function trigger(source: TaskTrigger['source'], patch: Partial<TaskTrigger> = {}): TaskTrigger {
  return { id: 't1', source, enabled: true, ...patch }
}

test('normalizeTriggerFilter moves legacy filewatch params into filter', () => {
  assert.deepEqual(
    normalizeTriggerFilter(trigger('filewatch', { params: { path: 'app.log', other: 1 } })),
    {
      id: 't1',
      source: 'filewatch',
      enabled: true,
      params: { other: 1 },
      filter: { path: 'app.log' },
    },
  )
  assert.deepEqual(
    normalizeTriggerFilter(trigger('filewatch', { params: { path: 'app.log' } })),
    {
      id: 't1',
      source: 'filewatch',
      enabled: true,
      filter: { path: 'app.log' },
    },
  )
})

test('normalizeTriggerFilter moves legacy webhook and exec params', () => {
  // Legacy webhook params.path was never a live filter and must not become one.
  assert.deepEqual(
    normalizeTriggerFilter(trigger('webhook', { params: { path: '/hooks/ops' }, filter: { token: 'x' } })),
    { id: 't1', source: 'webhook', enabled: true, filter: { token: 'x' } },
  )
  assert.deepEqual(
    normalizeTriggerFilter(trigger('webhook', { filter: { path: '/hooks/ops', token: 'x' } })),
    {
      id: 't1',
      source: 'webhook',
      enabled: true,
      filter: { token: 'x' },
    },
  )
  assert.deepEqual(
    normalizeTriggerFilter(trigger('webhook', { filter: { path: '/hooks/ops' } })),
    { id: 't1', source: 'webhook', enabled: true },
  )
  assert.deepEqual(
    normalizeTriggerFilter(trigger('filewatch', { params: null as never, filter: {} })),
    { id: 't1', source: 'filewatch', enabled: true },
  )
  assert.deepEqual(
    normalizeTriggerFilter(trigger('exec', { params: { command: 'df -h' } })),
    {
      id: 't1',
      source: 'exec',
      enabled: true,
      filter: { command: 'df -h' },
    },
  )
})

test('normalizeTriggerFilter keeps an existing filter and other sources untouched', () => {
  const existing = trigger('filewatch', {
    params: { path: 'legacy.log' },
    filter: { path: 'current.log', regex: 'ERROR' },
  })
  assert.equal(normalizeTriggerFilter(existing), existing)
  const schedule = trigger('schedule', { params: { path: 'not-used' } })
  assert.equal(normalizeTriggerFilter(schedule), schedule)
})
