import { test } from 'node:test'
import assert from 'node:assert/strict'
import { evaluateCel, validateCel } from '../../src/core/triggers/condition.ts'
import { normalizeEvent } from '../../src/core/triggers/event.ts'
import type { TriggerEvent } from '../../src/core/contract.ts'

function event(payload: Record<string, unknown> = {}): TriggerEvent {
  return normalizeEvent('docker', '2026-08-23T00:00:00.000Z', payload)
}

test('evaluateCel: empty or missing expression returns true', () => {
  assert.equal(evaluateCel('', event()), true)
  assert.equal(evaluateCel('   ', event()), true)
  assert.equal(evaluateCel(undefined, event()), true)
})

test('evaluateCel: literals and comparisons', () => {
  assert.equal(evaluateCel('1 == 1', event()), true)
  assert.equal(evaluateCel('1 != 2', event()), true)
  assert.equal(evaluateCel('2 > 1', event()), true)
  assert.equal(evaluateCel('2 >= 2', event()), true)
  assert.equal(evaluateCel('1 < 2', event()), true)
  assert.equal(evaluateCel('2 <= 1', event()), false)
  assert.equal(evaluateCel("'a' < 'b'", event()), true)
  assert.equal(evaluateCel('true', event()), true)
  assert.equal(evaluateCel('!false', event()), true)
  assert.equal(evaluateCel("null == null", event()), true)
})

test('evaluateCel: identifier roots and dot access', () => {
  const evt = event({ container: 'web-1', exitCode: 0, nested: { level: 'error' } })
  assert.equal(evaluateCel("source == 'docker'", evt), true)
  assert.equal(evaluateCel("occurredAt == '2026-08-23T00:00:00.000Z'", evt), true)
  assert.equal(evaluateCel("payload.container == 'web-1'", evt), true)
  assert.equal(evaluateCel('payload.exitCode == 0', evt), true)
  assert.equal(evaluateCel("event.payload.nested.level == 'error'", evt), true)
  assert.equal(evaluateCel("event.source == 'docker'", evt), true)
})

test('evaluateCel: logical operators and parentheses', () => {
  const evt = event({ exitCode: 1, container: 'db' })
  assert.equal(evaluateCel('payload.exitCode == 1 && true', evt), true)
  assert.equal(evaluateCel('payload.exitCode == 0 || true', evt), true)
  assert.equal(evaluateCel('!(payload.exitCode == 0)', evt), true)
  assert.equal(
    evaluateCel("(payload.exitCode == 0 || payload.exitCode == 1) && payload.container == 'db'", evt),
    true,
  )
  assert.equal(evaluateCel('true || (1 < 0 && true)', evt), true)
})

test('evaluateCel: whitelisted string functions', () => {
  const evt = event({ message: 'disk full on /dev/sda1' })
  assert.equal(evaluateCel("matches(payload.message, 'disk (full|empty)')", evt), true)
  assert.equal(evaluateCel("matches(payload.message, '^disk')", evt), true)
  assert.equal(evaluateCel("startsWith(payload.message, 'disk')", evt), true)
  assert.equal(evaluateCel("endsWith(payload.message, 'sda1')", evt), true)
  assert.equal(evaluateCel("contains(payload.message, 'full')", evt), true)
  assert.equal(evaluateCel("contains(payload.message, 'quiet')", evt), false)
})

test('evaluateCel: unknown identifier throws', () => {
  assert.throws(() => evaluateCel('foo == 1', event()), /unknown identifier/)
  assert.throws(() => evaluateCel('process.env', event()), /unknown identifier/)
})

test('evaluateCel: non-whitelisted function throws', () => {
  assert.throws(() => evaluateCel("exec('ls')", event()), /not whitelisted/)
  assert.throws(() => evaluateCel("now() > 0", event()), /not whitelisted/)
})

test('evaluateCel: invalid syntax throws', () => {
  assert.throws(() => evaluateCel('payload.container ==', event()))
  assert.throws(() => evaluateCel('(true', event()))
  assert.throws(() => evaluateCel('true true', event()), /trailing/)
  assert.throws(() => evaluateCel("'unterminated", event()), /unterminated/)
  assert.throws(() => evaluateCel('payload.', event()))
})

test('evaluateCel: type errors throw', () => {
  const evt = event({ message: 'hi', exitCode: 0 })
  assert.throws(() => evaluateCel('payload.message < 3', evt), /two numbers or two strings/)
  assert.throws(() => evaluateCel("payload.exitCode && true", evt), /must be a boolean/)
  assert.throws(() => evaluateCel('!payload.message', evt), /must be a boolean/)
  assert.throws(() => evaluateCel('matches(payload.exitCode, "0")', evt), /must be a string/)
  assert.throws(() => evaluateCel('payload.message', evt), /must evaluate to a boolean/)
  assert.throws(() => evaluateCel('payload.exitCode.foo == 1', evt), /non-object/)
})

test('evaluateCel: missing payload keys yield undefined comparisons', () => {
  const evt = event({})
  assert.equal(evaluateCel('payload.missing == null', evt), false)
  assert.equal(evaluateCel('payload.missing != 1', evt), true)
})

test('evaluateCel: inherited object members are not whitelisted', () => {
  const event = normalizeEvent('docker', '2026-08-23T00:00:00.000Z', {})
  assert.throws(() => evaluateCel("toString() != ''", event), /function not whitelisted/)
  assert.throws(() => evaluateCel("hasOwnProperty('x')", event), /function not whitelisted/)
})

test('validateCel: rejects unknown roots/functions and literal regex errors before evaluation', () => {
  assert.throws(() => validateCel('unknownFn(event.source)'), /function not whitelisted/)
  assert.throws(() => validateCel('wrongRoot == true'), /unknown identifier/)
  assert.throws(() => validateCel('matches(event.source, "[")'), /invalid regular expression/)
  assert.throws(() => validateCel('matches(event.source)'), /expected 2 arguments/)
  assert.throws(() => validateCel('contains("x")'), /expected 2 arguments/)
  assert.throws(() => validateCel('startsWith(source, 1)'), /second argument must be a string/)
  assert.doesNotThrow(() => validateCel("event.payload.line == 'ERROR' && matches(event.source, '^file')"))
})
