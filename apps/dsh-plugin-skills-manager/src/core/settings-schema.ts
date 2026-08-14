/**
 * Settings and persistence shapes for the skills manager, plus pure
 * normalization/validation.
 *
 * The host plugin registers ONE settings namespace (`skills-manager`) whose
 * section holds every scope's overrides, so the browser can read/write all
 * three scopes through the existing settings transport (no custom RPC):
 *
 *   skills-manager:
 *     global:     { <skill>: true|false }          # global overrides
 *     workspaces: { <path>: { <skill>: bool } }    # per-workspace overrides
 *     sessions:   { <id>:   { <skill>: bool } }    # per-session overrides
 *
 * This module defines the plain shapes and their validation so the host
 * wiring, the client decoder, and the unit tests share one source of truth.
 */

import { isSkillName } from './skill-filter.ts'
import type { ScopeKind, SkillStateStoreData } from './scope.ts'

/** Namespace id registered with `ctx.settings` / bound on the client. */
export const SETTINGS_NAMESPACE = 'skills-manager'

/** One scope's override map: skill name -> enabled. */
export type SkillOverrides = Record<string, boolean>

/**
 * The `skills-manager` settings section. Every key is optional; an omitted
 * scope is treated as empty (no overrides).
 */
export interface SkillsManagerSection {
  readonly global?: SkillOverrides
  readonly workspaces?: Record<string, SkillOverrides>
  readonly sessions?: Record<string, SkillOverrides>
}

/**
 * Validate a raw settings section into a clean `SkillsManagerSection`.
 * Invalid skill names and non-boolean values are dropped (fail-safe: an
 * unparseable entry is ignored rather than silently enabling a skill).
 */
export function normalizeSection(raw: unknown): SkillsManagerSection {
  const obj = raw !== null && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
  return {
    global: normalizeOverrides(obj.global),
    workspaces: normalizeScopedOverrides(obj.workspaces),
    sessions: normalizeScopedOverrides(obj.sessions),
  }
}

function normalizeOverrides(raw: unknown): SkillOverrides {
  const out: SkillOverrides = {}
  if (raw === null || typeof raw !== 'object') return out
  for (const [name, value] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof value === 'boolean' && isSkillName(name)) out[name] = value
  }
  return out
}

function normalizeScopedOverrides(raw: unknown): Record<string, SkillOverrides> {
  const out: Record<string, SkillOverrides> = {}
  if (raw === null || typeof raw !== 'object') return out
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    const normalized = normalizeOverrides(value)
    if (Object.keys(normalized).length > 0) out[key] = normalized
  }
  return out
}

/** Convert a settings section into the immutable store data maps. */
export function toStoreData(section: SkillsManagerSection): SkillStateStoreData {
  return {
    global: toMap(section.global ?? {}),
    workspaces: toMapOfMaps(section.workspaces ?? {}),
    sessions: toMapOfMaps(section.sessions ?? {}),
  }
}

/** Convert immutable store data back into the settings section shape. */
export function fromStoreData(data: SkillStateStoreData): SkillsManagerSection {
  return {
    global: fromMap(data.global),
    workspaces: fromMapOfMaps(data.workspaces),
    sessions: fromMapOfMaps(data.sessions),
  }
}

function toMap(record: SkillOverrides): ReadonlyMap<string, boolean> {
  return new Map(Object.entries(record))
}

function toMapOfMaps(record: Record<string, SkillOverrides>): ReadonlyMap<string, ReadonlyMap<string, boolean>> {
  const out = new Map<string, ReadonlyMap<string, boolean>>()
  for (const [key, inner] of Object.entries(record)) out.set(key, toMap(inner))
  return out
}

function fromMap(map: ReadonlyMap<string, boolean>): SkillOverrides {
  return Object.fromEntries(map)
}

function fromMapOfMaps(map: ReadonlyMap<string, ReadonlyMap<string, boolean>>): Record<string, SkillOverrides> {
  const out: Record<string, SkillOverrides> = {}
  for (const [key, inner] of map) out[key] = fromMap(inner)
  return out
}

/** The three settings-section fields, mirroring the scope kinds. */
export type SectionField = 'global' | 'workspaces' | 'sessions'

/** Map a scope kind to the settings field that carries its overrides. */
export function overrideFieldFor(scopeKind: ScopeKind): SectionField {
  return scopeKind === 'global' ? 'global' : scopeKind === 'workspace' ? 'workspaces' : 'sessions'
}

/**
 * Compute the settings field + value that records one override toggle for a
 * scope. Used by the client to write a single field through the settings scope
 * (`set(field, value)`). Pure so it can be unit-tested (this guards the
 * workspace-vs-sessions field mapping that a strict typecheck catches).
 */
export function setOverrideInSection(
  section: SkillsManagerSection,
  scopeKind: ScopeKind,
  scopeKey: string | undefined,
  name: string,
  enabled: boolean,
): { field: SectionField; value: unknown } {
  return setOverridesInSection(section, scopeKind, scopeKey, [name], enabled)
}

/**
 * Batch form of {@link setOverrideInSection}: record several overrides for the
 * same scope in ONE field value. The client uses this for multi-select
 * enable/disable so every selected name lands in a single `set(field, value)`
 * (writing per-name against the same stale section would drop all but the last).
 */
export function setOverridesInSection(
  section: SkillsManagerSection,
  scopeKind: ScopeKind,
  scopeKey: string | undefined,
  names: readonly string[],
  enabled: boolean,
): { field: SectionField; value: unknown } {
  const field = overrideFieldFor(scopeKind)
  if (scopeKind === 'global') {
    const global = { ...(section.global ?? {}) }
    for (const name of names) global[name] = enabled
    return { field, value: global }
  }
  // scopeKind is 'workspace' | 'session' here, so the field is a map of
  // scope-key -> overrides (narrowed explicitly so spreading type-checks).
  const map = (scopeKind === 'workspace' ? section.workspaces : section.sessions) ?? {}
  const inner = { ...(map[scopeKey ?? ''] ?? {}) }
  for (const name of names) inner[name] = enabled
  return { field, value: { ...map, [scopeKey ?? '']: inner } }
}

/**
 * Compute the settings field + value that clears ONE scope instance's overrides.
 * Global clears the whole field; workspace/session remove only that key's entry
 * (so resetting one session does not wipe every other session's overrides).
 */
export function resetScopeInSection(
  section: SkillsManagerSection,
  scopeKind: ScopeKind,
  scopeKey: string | undefined,
): { field: SectionField; value: unknown } {
  const field = overrideFieldFor(scopeKind)
  if (scopeKind === 'global') {
    return { field, value: {} }
  }
  const map = (scopeKind === 'workspace' ? section.workspaces : section.sessions) ?? {}
  const next = { ...map }
  delete next[scopeKey ?? '']
  return { field, value: next }
}
