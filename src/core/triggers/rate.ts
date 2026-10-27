/**
 * Debounce and rate limiting for trigger firings.
 *
 * State is plain JSON (`lastFiredAt` + a rolling list of fire timestamps) so
 * it persists directly into `storages/trigger-state.json`. The limiter owns a
 * private copy of the state it was constructed with; callers persist the
 * state returned by `tryFire`.
 */

import type { RateState, TriggerRateLimit, TriggerState } from '../contract.ts'

export type { RateState } from '../contract.ts'



export type FireDecision =
  | { allowed: true; state: RateState }
  | { allowed: false; reason: 'min-interval' | 'rate-limit' }

const HOUR_MS = 60 * 60 * 1000

/** Fresh, empty rate-limit state. */
export function emptyRateState(): RateState {
  return { fireTimestamps: [] }
}

/**
 * Validate untrusted data as `RateState`, filling defaults. Throws on
 * structurally invalid input (non-array timestamps, non-string entries).
 */
export function deserializeRateState(raw: unknown): RateState {
  if (typeof raw !== 'object' || raw === null) {
    throw new Error('rate state must be an object')
  }
  const record = raw as Record<string, unknown>
  if (record.lastFiredAt !== undefined && typeof record.lastFiredAt !== 'string') {
    throw new Error('rate state lastFiredAt must be a string')
  }
  const timestamps = record.fireTimestamps
  if (timestamps !== undefined && !Array.isArray(timestamps)) {
    throw new Error('rate state fireTimestamps must be an array')
  }
  const fireTimestamps = ((timestamps ?? []) as unknown[]).map((ts) => {
    if (typeof ts !== 'string') {
      throw new Error('rate state fireTimestamps entries must be strings')
    }
    return ts
  })
  const state: RateState = { fireTimestamps }
  if (record.lastFiredAt !== undefined) state.lastFiredAt = record.lastFiredAt
  return state
}

/** Read the rate state of one trigger out of persisted `TriggerState`. */
export function rateStateOf(state: TriggerState, triggerId: string): RateState {
  const raw = state.triggers[triggerId]
  return raw ? deserializeRateState(raw) : emptyRateState()
}

/** Write one trigger's rate state back into persisted `TriggerState`. */
export function withRateState(state: TriggerState, triggerId: string, rate: RateState): TriggerState {
  state.triggers[triggerId] = deserializeRateState(rate)
  return state
}

export class RateLimiter {
  private state: RateState
  private readonly opts: TriggerRateLimit
  private readonly now: () => Date

  constructor(state: RateState, opts: TriggerRateLimit, now: () => Date = () => new Date()) {
    if (!Number.isFinite(opts.minIntervalSeconds) || opts.minIntervalSeconds < 0) {
      throw new Error('rate minIntervalSeconds must be a non-negative finite number')
    }
    if (!Number.isFinite(opts.maxPerHour) || opts.maxPerHour < 0) {
      throw new Error('rate maxPerHour must be a non-negative finite number')
    }
    this.state = deserializeRateState(state)
    this.opts = opts
    this.now = now
  }

  /**
   * Attempt a firing at `now()`. On success the internal state is updated
   * (timestamps pruned to the rolling hour, `lastFiredAt` set) and returned
   * for persistence. On denial the state is untouched.
   */
  tryFire(): FireDecision {
    const decision = this.decide(this.now().getTime())
    if (decision.allowed) {
      this.state = decision.state
    }
    return decision
  }

  /** Same decision as `tryFire` but never mutates internal state. */
  peek(): FireDecision {
    return this.decide(this.now().getTime())
  }

  private decide(nowMs: number): FireDecision {
    const minIntervalMs = this.opts.minIntervalSeconds * 1000
    if (this.state.lastFiredAt !== undefined) {
      const lastMs = Date.parse(this.state.lastFiredAt)
      if (!Number.isNaN(lastMs) && nowMs - lastMs < minIntervalMs) {
        return { allowed: false, reason: 'min-interval' }
      }
    }
    const cutoff = nowMs - HOUR_MS
    const recent = this.state.fireTimestamps.filter((ts) => {
      const ms = Date.parse(ts)
      return !Number.isNaN(ms) && ms > cutoff
    })
    // Zero means no hourly cap; the Save dialog uses 0 for its default.
    if (this.opts.maxPerHour > 0 && recent.length >= this.opts.maxPerHour) {
      return { allowed: false, reason: 'rate-limit' }
    }
    const firedAt = new Date(nowMs).toISOString()
    return {
      allowed: true,
      state: { lastFiredAt: firedAt, fireTimestamps: [...recent, firedAt] },
    }
  }
}
