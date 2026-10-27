/**
 * Session replay dispatch.
 *
 * Creates the new agent+session pair for an already-fired deterministic
 * trigger: materializes a run cwd, rewrites the task seed, creates the agent
 * through the injected `agents` face, injects the trigger context as the first
 * user message, and persists run-map and registry state. No dsh imports; the
 * host service supplies the faces.
 */

import { randomUUID } from 'node:crypto'
import { rm } from 'node:fs/promises'
import { basename, join } from 'node:path'
import type { SeedEvent, TriggerEvent } from '../core/contract.ts'
import {
  loadRegistryState,
  loadRunMapState,
  pluginDataRoot,
  saveRegistryState,
  saveRunMapState,
} from '../core/storage.ts'
import { createRunCwd } from './run-cwd.ts'
import { loadTask } from './load-task.ts'
import { buildSeedForRun, firstUserMessage } from './session.ts'

/** Minimal face of one dsh agent consumed by dispatch. */
export interface ReplayAgentFace {
  followup(message: unknown): void
  /** Present on a real dsh agent; dispatch applies the session title to it. */
  session?: unknown
  /** Present on a real dsh agent; dispatch does not call it directly. */
  dispose?: () => void | Promise<void>
}

/** One created agent plus the host-owned handle disposer. */
export interface ReplayHandle {
  agent: ReplayAgentFace
  /** Undo an unpublished session when a post-create step fails. */
  dispose?: () => void | Promise<void>
}

/** Minimal face of the dsh agent registry consumed by dispatch. */
export interface ReplayAgentsFace {
  create(options: {
    sessionId: string
    seed?: SeedEvent[]
    meta?: { cwd?: string; agentPreset?: string }
  }): Promise<ReplayHandle>
}

/** Minimal face of dsh's permission-preset service. */
export interface PermissionPresetsFace {
  resolve(name: string): unknown
  set(session: unknown, name: string): void
}

/** Minimal face of dsh's session-title service. */
export interface SessionTitleFace {
  rename(session: unknown, title: string): unknown
}

/** Machine-readable failure reason for the replay flow. */
export type DispatchFailureReason =
  | 'unknown_task'
  | 'agents_unavailable'
  | 'permission_unavailable'
  | 'permission_unknown'
  | 'asset_unreadable'
  | 'run_cwd_failed'
  | 'seed_build_failed'
  | 'agent_create_failed'
  | 'task_deleted'
  | 'publish_failed'

/** Result shape returned by `dispatchReplay`. */
export interface DispatchResult {
  ok: boolean
  reason?: DispatchFailureReason
  warning?: 'bookkeeping_incomplete'
  error?: string
  sessionId?: string
}

/** Keep a session title within dsh's 120-byte title cap without splitting a code point. */
function truncateTitle(value: string): string {
  const title = value.trim() === '' ? 'MaintainAll run' : value.trim()
  if (Buffer.byteLength(title, 'utf8') <= 120) return title
  let out = ''
  for (const character of title) {
    if (Buffer.byteLength(out + character, 'utf8') > 120) break
    out += character
  }
  return out === '' ? 'MaintainAll run' : out
}

/** User-visible title for one replayed session. */
export function replaySessionTitle(taskName: string, event: TriggerEvent): string {
  return truncateTitle(`${taskName} · ${event.source}`)
}

/** Read an optional host service through Cordis `get()` or a plain face object. */
function optionalService<T>(ctx: unknown, name: string): T | undefined {
  if (typeof ctx !== 'object' || ctx === null) return undefined
  const candidate = ctx as { get?: (key: string) => unknown; [key: string]: unknown }
  if (typeof candidate.get === 'function') {
    try {
      return candidate.get(name) as T | undefined
    } catch {
      return undefined
    }
  }
  return candidate[name] as T | undefined
}

/**
 * Create the replay agent+session for a fired trigger.
 *
 * The trigger decision is deterministic and already happened; this function
 * only materializes the run cwd, rewrites the task seed, creates the agent and
 * session, applies the task's permission preset and a readable title, and
 * injects the trigger context as the first real user message. A failure after
 * creation disposes the unpublished handle so a half-configured session does
 * not linger.
 */
export async function dispatchReplay(
  ctx: unknown,
  taskId: string,
  event: TriggerEvent,
  opts: {
    root?: string
    keepAlive?: (sessionId: string, handle: unknown) => void
    createAgent?: (options: { sessionId: string; seed?: SeedEvent[]; meta?: { cwd?: string; agentPreset?: string } }) => Promise<ReplayHandle>
    permissionPresets?: PermissionPresetsFace
    sessionTitle?: SessionTitleFace
  } = {},
): Promise<DispatchResult> {
  const root = opts.root ?? pluginDataRoot()
  const registry = loadRegistryState(root)
  const record = registry.tasks[taskId]
  if (record === undefined) return { ok: false, reason: 'unknown_task', error: `unknown task: ${taskId}` }
  let task: Awaited<ReturnType<typeof loadTask>>
  try {
    task = loadTask(root, taskId)
  } catch (error) {
    return { ok: false, reason: 'asset_unreadable', error: error instanceof Error ? error.message : String(error) }
  }
  const agents = optionalService<ReplayAgentsFace>(ctx, 'agents')
  if (agents === undefined && opts.createAgent === undefined) {
    return { ok: false, reason: 'agents_unavailable', error: 'agents service unavailable' }
  }
  const permissionPresets = opts.permissionPresets
    ?? optionalService<PermissionPresetsFace>(ctx, 'permissionPresets')
  const sessionTitle = opts.sessionTitle
    ?? optionalService<SessionTitleFace>(ctx, 'sessionTitle')
  const presetHint = task.manifest.bindings?.permissionPreset?.hint
  if (presetHint !== undefined && permissionPresets === undefined) {
    return { ok: false, reason: 'permission_unavailable', error: `permission preset service unavailable for '${presetHint}'` }
  }
  if (presetHint !== undefined && permissionPresets !== undefined) {
    try {
      permissionPresets.resolve(presetHint)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      return { ok: false, reason: 'permission_unknown', error: `unknown permission preset '${presetHint}': ${message}` }
    }
  }

  // Materialize the run directory only after fail-closed preflight, and remove
  // it if a later step fails before the run is recorded.
  let runCwd: string
  try {
    runCwd = await createRunCwd(root, taskId)
  } catch (error) {
    return { ok: false, reason: 'run_cwd_failed', error: error instanceof Error ? error.message : String(error) }
  }
  const cleanupRunCwd = async (): Promise<void> => {
    try {
      await rm(runCwd, { recursive: true, force: true })
      // A delete/dispatch race can recreate the parent `runs/` skeleton after
      // the task directory was removed; remove it while it is still empty.
      await rm(join(root, 'ops', taskId, 'runs'), { recursive: false })
    } catch {
      // Best effort; a failed run generally leaves its directory for inspection.
    }
  }
  const availableTools = task.manifest.requires?.tools
  let seed: SeedEvent[] | undefined
  try {
    seed = task.seed === undefined
      ? undefined
      : buildSeedForRun({ seed: task.seed, manifest: task.manifest }, { runCwd, ...(availableTools === undefined ? {} : { availableTools }) })
  } catch (error) {
    await cleanupRunCwd()
    return { ok: false, reason: 'seed_build_failed', error: error instanceof Error ? error.message : String(error) }
  }
  const sessionId = `session-${randomUUID()}`
  const create = opts.createAgent ?? agents!.create.bind(agents!)
  const meta = { cwd: runCwd, ...(task.manifest.bindings?.agentPreset?.hint !== undefined
    ? { agentPreset: task.manifest.bindings.agentPreset.hint }
    : {}) }
  let handle: ReplayHandle
  try {
    handle = await create({
      sessionId,
      ...(seed === undefined ? {} : { seed }),
      meta,
    })
  } catch (error) {
    await cleanupRunCwd()
    return { ok: false, reason: 'agent_create_failed', error: error instanceof Error ? error.message : String(error) }
  }
  if (loadRegistryState(root).tasks[taskId] === undefined) {
    try {
      await handle.dispose?.()
    } catch {
      // Rollback is best effort; report the deletion below.
    }
    await cleanupRunCwd()
    return { ok: false, reason: 'task_deleted', error: `task deleted during replay: ${taskId}` }
  }
  try {
    if (presetHint !== undefined && permissionPresets !== undefined) {
      if (handle.agent.session === undefined) {
        throw new Error(`cannot apply permission preset '${presetHint}': created Agent has no Session`)
      }
      permissionPresets.set(handle.agent.session, presetHint)
    }
    if (sessionTitle !== undefined && handle.agent.session !== undefined) {
      try {
        sessionTitle.rename(handle.agent.session, replaySessionTitle(record.name, event))
      } catch {
        // A title is presentation; a rename failure must not lose the run.
      }
    }
    const message = firstUserMessage(event, record.name, runCwd)
    handle.agent.followup({
      id: randomUUID(),
      role: 'user',
      content: [{ type: 'text', text: message.content }],
      source: { kind: 'plugin:maintainall' },
    })
  } catch (error) {
    try {
      await handle.dispose?.()
    } catch {
      // Rollback is best effort; report the original failure.
    }
    await cleanupRunCwd()
    return { ok: false, reason: 'publish_failed', error: error instanceof Error ? error.message : String(error) }
  }
  try {
    opts.keepAlive?.(sessionId, handle)
    const runMap = loadRunMapState(root)
    const runId = basename(runCwd)
    runMap.runs[runId] = { taskId, sessionId, cwd: runCwd, createdAt: new Date().toISOString() }
    saveRunMapState(root, runMap)
    // Reload immediately before the write so a concurrent save/import/delete is
    // not overwritten by the snapshot read before Agent creation.
    const latestRegistry = loadRegistryState(root)
    const currentRecord = latestRegistry.tasks[taskId]
    if (currentRecord !== undefined) {
      currentRecord.lastRunAt = new Date().toISOString()
      saveRegistryState(root, latestRegistry)
    }
  } catch {
    // The trigger message is already published; bookkeeping failure must not
    // dispose the live run or delete its workspace.
    return { ok: true, sessionId, warning: 'bookkeeping_incomplete' }
  }
  return { ok: true, sessionId }
}
