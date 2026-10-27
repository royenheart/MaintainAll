/**
 * Docker event stream parsing and source-native filtering.
 *
 * Pure functions over the JSON lines produced by `docker events`; the host
 * owns the actual socket/stream. Nothing here performs IO.
 */

import type { TriggerEvent } from '../contract.ts'
import { normalizeEvent } from './event.ts'

export interface DockerEvent {
  type?: string
  action?: string
  actor?: { Attributes?: Record<string, string> }
  status?: string
  time?: number
}

interface RawDockerEvent {
  Type?: unknown
  type?: unknown
  Action?: unknown
  action?: unknown
  Actor?: unknown
  actor?: unknown
  status?: unknown
  time?: unknown
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined
}

function actorOf(value: unknown): { Attributes?: Record<string, string> } | undefined {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return undefined
  const raw = value as { Attributes?: unknown; attributes?: unknown }
  const attributes = raw.Attributes ?? raw.attributes
  if (typeof attributes !== 'object' || attributes === null || Array.isArray(attributes)) return {}
  const result: Record<string, string> = {}
  for (const [key, item] of Object.entries(attributes)) {
    if (typeof item === 'string') result[key] = item
  }
  return { Attributes: result }
}

export interface DockerEventFilter {
  /** Matches when `evt.type` or `evt.status` equals one of the entries. */
  events?: string[]
  /** Container name glob; `*` matches any sequence of characters. */
  container?: string
}

/** Parse one JSON line of docker event output. Returns null when malformed. */
export function parseDockerEvent(json: string): DockerEvent | null {
  let value: unknown
  try {
    value = JSON.parse(json)
  } catch {
    return null
  }
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return null
  }
  const raw = value as RawDockerEvent
  const type = stringValue(raw.Type) ?? stringValue(raw.type)
  const action = stringValue(raw.Action) ?? stringValue(raw.action)
  const actor = actorOf(raw.Actor) ?? actorOf(raw.actor)
  const status = stringValue(raw.status)
  const time = typeof raw.time === 'number' ? raw.time : undefined
  return {
    ...(type === undefined ? {} : { type }),
    ...(action === undefined ? {} : { action }),
    ...(actor === undefined ? {} : { actor }),
    ...(status === undefined ? {} : { status }),
    ...(time === undefined ? {} : { time }),
  }
}

/** Convert a `*` glob into an anchored RegExp; everything else is literal. */
export function globToRegExp(glob: string): RegExp {
  const escaped = glob.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\\\*/g, '.*')
  return new RegExp(`^${escaped}$`)
}

/** Source-native docker filter. Both clauses must pass when present. */
export function filterDockerEvent(evt: DockerEvent, filter: DockerEventFilter): boolean {
  if (filter.events !== undefined) {
    const matches = filter.events.some((name) => evt.type === name || evt.status === name || evt.action === name)
    if (!matches) return false
  }
  if (filter.container !== undefined) {
    const name = evt.actor?.Attributes?.name
    if (name === undefined || !globToRegExp(filter.container).test(name)) return false
  }
  return true
}

function exitCodeOf(attributes: Record<string, string> | undefined): number | string | undefined {
  const raw = attributes?.exitCode
  if (raw === undefined) return undefined
  return /^-?\d+$/.test(raw) ? Number(raw) : raw
}

/** Normalize a docker event into a `TriggerEvent`. */
export function toTriggerEvent(evt: DockerEvent, occurredAt: string): TriggerEvent {
  const attributes = evt.actor?.Attributes
  const payload: Record<string, unknown> = {
    type: evt.type,
    action: evt.action,
    status: evt.status,
    container: attributes?.name,
    exitCode: exitCodeOf(attributes),
  }
  for (const key of Object.keys(payload)) {
    if (payload[key] === undefined) delete payload[key]
  }
  return normalizeEvent('docker', occurredAt, payload)
}
