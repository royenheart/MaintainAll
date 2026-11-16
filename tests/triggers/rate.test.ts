import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  RateLimiter,
  deserializeRateState,
  emptyRateState,
  rateStateOf,
  withRateState,
  type RateState,
} from '../../src/core/triggers/rate.ts'
import type { TriggerState } from '../../src/core/contract.ts'

const BASE = Date.parse('2026-08-23T00:00:00.000Z')

function clock(start: number) {
  let current = start
  return {
    now: () => new Date(current),
    advance(ms: number) {
      current += ms
    },
  }
}

function opts(overrides: Partial<{ minIntervalSeconds: number; maxPerHour: number }> = {}) {
  return { minIntervalSeconds: 60, maxPerHour: 5, ...overrides }
}

test('tryFire: empty state allows and records the firing', () => {
  const c = clock(BASE)
  const limiter = new RateLimiter(emptyRateState(), opts(), c.now)
  const result = limiter.tryFire()
  assert.equal(result.allowed, true)
  if (result.allowed) {
    assert.equal(result.state.lastFiredAt, '2026-08-23T00:00:00.000Z')
    assert.deepEqual(result.state.fireTimestamps, ['2026-08-23T00:00:00.000Z'])
  }
})

test('tryFire: min interval blocks until enough time passes', () => {
  const c = clock(BASE)
  const limiter = new RateLimiter(emptyRateState(), opts({ minIntervalSeconds: 60 }), c.now)
  assert.equal(limiter.tryFire().allowed, true)

  c.advance(59_000)
  const denied = limiter.tryFire()
  assert.deepEqual(denied, { allowed: false, reason: 'min-interval' })

  c.advance(1_000) // exactly 60s later: allowed (boundary inclusive)
  assert.equal(limiter.tryFire().allowed, true)
})

test('tryFire: max per hour blocks within the rolling window', () => {
  const c = clock(BASE)
  const limiter = new RateLimiter(
    emptyRateState(),
    opts({ minIntervalSeconds: 0, maxPerHour: 3 }),
    c.now,
  )
  assert.equal(limiter.tryFire().allowed, true)
  c.advance(1_000)
  assert.equal(limiter.tryFire().allowed, true)
  c.advance(1_000)
  assert.equal(limiter.tryFire().allowed, true)
  c.advance(1_000)
  assert.deepEqual(limiter.tryFire(), { allowed: false, reason: 'rate-limit' })

  // The first firing falls out of the rolling hour; firing resumes.
  c.advance(60 * 60 * 1000)
  assert.equal(limiter.tryFire().allowed, true)
})

test('tryFire: stale timestamps are pruned from returned state', () => {
  const stale = new Date(BASE - 2 * 60 * 60 * 1000).toISOString()
  const state: RateState = { lastFiredAt: stale, fireTimestamps: [stale] }
  const c = clock(BASE)
  const limiter = new RateLimiter(state, opts(), c.now)
  const result = limiter.tryFire()
  assert.equal(result.allowed, true)
  if (result.allowed) {
    assert.deepEqual(result.state.fireTimestamps, ['2026-08-23T00:00:00.000Z'])
  }
})

test('tryFire: min-interval check wins over the rate check', () => {
  const c = clock(BASE)
  const limiter = new RateLimiter(
    emptyRateState(),
    opts({ minIntervalSeconds: 60, maxPerHour: 1 }),
    c.now,
  )
  assert.equal(limiter.tryFire().allowed, true)
  c.advance(1_000)
  assert.deepEqual(limiter.tryFire(), { allowed: false, reason: 'min-interval' })
})

test('tryFire: constructor input state is not mutated', () => {
  const input: RateState = { fireTimestamps: [] }
  const c = clock(BASE)
  const limiter = new RateLimiter(input, opts(), c.now)
  limiter.tryFire()
  assert.deepEqual(input, { fireTimestamps: [] })
})

test('peek: reports the decision without mutating state', () => {
  const c = clock(BASE)
  const limiter = new RateLimiter(emptyRateState(), opts({ minIntervalSeconds: 60 }), c.now)
  const peeked = limiter.peek()
  assert.equal(peeked.allowed, true)
  // peek did not consume the firing.
  assert.equal(limiter.tryFire().allowed, true)

  const deniedPeek = limiter.peek()
  assert.deepEqual(deniedPeek, { allowed: false, reason: 'min-interval' })
  // State still intact after peeking a denial.
  c.advance(60_000)
  assert.equal(limiter.tryFire().allowed, true)
})

test('serialize/deserialize round-trip and validation', () => {
  const state: RateState = {
    lastFiredAt: '2026-08-23T00:00:00.000Z',
    fireTimestamps: ['2026-08-23T00:00:00.000Z'],
  }
  const copy = deserializeRateState(state)
  assert.deepEqual(copy, state)
  assert.notEqual(copy.fireTimestamps, state.fireTimestamps)

  assert.deepEqual(deserializeRateState({}), { fireTimestamps: [] })
  assert.throws(() => deserializeRateState(null), /must be an object/)
  assert.throws(() => deserializeRateState({ fireTimestamps: 'x' }), /must be an array/)
  assert.throws(() => deserializeRateState({ fireTimestamps: [1] }), /must be strings/)
  assert.throws(() => deserializeRateState({ lastFiredAt: 3 }), /must be a string/)
})

test('TriggerState helpers: round-trip a per-trigger rate state', () => {
  const triggerState: TriggerState = {
    version: 2,
    triggers: {},
    schedules: {},
    filewatch: {},
    exec: {},
  }
  assert.deepEqual(rateStateOf(triggerState, 't1'), { fireTimestamps: [] })

  const rate: RateState = {
    lastFiredAt: '2026-08-23T00:00:00.000Z',
    fireTimestamps: ['2026-08-23T00:00:00.000Z'],
  }
  withRateState(triggerState, 't1', rate)
  assert.deepEqual(rateStateOf(triggerState, 't1'), rate)
  // JSON round-trip like the atomic state file does.
  const persisted = JSON.parse(JSON.stringify(triggerState)) as TriggerState
  assert.deepEqual(rateStateOf(persisted, 't1'), rate)
})

test('tryFire: zero maxPerHour means no hourly cap', () => {
  const now = Date.parse('2026-08-23T00:00:00.000Z')
  const limiter = new RateLimiter({ fireTimestamps: [] }, { minIntervalSeconds: 0, maxPerHour: 0 }, () => new Date(now))
  assert.equal(limiter.tryFire().allowed, true)
})
