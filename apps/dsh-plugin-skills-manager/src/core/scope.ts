/**
 * Scoped skill-state override model.
 *
 * Skills can be enabled/disabled in three scopes with an override relationship:
 *
 *     session  >  workspace  >  global  >  default (enabled)
 *
 * Each scope holds an *override map*: skill name -> explicit boolean. A name
 * absent from a scope's map means "inherit from the next-lower scope". This
 * module owns the pure resolution and is deliberately free of any Cordis / dsh
 * dependency so it can be unit-tested in isolation.
 */

/** The three override scopes, nearest-first. */
export type ScopeKind = 'session' | 'workspace' | 'global'

/** Stable identity for a concrete scope instance. */
export interface ScopeId {
  readonly kind: ScopeKind
  readonly key?: string
}

/** Explicit per-scope overrides: skill name -> enabled. */
export type ScopeOverrides = ReadonlyMap<string, boolean>

/** The complete persisted store across all scope instances. */
export interface SkillStateStoreData {
  readonly global: ScopeOverrides
  readonly workspaces: ReadonlyMap<string, ScopeOverrides>
  readonly sessions: ReadonlyMap<string, ScopeOverrides>
}

/** A view selector: which workspace/session a resolution should consider. */
export interface ScopeView {
  readonly workspacePath?: string
  readonly sessionId?: string
}

export type SkillDecision = 'enabled' | 'disabled'

/** Where a decision came from - used by the UI for inherit/override hints. */
export type DecisionOrigin = ScopeKind | 'default'

export interface ResolvedSkillState {
  readonly enabled: boolean
  readonly origin: DecisionOrigin
}

export const EMPTY_STORE: SkillStateStoreData = {
  global: new Map(),
  workspaces: new Map(),
  sessions: new Map(),
}

const EMPTY_OVERRIDES: ScopeOverrides = new Map()

/**
 * The scope chain for a view, nearest-first. `global` is always the last link;
 * workspace/session links are only present when the view names them.
 */
export function scopeChain(view: ScopeView): readonly ScopeId[] {
  const chain: ScopeId[] = []
  if (view.sessionId !== undefined) chain.push({ kind: 'session', key: view.sessionId })
  if (view.workspacePath !== undefined) chain.push({ kind: 'workspace', key: view.workspacePath })
  chain.push({ kind: 'global' })
  return chain
}

/** Read the override map for a concrete scope instance (empty when absent). */
export function overridesFor(data: SkillStateStoreData, scope: ScopeId): ScopeOverrides {
  if (scope.kind === 'global') return data.global
  if (scope.kind === 'workspace') return scope.key !== undefined ? (data.workspaces.get(scope.key) ?? EMPTY_OVERRIDES) : EMPTY_OVERRIDES
  if (scope.kind === 'session') return scope.key !== undefined ? (data.sessions.get(scope.key) ?? EMPTY_OVERRIDES) : EMPTY_OVERRIDES
  return EMPTY_OVERRIDES
}

/**
 * Resolve one skill's effective state for a view, following the override chain.
 * Returns the decision plus the origin that supplied it.
 */
export function resolveSkillState(
  data: SkillStateStoreData,
  skillName: string,
  view: ScopeView = {},
): ResolvedSkillState {
  for (const scope of scopeChain(view)) {
    const override = overridesFor(data, scope).get(skillName)
    if (override !== undefined) {
      return { enabled: override, origin: scope.kind }
    }
  }
  return { enabled: true, origin: 'default' }
}

/** Resolve every skill name in `names` for a view, preserving input order. */
export function resolveSkills(
  data: SkillStateStoreData,
  names: readonly string[],
  view: ScopeView = {},
): ReadonlyMap<string, ResolvedSkillState> {
  const out = new Map<string, ResolvedSkillState>()
  for (const name of names) out.set(name, resolveSkillState(data, name, view))
  return out
}

/**
 * The set of names that resolve to `enabled` for a view. This is the filter a
 * model-facing catalog applies: disabled skills drop out entirely.
 */
export function enabledSkillNames(
  data: SkillStateStoreData,
  names: readonly string[],
  view: ScopeView = {},
): string[] {
  const out: string[] = []
  for (const name of names) {
    if (resolveSkillState(data, name, view).enabled) out.push(name)
  }
  return out
}

/** Immutable set/clear helpers used by tests and the host plugin. */
export function withOverride(
  data: SkillStateStoreData,
  scope: ScopeId,
  skillName: string,
  enabled: boolean,
): SkillStateStoreData {
  return applyOverride(data, scope, skillName, enabled)
}

export function withoutOverride(
  data: SkillStateStoreData,
  scope: ScopeId,
  skillName: string,
): SkillStateStoreData {
  return applyOverride(data, scope, skillName, undefined)
}

function applyOverride(
  data: SkillStateStoreData,
  scope: ScopeId,
  skillName: string,
  enabled: boolean | undefined,
): SkillStateStoreData {
  const current = overridesFor(data, scope)
  const next = new Map(current)
  if (enabled === undefined) next.delete(skillName)
  else next.set(skillName, enabled)

  if (scope.kind === 'global') return { ...data, global: next }
  if (scope.kind === 'workspace') {
    return { ...data, workspaces: withMapEntry(data.workspaces, scope.key as string, next) }
  }
  if (scope.kind === 'session') {
    return { ...data, sessions: withMapEntry(data.sessions, scope.key as string, next) }
  }
  return data
}

function withMapEntry<K, V>(map: ReadonlyMap<K, V>, key: K, value: V): ReadonlyMap<K, V> {
  const next = new Map(map)
  next.set(key, value)
  return next
}

/** Every name carrying an override anywhere in the store, sorted. */
export function allOverrideNames(data: SkillStateStoreData): string[] {
  const names = new Set<string>()
  for (const name of data.global.keys()) names.add(name)
  for (const overrides of data.workspaces.values()) for (const name of overrides.keys()) names.add(name)
  for (const overrides of data.sessions.values()) for (const name of overrides.keys()) names.add(name)
  return [...names].sort()
}

/**
 * Names that resolve to `disabled` for a view. This is the enforcement
 * predicate a block provider uses: every name in the store that the view's
 * chain resolves to false.
 */
export function disabledSkillNames(data: SkillStateStoreData, view: ScopeView = {}): string[] {
  return allOverrideNames(data).filter((name) => !resolveSkillState(data, name, view).enabled)
}

/**
 * Explicit override names for one scope instance, sorted - the editable list a
 * settings surface shows as "this scope's own decisions".
 */
export function explicitOverrides(
  data: SkillStateStoreData,
  scope: ScopeId,
): ReadonlyMap<string, boolean> {
  return new Map([...overridesFor(data, scope)].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)))
}
