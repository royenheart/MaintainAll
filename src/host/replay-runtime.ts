/**
 * Replay-side Agent creation and handle retention. The host service wires the
 * plugin lifecycle; this class owns the dsh Agent/Preset faces and the bounded
 * map of live handles.
 */

import type { Context } from '@deepseek-ai/cordis'
import type { SeedEvent } from '../core/contract.ts'
import type { ReplayAgentFace } from '../dispatch/replay.ts'

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

  constructor(
    private readonly ctx: Context,
    private readonly logger: ReplayLogger,
  ) {}

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

  async createAgent(
    options: CreateReplayAgentOptions,
  ): Promise<{ agent: ReplayAgentFace; dispose?: () => void | Promise<void> }> {
    const agents = this.ctx.get('agents') as unknown as {
      create(input: unknown): Promise<{ agent: ReplayAgentFace; dispose?: () => void | Promise<void> }>
    }
    const presets = this.ctx.get('agentPresets') as unknown as {
      resolve(id?: string): Promise<{ id: string; broken?: string }>
      mount(agentCtx: unknown, id: string): Promise<unknown>
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
