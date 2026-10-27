/**
 * Normalized trigger events.
 *
 * Every trigger source converts its native observation into a `TriggerEvent`
 * (see `contract.ts`) before source-native filters, the CEL `when`
 * expression, and rate limits run. This module only validates and shapes the
 * event; it performs no IO.
 */

import type { TriggerEvent, TriggerSourceKind } from '../contract.ts'

const SOURCE_KINDS: ReadonlySet<string> = new Set([
  'schedule',
  'filewatch',
  'docker',
  'journald',
  'webhook',
  'exec',
  'manual',
])

/** True when `value` is a plain JSON-style object. */
function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * Build a validated `TriggerEvent`.
 *
 * Throws when `source` is not a known source kind, `occurredAt` is not a
 * parseable RFC 3339 instant, or `payload` is not a plain object. The
 * returned payload is a shallow copy so later mutation by the caller cannot
 * corrupt the event.
 */
export function normalizeEvent(
  source: TriggerSourceKind,
  occurredAt: string,
  payload: Record<string, unknown>,
): TriggerEvent {
  if (!SOURCE_KINDS.has(source)) {
    throw new Error(`unknown trigger source kind: ${String(source)}`)
  }
  if (typeof occurredAt !== 'string' || Number.isNaN(Date.parse(occurredAt))) {
    throw new Error(`invalid occurredAt instant: ${String(occurredAt)}`)
  }
  if (!isPlainObject(payload)) {
    throw new Error('trigger event payload must be a plain object')
  }
  return { source, occurredAt, payload: { ...payload } }
}

/** Source kind that produced `event`. */
export function sourceNameOf(event: TriggerEvent): TriggerSourceKind {
  return event.source
}

/** Parsed `occurredAt` instant of `event`. */
export function occurredAtOf(event: TriggerEvent): Date {
  return new Date(event.occurredAt)
}
