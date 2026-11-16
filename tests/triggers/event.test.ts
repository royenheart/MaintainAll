import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  normalizeEvent,
  occurredAtOf,
  sourceNameOf,
} from '../../src/core/triggers/event.ts'

test('normalizeEvent: builds a validated event with a copied payload', () => {
  const payload = { container: 'web-1' }
  const event = normalizeEvent('docker', '2026-08-23T00:00:00.000Z', payload)
  assert.equal(event.source, 'docker')
  assert.equal(event.occurredAt, '2026-08-23T00:00:00.000Z')
  assert.deepEqual(event.payload, payload)
  assert.notEqual(event.payload, payload)
})

test('normalizeEvent: rejects bad source, instant, or payload', () => {
  assert.throws(
    () => normalizeEvent('nope' as 'docker', '2026-08-23T00:00:00.000Z', {}),
    /unknown trigger source/,
  )
  assert.throws(() => normalizeEvent('docker', 'not a date', {}), /invalid occurredAt/)
  assert.throws(
    () => normalizeEvent('docker', '2026-08-23T00:00:00.000Z', null as never),
    /plain object/,
  )
  assert.throws(
    () => normalizeEvent('docker', '2026-08-23T00:00:00.000Z', [] as never),
    /plain object/,
  )
})

test('sourceNameOf / occurredAtOf expose event fields', () => {
  const event = normalizeEvent('webhook', '2026-08-23T00:00:00.000Z', {})
  assert.equal(sourceNameOf(event), 'webhook')
  assert.equal(occurredAtOf(event).toISOString(), '2026-08-23T00:00:00.000Z')
})
