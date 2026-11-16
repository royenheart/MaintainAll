/**
 * Replay-side Agent creation and handle retention. The host service wires the
 * plugin lifecycle; this class owns the dsh Agent/Preset faces and the bounded
 * map of live handles.
 */

import type { Context } from '@deepseek-ai/cordis'
import type { SeedEvent } from '../core/contract.ts'
import type { ReplayAgentFace, ReplaySourceAgentFace } from '../dispatch/replay.ts'

const MAX_RETAINED_AGENT_HANDLES = 256

interface ReplayLogger {
  warn(message: string, ...args: unknown[]): void
}

export interface CreateReplayAgentOptions {
  sessionId: string
  seed?: SeedEvent[]
  meta?: { cwd?: string; agentPreset?: string }
  /** Replay uses ops by default; an edit session uses the deployment default. */
  defaultPreset?: 'ops' | 'deployment'
}

export class ReplayRuntime {
  private readonly agentHandles = new Map<string, unknown>()
  private stopping = false
  private readonly ctx: Context
  private readonly logger: ReplayLogger

  constructor(ctx: Context, logger: ReplayLogger) {
    this.ctx = ctx
    this.logger = logger
  }

  stop(): void {
    this.stopping = true
    this.agentHandles.clear()
  }

  forget(sessionId: string): void {
    this.agentHandles.delete(sessionId)
  }

  remember(sessionId: string, handle: unknown): void {
    if (this.stopping) return
    this.agentHandles.delete(sessionId)
    this.agentHandles.set(sessionId, handle)
    while (this.agentHandles.size > MAX_RETAINED_AGENT_HANDLES) {
      const oldest = this.agentHandles.keys().next().value
      if (oldest === undefined) break
      this.agentHandles.delete(oldest)
    }
  }

  /**
   * Resolve the Agent for a continuation task's source Session.
   *
   * A live Agent is reused. Otherwise the source Session is activated through
   * dsh's `schedule/resolve-agent` waterfall — the same extension point native
   * dsh reminders use for Session activation. The Web profile supplies a
   * `sessionController` fallback; an SDK composition may register its own
   * handler. Activation providers own the resumed Agent's lifecycle, so
   * unloading this plugin cannot cancel the user's source Agent. A deployment
   * without any activation provider fails closed. An archived or
   * subagent-owned source Session also fails closed, and the task never
   * mutates the Session's preset, title, working directory, or permissions.
   */
  async resolveSourceSession(sessionId: string): Promise<ReplaySourceAgentFace> {
    const agents = this.ctx.get('agents') as unknown as {
      get?(id: string): ReplayAgentFace | undefined
    } | undefined
    if (agents === undefined) throw new Error('agents service unavailable')
    const archived = (this.ctx.get('workspaceRegistry') as unknown as {
      archivedSessionIds?: readonly string[]
    } | undefined)?.archivedSessionIds
    if (archived?.includes(sessionId) === true) {
      throw new Error(`source session "${sessionId}" is archived; restore it before the task can continue it`)
    }
    const live = agents.get?.(sessionId)
    if (live !== undefined) {
      assertOrdinarySourceAgent(sessionId, live)
      return { agent: live }
    }

    const waterfall = (this.ctx as unknown as {
      waterfall?: (name: string, ...args: unknown[]) => Promise<unknown>
    }).waterfall
    if (typeof waterfall !== 'function') {
      throw new Error('source Session activation is unavailable: no agent activation waterfall')
    }
    const fallback = async (): Promise<ReplayAgentFace> => {
      const controller = this.ctx.get('sessionController') as unknown as {
        resolveAgent?(id: string): Promise<
          { agent?: ReplayAgentFace } | { error?: { message?: string } }
        >
      } | undefined
      if (typeof controller?.resolveAgent === 'function') {
        const resolved = await controller.resolveAgent(sessionId)
        if (resolved !== undefined && typeof resolved === 'object' && 'agent' in resolved
          && resolved.agent !== undefined) {
          assertOrdinarySourceAgent(sessionId, resolved.agent)
          return resolved.agent
        }
        const message = resolved !== undefined && typeof resolved === 'object' && 'error' in resolved
          ? resolved.error?.message
          : undefined
        throw new Error(message ?? `cannot activate source session "${sessionId}"`)
      }
      throw new Error(`no Session activation provider can resume source session "${sessionId}"`)
    }
    let activated: unknown
    try {
      activated = await waterfall.call(this.ctx, 'schedule/resolve-agent', sessionId, fallback)
    } catch (error) {
      throw new Error(
        `cannot activate source session "${sessionId}": `
        + `${error instanceof Error ? error.message : String(error)}`,
      )
    }
    const agent = activated as ReplayAgentFace | undefined
    if (agent === undefined || typeof agent !== 'object' || typeof agent.followup !== 'function') {
      throw new Error(`source session "${sessionId}" activation returned no Agent`)
    }
    assertOrdinarySourceAgent(sessionId, agent)
    return { agent }
  }

  async createAgent(
    options: CreateReplayAgentOptions,
  ): Promise<{ agent: ReplayAgentFace; dispose?: () => void | Promise<void> }> {
    const agents = this.ctx.get('agents') as unknown as {
      create(input: unknown): Promise<{ agent: ReplayAgentFace; dispose?: () => void | Promise<void> }>
    }
    const presets = this.ctx.get('agentPresets') as unknown as {
      resolve(id?: string): Promise<{ id: string; broken?: string }>
      mount(agentCtx: unknown, id: string): Promise<unknown>
      presetForSession?(session: unknown): string | undefined
    } | undefined
    const defaultModel = this.ctx.get('agentDefaultModel') as unknown as {
      currentSelection(): { provider: string; model: string }
    } | undefined
    const explicitPreset = options.meta?.agentPreset
    const presetId = explicitPreset ?? (options.defaultPreset === 'deployment' ? undefined : 'ops')
    let resolved: string | undefined
    if (presets !== undefined) {
      try {
        const preset = await presets.resolve(presetId)
        if (preset.broken !== undefined) {
          throw new Error(`agent preset '${presetId}' failed to activate: ${preset.broken}`)
        }
        resolved = preset.id
      } catch (error) {
        if (explicitPreset !== undefined) throw error
        const message = error instanceof Error ? error.message : String(error)
        this.logger.warn('maintainall: preset unavailable, using deployment default: %s', message)
        resolved = (await presets.resolve(undefined)).id
      }
    } else {
      resolved = presetId
    }
    const setup = async (agentCtx: unknown): Promise<void> => {
      if (presets !== undefined && resolved !== undefined) await presets.mount(agentCtx, resolved)
    }
    const agentOptions = defaultModel?.currentSelection() ?? {}
    const created = await agents.create({
      sessionId: options.sessionId,
      ...(options.seed === undefined ? {} : { seed: options.seed }),
      meta: {
        ...(options.meta?.cwd === undefined ? {} : { cwd: options.meta.cwd }),
        ...(resolved === undefined ? {} : { agentPreset: resolved }),
      },
      agentOptions,
      setup,
    })
    const dispose = created.dispose ?? created.agent.dispose?.bind(created.agent)
    return {
      agent: created.agent,
      ...(dispose === undefined ? {} : { dispose }),
    }
  }
}

/** Reject a source Agent that belongs to dsh's subagent routing. */
function assertOrdinarySourceAgent(sessionId: string, agent: ReplayAgentFace): void {
  const header = agent.session?.header
  if (header?.origin === 'subagent' || (header?.delegationDepth ?? 0) > 0) {
    throw new Error(`source session "${sessionId}" belongs to subagent routing and cannot receive a continuation run`)
  }
}
