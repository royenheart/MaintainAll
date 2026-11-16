import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  filterDockerEvent,
  globToRegExp,
  parseDockerEvent,
  toTriggerEvent,
} from '../../src/core/triggers/docker.ts'

const DIE_EVENT = JSON.stringify({
  status: 'die',
  id: 'abc123',
  Type: 'container',
  Action: 'die',
  type: 'container',
  action: 'die',
  actor: { ID: 'abc123', Attributes: { name: 'web-1', exitCode: '137' } },
  time: 1787500000,
})

test('parseDockerEvent: parses a valid event line', () => {
  const evt = parseDockerEvent(DIE_EVENT)!
  assert.equal(evt.type, 'container')
  assert.equal(evt.action, 'die')
  assert.equal(evt.actor?.Attributes?.name, 'web-1')
  assert.equal(evt.time, 1787500000)
})

test('parseDockerEvent: accepts the real Docker JSON capitalization', () => {
  const evt = parseDockerEvent(JSON.stringify({
    Type: 'container',
    Action: 'die',
    Actor: { ID: 'abc123', Attributes: { name: 'web-1', exitCode: '137' } },
    time: 1787500000,
  }))!
  assert.equal(evt.type, 'container')
  assert.equal(evt.action, 'die')
  assert.equal(evt.actor?.Attributes?.name, 'web-1')
  assert.equal(filterDockerEvent(evt, { container: 'web-*', events: ['die'] }), true)
  assert.equal(toTriggerEvent(evt, '2026-08-23T00:00:00.000Z').payload.container, 'web-1')
})

test('parseDockerEvent: malformed input returns null', () => {
  assert.equal(parseDockerEvent('not json'), null)
  assert.equal(parseDockerEvent(''), null)
  assert.equal(parseDockerEvent('[1,2]'), null)
  assert.equal(parseDockerEvent('42'), null)
})

test('globToRegExp: escapes regex chars and expands *', () => {
  assert.ok(globToRegExp('web-*').test('web-1'))
  assert.ok(!globToRegExp('web-*').test('db-1'))
  assert.ok(globToRegExp('*').test('anything'))
  assert.ok(!globToRegExp('web-*').test('web')) // '*' needs at least empty match -> actually matches 'web-'
  assert.ok(globToRegExp('web-*').test('web-'))
  assert.ok(!globToRegExp('a.b').test('aXb'))
  assert.ok(globToRegExp('a.b').test('a.b'))
})

test('filterDockerEvent: events match type or status', () => {
  const evt = parseDockerEvent(DIE_EVENT)!
  assert.equal(filterDockerEvent(evt, { events: ['die'] }), true)
  assert.equal(filterDockerEvent(evt, { events: ['container'] }), true)
  assert.equal(filterDockerEvent(evt, { events: ['start', 'stop'] }), false)
  assert.equal(filterDockerEvent(evt, {}), true)
})

test('filterDockerEvent: container glob on actor name', () => {
  const evt = parseDockerEvent(DIE_EVENT)!
  assert.equal(filterDockerEvent(evt, { container: 'web-*' }), true)
  assert.equal(filterDockerEvent(evt, { container: 'db-*' }), false)
  assert.equal(filterDockerEvent(evt, { container: 'web-1' }), true)
})

test('filterDockerEvent: combined clauses must both pass', () => {
  const evt = parseDockerEvent(DIE_EVENT)!
  assert.equal(filterDockerEvent(evt, { events: ['die'], container: 'web-*' }), true)
  assert.equal(filterDockerEvent(evt, { events: ['die'], container: 'db-*' }), false)
  assert.equal(filterDockerEvent(evt, { events: ['start'], container: 'web-*' }), false)
})

test('filterDockerEvent: missing actor name fails a container filter', () => {
  const evt = parseDockerEvent('{"type":"container","status":"die"}')!
  assert.equal(filterDockerEvent(evt, { container: '*' }), false)
})

test('toTriggerEvent: normalizes payload and numeric exit code', () => {
  const evt = parseDockerEvent(DIE_EVENT)!
  const trigger = toTriggerEvent(evt, '2026-08-23T00:00:00.000Z')
  assert.equal(trigger.source, 'docker')
  assert.equal(trigger.occurredAt, '2026-08-23T00:00:00.000Z')
  assert.deepEqual(trigger.payload, {
    type: 'container',
    action: 'die',
    status: 'die',
    container: 'web-1',
    exitCode: 137,
  })
})

test('toTriggerEvent: omits absent fields and keeps non-numeric exit codes', () => {
  const evt = parseDockerEvent(
    '{"type":"container","action":"die","actor":{"Attributes":{"name":"x","exitCode":"killed"}}}',
  )!
  const trigger = toTriggerEvent(evt, '2026-08-23T00:00:00.000Z')
  assert.deepEqual(trigger.payload, {
    type: 'container',
    action: 'die',
    container: 'x',
    exitCode: 'killed',
  })
})
