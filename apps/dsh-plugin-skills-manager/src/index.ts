/**
 * Host plugin for the skills manager.
 *
 * Provides `ctx.skillManager` — the scoped enable/disable registry with the
 * session > workspace > global override relationship — and registers:
 *
 *   1. a `skills-manager` settings namespace holding ALL scopes' overrides
 *      (global / workspaces / sessions), so the browser reads and writes them
 *      through the existing settings transport;
 *   2. a skill provider that shadows disabled skills so they disappear from
 *      model-facing catalogs and human-facing invocations.
 */

import { Service, type Context } from '@deepseek-ai/cordis'
import Schema from '@deepseek-ai/schemastery'
import { settingsNamespace } from '@deepseek-ai/dsh-settings'
import type { SkillCandidate, SkillDefinition, SkillProvider, SkillProviderControl } from '@deepseek-ai/dsh-skill'

import {
  disabledSkillNames,
  explicitOverrides,
  resolveSkillState,
  withOverride,
  withoutOverride,
  type ResolvedSkillState,
  type ScopeId,
  type ScopeView,
  type SkillStateStoreData,
} from './core/scope.ts'
import { isManagedSource } from './core/skill-filter.ts'
import {
  fromStoreData,
  normalizeSection,
  SETTINGS_NAMESPACE,
  toStoreData,
} from './core/settings-schema.ts'

/** Rank used by enforcement block candidates. Must beat the filesystem
 * provider's project/user ranks (100-500) so a block wins within one layer. */
export const ENFORCE_RANK = 50

/** Provider name registered on `ctx.skills` for enforcement blocks. */
export const ENFORCE_PROVIDER = 'skills-manager'

export interface Config {
  /** Provider name used for enforcement blocks on `ctx.skills`. */
  providerName?: string
  /** Rank for enforcement blocks (default ENFORCE_RANK). */
  enforceRank?: number
}

/** A resolved skill row as consumed by the client UI. */
export interface ResolvedSkillRow {
  readonly name: string
  readonly source: string
  readonly description: string
  readonly managed: boolean
  readonly state: ResolvedSkillState
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    skillManager: SkillManagerService
  }
}

export class SkillManagerService extends Service {
  static inject = ['skills', 'settings']

  private readonly providerName: string
  private readonly enforceRank: number

  private store: SkillStateStoreData = toStoreData({})
  private readonly listeners = new Set<() => void>()
  /** Registration-scoped invalidation control from the skill registry (bumps the catalog revision). */
  private providerControl?: SkillProviderControl
  private settingsScope?: {
    get(): unknown
    watch(cb: (next: unknown, prev: unknown) => void | Promise<void>): () => void
    replace(section: object): Promise<void>
  }

  constructor(ctx: Context, config: Config = {}) {
    super(ctx, 'skillManager')
    this.providerName = config.providerName ?? ENFORCE_PROVIDER
    this.enforceRank = config.enforceRank ?? ENFORCE_RANK
  }

  async *[Service.init]() {
    const schema = Schema.object({
      global: Schema.dict(Schema.boolean()),
      workspaces: Schema.dict(Schema.dict(Schema.boolean())),
      sessions: Schema.dict(Schema.dict(Schema.boolean())),
    })
    this.settingsScope = this.ctx.settings.register(settingsNamespace(SETTINGS_NAMESPACE), schema, {
      applies: 'live',
    })

    this.syncFromSettings()
    const unwatch = this.settingsScope.watch(() => {
      this.syncFromSettings()
      this.emit()
    })
    yield unwatch

    const provider: SkillProvider = {
      name: this.providerName,
      // The registry forwards the viewing scope to providers at runtime (the
      // `scope` field on the borrowed options object) even though the public
      // `SkillLookupOptions` type only names `cwd`/`signal`. For an agent the
      // scope key IS the Agent, so `.id` is the session id — this is what makes
      // session-scoped enforcement possible without a separate RPC.
      list: async (options) => this.listBlocks(options.cwd, sessionIdOf(options)),
      get: async (candidate) => this.blockDefinition(candidate),
    }
    const unregister = this.ctx.skills.registerProvider((control) => {
      this.providerControl = control
      return provider
    })
    yield unregister
  }

  private syncFromSettings() {
    this.store = toStoreData(normalizeSection(this.settingsScope?.get()))
  }

  private listBlocks(cwd?: string, sessionId?: string) {
    return this.disabledNamesFor(cwd, sessionId).map((name) => ({
      name,
      description: 'Disabled by skills-manager',
      whenToUse: undefined,
      invocation: { modelInvocable: false, userInvocable: false },
      source: 'custom',
      provider: this.providerName,
      rank: this.enforceRank,
      locator: name,
    }))
  }

  private blockDefinition(candidate: SkillCandidate): SkillDefinition {
    return {
      name: candidate.name,
      description: 'Disabled by skills-manager',
      invocation: { modelInvocable: false, userInvocable: false },
      source: 'custom',
      provider: this.providerName,
      content: '',
    }
  }

  /**
   * Every skill name currently disabled for the given view (session + workspace
   * + global). Delegates to the pure `disabledSkillNames` so the enforcement
   * predicate is unit-tested in isolation.
   */
  private disabledNamesFor(cwd?: string, sessionId?: string): string[] {
    return disabledSkillNames(this.store, { workspacePath: cwd, sessionId })
  }

  // ---- public API --------------------------------------------------------

  /**
   * List the discovered skills that this manager recognises (`.agents` + dsh
   * roots only), each with its resolved enable/disable state for `view`.
   */
  async list(view: ScopeView = {}): Promise<ResolvedSkillRow[]> {
    const summaries = await this.ctx.skills.list({ cwd: view.workspacePath, scope: undefined })
    const rows: ResolvedSkillRow[] = []
    for (const summary of summaries) {
      rows.push({
        name: summary.name,
        source: summary.source,
        description: summary.description ?? '',
        managed: isManagedSource(summary.source),
        state: resolveSkillState(this.store, summary.name, view),
      })
    }
    rows.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0))
    return rows
  }

  /** Resolve one skill's effective state for a view. */
  resolve(name: string, view: ScopeView = {}): ResolvedSkillState {
    return resolveSkillState(this.store, name, view)
  }

  /** Set (or clear, when `enabled` is undefined) one override in one scope. */
  async setState(scope: ScopeId, name: string, enabled: boolean | undefined): Promise<void> {
    this.store = enabled === undefined
      ? withoutOverride(this.store, scope, name)
      : withOverride(this.store, scope, name, enabled)
    await this.persistAll()
    this.emit()
  }

  /** Clear every override in one scope. */
  async reset(scope: ScopeId): Promise<void> {
    const overrides = explicitOverrides(this.store, scope)
    for (const name of overrides.keys()) {
      this.store = withoutOverride(this.store, scope, name)
    }
    await this.persistAll()
    this.emit()
  }

  /** Snapshot of the full store (for tests and diagnostics). */
  getStoreData(): SkillStateStoreData {
    return this.store
  }

  /** Subscribe to store changes; returns a disposer. */
  subscribe(listener: () => void): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  private async persistAll() {
    await this.settingsScope?.replace(fromStoreData(this.store))
  }

  private emit() {
    // Invalidate the skill registry's completed catalogs so an override takes
    // effect on the next agent step: the registry caches by (cwd, scope chain,
    // revision) and only an invalidation bumps that revision, so without this a
    // toggle would stay stale until an unrelated change.
    this.providerControl?.invalidate()
    for (const listener of [...this.listeners]) {
      try {
        listener()
      } catch (error) {
        this.ctx.logger.warn('skills-manager: listener failed', error)
      }
    }
  }
}

/**
 * Read the viewing session id out of a provider lookup's borrowed options.
 * The registry forwards `scope` to providers at runtime; for an agent the scope
 * key is the Agent itself, whose `id` is the SessionId. Non-agent views (no
 * scope, or a scope without an id) resolve to undefined → workspace/global only.
 */
function sessionIdOf(options: unknown): string | undefined {
  const scope = (options as { scope?: unknown }).scope as { id?: unknown } | undefined
  return typeof scope?.id === 'string' ? scope.id : undefined
}

export default SkillManagerService
