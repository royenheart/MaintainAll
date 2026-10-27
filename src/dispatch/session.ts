/**
 * Session seed assembly for a replayed run.
 *
 * Bridges the pure seed core (`src/core/seed.ts`) and the host dispatch path:
 * given a task asset (seed + manifest) and a materialized run cwd, produce
 * the durable event list and the first user message a new session is created
 * with. No dsh imports; session creation itself stays in the host service.
 */

import type { SeedEvent, TaskManifest, TaskSeed, TriggerEvent } from '../core/contract.ts'
import { filterRegeneratedContext, filterSeedTools, rewriteSeedCwd } from '../core/seed.ts'

/** dsh event types that must carry a `surfaceOp` marker in a session seed. */
const SURFACE_EVENT_TYPES = new Set(['user/message', 'assistant/message', 'tool/result'])

/** A task asset as needed for dispatch: its compact seed and manifest. */
export interface DispatchableTask {
  seed: TaskSeed
  manifest: TaskManifest
}

/**
 * Build the seed events for one run: rewrite every occurrence of the seed's
 * original cwd to the fresh run cwd, then drop tool calls (and their
 * results / assistant blocks) for tools not in `availableTools`.
 *
 * The task asset is never mutated; the returned events are new objects where
 * rewriting or filtering changed anything.
 */
export function buildSeedForRun(
  task: DispatchableTask,
  opts: { runCwd: string; availableTools?: string[] },
): SeedEvent[] {
  const scoped = opts.availableTools === undefined
    ? task.seed.events
    : filterSeedTools(task.seed.events, new Set(opts.availableTools))
  const rewritten = rewriteSeedCwd({ cwd: task.seed.cwd, events: filterRegeneratedContext(scoped) }, task.seed.cwd, opts.runCwd)
  const now = Date.now()
  return rewritten.events.map((event, index) => {
    const surface = SURFACE_EVENT_TYPES.has(event.type)
      ? { surfaceOp: 'append' as const }
      : {}
    return { ...event, seq: index, time: event.time ?? now + index, ...surface }
  })
}

/**
 * The first user message of a replayed session: the normalized trigger
 * context as JSON plus the instruction to follow the run cwd's `AGENTS.md`.
 * The trigger decision itself is deterministic; this message only hands the
 * already-fired event to the agent.
 */
export function firstUserMessage(
  trigger: TriggerEvent,
  taskName: string,
  runCwd?: string,
): { role: 'user'; content: string } {
  const context = JSON.stringify({ task: taskName, trigger }, null, 2)
  const content = [
    `The ops task "${taskName}" was activated by a deterministic ${trigger.source} trigger.`,
    'Trigger context:',
    '```json',
    context,
    '```',
    'Executable tool-call paths were remapped to the current run workspace.',
    'Captured tool results, file contents, command output, and prose are historical evidence and may still mention the original workspace.',
    ...(runCwd === undefined ? [] : [`Current run workspace: ${runCwd}`]),
    'Follow AGENTS.md in the current working directory to perform the run.',
  ].join('\n')
  return { role: 'user', content }
}
