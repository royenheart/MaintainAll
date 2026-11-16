/**
 * Host plugin for `@royenheart/dsh-plugin-maintainall`.
 *
 * The `maintainall` Cordis service owns the plugin data root, the persisted
 * state files under `storages/`, and the browser-facing HTTP surface the
 * client half talks to: status, task listing, save-request recording,
 * trigger enable/disable toggles, and the session dispatch seam
 * {@link dispatchReplay}.
 */

import type { IncomingMessage, ServerResponse } from 'node:http'
import { randomUUID } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { parse as parseYaml } from 'yaml'
import { Service, type Context } from '@deepseek-ai/cordis'

import type { RegistryState, RunMapState, TaskManifest, TaskMode, TaskTrigger } from './core/contract.ts'
import { assertTaskId, parseManifest } from './core/manifest.ts'
import { exportTask, importTask } from './core/opskit.ts'
import { MAX_EVENT_COUNT, MAX_SEED_BYTES } from './core/seed.ts'
import {
  loadTriggerState,
  pluginDataRoot,
  saveTriggerState,
} from './core/storage.ts'
import { readTaskAsset, writeTaskAsset, writeTaskMeta } from './core/task-writer.ts'
import { PluginLogger } from './core/logger.ts'
import { sendJson } from './core/http.ts'
import { normalizeEvent } from './core/triggers/event.ts'
import { normalizeTriggerFilter } from './core/triggers/normalize.ts'
import type { EngineTask } from './engine/trigger-engine.ts'
import {
  assertReplayModeUnchanged,
  assertSeedBudget,
  buildTaskSeed,
  materializeTaskEdit,
  materializeTaskFromSave,
  summarizeSessionSeed,
  validateContinuationCreation,
  validateTaskTriggers,
  type SaveSessionFace,
  type SaveSessionsFace,
  type SaveTaskMeta,
} from './dispatch/save.ts'
import { buildEditPrompt, buildSavePrompt, type SavePromptSeed } from './dispatch/save-prompt.ts'
import { OPS_SAVE_TASK_TRIGGER_GUIDE, OPS_SAVE_TASK_TRIGGER_SCHEMA } from './dispatch/tool-contract.ts'
import { dispatchReplay } from './dispatch/replay.ts'
import { TaskStateStore } from './host/task-state.ts'
import { ReplayRuntime } from './host/replay-runtime.ts'
import { TriggerRuntime } from './host/trigger-runtime.ts'

export { createRunCwd, runTimestamp } from './dispatch/run-cwd.ts'
export { buildSeedForRun, firstUserMessage } from './dispatch/session.ts'
export { dispatchReplay, type DispatchResult } from './dispatch/replay.ts'
export { sendJson }
export type { DispatchableTask } from './dispatch/session.ts'

/** Cordis service name. */
export const name = 'maintainall'

/** Base pathname of every route this plugin serves. */
export const ROUTE_BASE = '/plugins/@royenheart/dsh-plugin-maintainall'

/** Task creation modes a save request may name. */
const TASK_MODE_VALUES: ReadonlySet<string> = new Set(['safe-copy', 'compact', 'fresh', 'auto'])

/** Composition-time config: `root` overrides the plugin data root (tests). */
export interface MaintainAllConfig {
  root?: string
}

/** Minimal face of the dsh webServer service this plugin consumes. */
interface ConnectionFace {
  requestRejection(request: { readonly headers: IncomingMessage['headers'] }): 401 | 403 | undefined
}

interface WebServerFace {
  register(route: {
    kind: 'exact' | 'prefix'
    path: string
    handler: (req: IncomingMessage, res: ServerResponse) => void | Promise<void>
  }): () => void
}

/** Minimal logger face; `console.warn` is the fallback. */
interface LoggerFace {
  warn(message: string, ...args: unknown[]): void
}

/** Read and parse a JSON request body, bounded to 1 MiB. */
async function readJsonBody(req: IncomingMessage, limit = 1024 * 1024): Promise<unknown> {
  const chunks: Buffer[] = []
  let size = 0
  for await (const chunk of req as AsyncIterable<Buffer>) {
    size += chunk.length
    if (size > limit) throw new Error('request body too large')
    chunks.push(chunk)
  }
  const text = Buffer.concat(chunks).toString('utf8')
  return text.trim() === '' ? {} : JSON.parse(text)
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Session face used when the Save dialog asks the model to auto-generate the task. */
interface FollowupAgentFace {
  readonly session: SaveSessionFace
  followup(message: unknown): void
}

/** Agent registry face used for prompt injection. */
interface AgentsFace {
  get(id: string): FollowupAgentFace | undefined
}

export class MaintainAllService extends Service {
  static inject = ['webServer', 'connection', 'sessions', 'tools', 'agents', 'agentPresets']

  private readonly configuredRoot?: string
  private root = ''
  private state!: TaskStateStore
  private get registry(): RegistryState {
    return this.state.registry
  }
  private get runMap(): RunMapState {
    return this.state.runMap
  }
  private runtime!: TriggerRuntime
  private replay!: ReplayRuntime
  private writeTail: Promise<void> = Promise.resolve()

  /** Serialize task/trigger writes so id checks and persist operations cannot interleave. */
  private async withWrite<T>(operation: () => Promise<T>): Promise<T> {
    const previous = this.writeTail
    let release!: () => void
    this.writeTail = new Promise<void>((resolve) => { release = resolve })
    await previous
    try {
      return await operation()
    } finally {
      release()
    }
  }
  private pluginLog?: PluginLogger

  constructor(ctx: Context, config: MaintainAllConfig = {}) {
    super(ctx, name)
    this.configuredRoot = config.root
  }

  private get logger(): LoggerFace {
    const logger = (this.ctx as unknown as { logger?: LoggerFace }).logger
    return logger ?? { warn: (message, ...args) => console.warn(message, ...args) }
  }

  private logInfo(msg: string, data?: Record<string, unknown>): void {
    const detail = data === undefined ? '' : ' ' + JSON.stringify(data)
    this.logger.warn('maintainall: %s%s', msg, detail)
    try {
      this.pluginLog?.info(msg + detail)
    } catch {
      // Plugin logging is best-effort; never turn a handled error into a
      // rejected engine tick or failed request.
    }
  }

  private logWarn(msg: string, data?: Record<string, unknown>): void {
    const detail = data === undefined ? '' : ' ' + JSON.stringify(data)
    this.logger.warn('maintainall: %s%s', msg, detail)
    try {
      this.pluginLog?.warn(msg + detail)
    } catch {
      // See logInfo.
    }
  }

  private logError(msg: string, data?: Record<string, unknown>): void {
    const detail = data === undefined ? '' : ' ' + JSON.stringify(data)
    this.logger.warn('maintainall: %s%s', msg, detail)
    try {
      this.pluginLog?.error(msg + detail)
    } catch {
      // Engine/onError callbacks are fire-and-forget; a full disk here must not
      // become an unhandled rejection.
    }
  }

  async *[Service.init]() {
    this.root = this.configuredRoot ?? pluginDataRoot()
    mkdirSync(join(this.root, 'ops'), { recursive: true, mode: 0o700 })
    mkdirSync(join(this.root, 'storages'), { recursive: true, mode: 0o700 })
    this.pluginLog = new PluginLogger(join(this.root, 'storages', 'logs'))
    this.state = new TaskStateStore(this.root)
    this.replay = new ReplayRuntime(this.ctx, this.logger)
    this.runtime = new TriggerRuntime(
      this.root,
      () => this.syncEngineTasks(),
      async (taskId, event) => {
        try {
          const result = await dispatchReplay(this.ctx, taskId, event, {
            root: this.root,
            keepAlive: (sessionId, handle) => { this.replay.remember(sessionId, handle) },
            createAgent: (options) => this.replay.createAgent(options),
            resolveSourceAgent: (sessionId) => this.replay.resolveSourceSession(sessionId),
          })
          if (!result.ok) this.logError('dispatch failed', { taskId, error: result.error })
          else if (result.warning !== undefined) this.logError('dispatch bookkeeping incomplete', { taskId, warning: result.warning })
          else this.logInfo('dispatch ok', { taskId, sessionId: result.sessionId })
        } catch (error) {
          this.logError('dispatch exception', {
            taskId,
            error: error instanceof Error ? error.message : String(error),
          })
        } finally {
          this.state.reloadRegistry()
        }
      },
      this.logger,
      (error) => this.logError('trigger engine error', { error: error.message }),
    )

    let disposeTool: (() => void) | undefined
    const disposers: Array<() => void> = []
    try {
      disposeTool = this.registerOpsSaveTask()
      const webServer = this.ctx.get('webServer') as unknown as WebServerFace
      type SessionDisposedListener = (session: { id: string }) => void
      const onSessionDisposed = this.ctx.on.bind(this.ctx) as unknown as (
        event: 'session/disposed',
        listener: SessionDisposedListener,
      ) => () => void
      const fence = (
        handler: (req: IncomingMessage, res: ServerResponse) => void | Promise<void>,
      ) => (req: IncomingMessage, res: ServerResponse): void | Promise<void> => {
        const connection = this.ctx.get('connection') as unknown as ConnectionFace
        const rejection = connection.requestRejection(req)
        if (rejection !== undefined) {
          res.statusCode = rejection
          res.end()
          return
        }
        return handler(req, res)
      }
      const routes: Parameters<WebServerFace['register']>[0][] = [
        { kind: 'exact', path: `${ROUTE_BASE}/logs`, handler: fence((req, res) => this.handleLogs(req, res)) },
        { kind: 'prefix', path: `${ROUTE_BASE}/tasks`, handler: fence((req, res) => this.handleTasksRoute(req, res)) },
        { kind: 'exact', path: `${ROUTE_BASE}/save`, handler: fence((req, res) => this.withWrite(() => this.handleSave(req, res))) },
        { kind: 'exact', path: `${ROUTE_BASE}/import`, handler: fence((req, res) => this.withWrite(() => this.handleImport(req, res))) },
        { kind: 'prefix', path: `${ROUTE_BASE}/export`, handler: fence((req, res) => this.withWrite(() => this.handleExport(req, res))) },
        { kind: 'prefix', path: `${ROUTE_BASE}/webhook`, handler: (req, res) => this.handleWebhook(req, res) },
        { kind: 'prefix', path: `${ROUTE_BASE}/triggers`, handler: fence((req, res) => this.withWrite(() => this.handleTriggerToggle(req, res))) },
      ]
      for (const route of routes) disposers.push(webServer.register(route))
      // Keep the retained-handle map bounded to live sessions. The handle is
      // not needed after dsh disposes its Session.
      const offSessionDisposed = onSessionDisposed('session/disposed', (session) => {
        this.replay.forget(session.id)
      })
      if (typeof offSessionDisposed === 'function') disposers.push(offSessionDisposed)


      await this.runtime.start()
    } catch (error) {
      try {
        await this.runtime.stop()
      } catch {
        // Cleanup below must run even when the final state flush fails.
      }
      for (const dispose of disposers) dispose()
      disposeTool?.()
      this.replay.stop()
      throw error
    }

    yield async () => {
      try {
        await this.runtime.stop()
      } finally {
        for (const dispose of disposers) dispose()
        disposeTool?.()
        this.replay.stop()
      }
    }
    this.logInfo('plugin ready', { root: this.root })
  }

  /** Register the `ops_save_task` tool the model calls to persist a generated task. */
  private registerOpsSaveTask(): () => void {
    const tools = this.ctx.get('tools') as unknown as { register(definition: unknown): () => void }
    const root = this.root
    const definition: unknown = {
      name: 'ops_save_task',
      description:
        'Persist the current ops session as a reusable task asset. Use it after the user asked to save the task: provide the task id/name/description, the runbook instructions, the trigger list, and the boundarySeq that separates the successful trajectory from the current generation turn.'
        + '\n\nTriggers:\n'
        + OPS_SAVE_TASK_TRIGGER_GUIDE
        + '\n\nReplay target:\n'
        + '- "new-session" (default) creates a seeded Run session.\n'
        + '- "continue-session" delivers the trigger into the source Session; it requires taskMode "fresh" '
        + 'and stores no replay seed.',
      parameters: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          name: { type: 'string' },
          description: { type: 'string' },
          instructions: { type: 'string' },
          triggers: {
            type: 'array',
            description:
              'Deterministic triggers. `source` is the trigger kind; schedule rules go in '
              + '`params`, source selectors in `filter`.',
            items: OPS_SAVE_TASK_TRIGGER_SCHEMA,
          },
          boundarySeq: { type: 'integer', minimum: 0 },
          skills: { type: 'object', additionalProperties: true },
          scripts: { type: 'object', additionalProperties: true },
          taskMode: { type: 'string', enum: ['safe-copy', 'compact', 'fresh'] },
          replayMode: {
            type: 'string',
            enum: ['new-session', 'continue-session'],
            description:
              'Creation-time replay target. "continue-session" keeps the source Session and requires '
              + 'taskMode "fresh"; "new-session" (default) creates a seeded Run session.',
          },
          icon: { type: 'string' },
          color: { type: 'string' },
          naturalPrompt: { type: 'string' },
        },
        required: ['id', 'name', 'description', 'instructions', 'triggers', 'boundarySeq'],
        additionalProperties: false,
      },
      output: {
        schema: {
          type: 'object',
          properties: { ok: { type: 'boolean' }, taskId: { type: 'string' }, path: { type: 'string' } },
          required: ['ok', 'taskId'],
          additionalProperties: false,
        },
        render: (_args: unknown, value: unknown) => {
          const result = value as { taskId?: string; path?: string }
          return [{ type: 'text', text: `ops task saved: ${result.taskId ?? ''} at ${result.path ?? ''}` }]
        },
      },
      execute: async (args: unknown, exec: unknown): Promise<unknown> => this.withWrite(async () => {
        const input = args as {
          id: string
          name: string
          description: string
          instructions: string
          triggers: TaskTrigger[]
          boundarySeq: number
          skills?: Record<string, string>
          scripts?: Record<string, string>
          taskMode?: TaskMode
          replayMode?: 'new-session' | 'continue-session'
          icon?: string
          color?: string
          naturalPrompt?: string
        }
        assertTaskId(input.id)
        if (typeof input.id !== 'string' || typeof input.name !== 'string' || input.name.trim() === ''
          || typeof input.description !== 'string' || typeof input.instructions !== 'string'
          || !Array.isArray(input.triggers)) {
          throw new Error('ops_save_task: invalid task metadata')
        }
        if (!Number.isInteger(input.boundarySeq) || input.boundarySeq < 0) {
          throw new Error('ops_save_task: boundarySeq must be a non-negative integer')
        }
        const replayMode = input.replayMode ?? 'new-session'
        if (replayMode !== 'new-session' && replayMode !== 'continue-session') {
          throw new Error('ops_save_task: replayMode must be "new-session" or "continue-session"')
        }
        const agent = (exec as { agent?: { session?: SaveSessionFace } }).agent
        const session = agent?.session
        if (session === undefined) throw new Error('ops_save_task: caller session is unavailable')
        const triggers = input.triggers.map((raw, index) => {
          if (!isPlainObject(raw)) throw new Error(`ops_save_task: triggers[${index}] must be an object`)
          return normalizeTriggerFilter(raw as unknown as TaskTrigger)
        })
        validateTaskTriggers(triggers)
        await this.assertTriggerIdsAvailable(input.id, triggers)
        const taskDir = join(root, 'ops', input.id)

        // Re-saving an existing task is an edit: preserve the captured seed,
        // skills, scripts, runs, and machine-local bindings/requirements.
        let existing: Awaited<ReturnType<typeof readTaskAsset>> | undefined
        let removedTriggerIds: string[] = []
        try {
          existing = await readTaskAsset(root, input.id)
        } catch (error) {
          if (existsSync(taskDir)) {
            throw new Error(`existing task asset is unreadable: ${error instanceof Error ? error.message : String(error)}`)
          }
        }
        if (existing !== undefined) {
          assertReplayModeUnchanged(existing.manifest, input.replayMode)
          const instructions = input.instructions.trim() === '' ? existing.agensMd : input.instructions
          const manifest: TaskManifest = {
            format: existing.manifest.format,
            id: input.id,
            name: input.name,
            description: input.description,
            version: existing.manifest.version,
            ...(existing.manifest.taskMode === undefined ? {} : { taskMode: existing.manifest.taskMode }),
            ...(input.icon === undefined
              ? (existing.manifest.icon === undefined ? {} : { icon: existing.manifest.icon })
              : { icon: input.icon }),
            ...(input.color === undefined
              ? (existing.manifest.color === undefined ? {} : { color: existing.manifest.color })
              : { color: input.color }),
            ...(input.naturalPrompt === undefined
              ? (existing.manifest.naturalPrompt === undefined ? {} : { naturalPrompt: existing.manifest.naturalPrompt })
              : { naturalPrompt: input.naturalPrompt }),
            ...(existing.manifest.requires === undefined ? {} : { requires: existing.manifest.requires }),
            ...(existing.manifest.bindings === undefined ? {} : { bindings: existing.manifest.bindings }),
          }
          await writeTaskMeta(taskDir, {
            manifest,
            agensMd: instructions,
            triggers,
          })
          removedTriggerIds = existing.triggers
            .map((trigger) => trigger.id)
            .filter((id) => !triggers.some((trigger) => trigger.id === id))
        } else {
          const taskMode = input.taskMode ?? 'safe-copy'
          if (!TASK_MODE_VALUES.has(taskMode)) {
            throw new Error('taskMode must be safe-copy, compact, fresh, or auto')
          }
          if (taskMode === 'auto') throw new Error('auto is a request mode; choose safe-copy, compact, or fresh')
          const continueSession = replayMode === 'continue-session'
          validateContinuationCreation({ continueSession, taskMode })
          const cwd = session.header.cwd
          if (taskMode !== 'fresh' && (typeof cwd !== 'string' || cwd.trim() === '')) {
            throw new Error('session cwd is unavailable; cannot materialize a replay seed')
          }
          const instructions = input.instructions.trim() === ''
            ? `# ${input.name}\n\n${input.description}`
            : input.instructions
          let boundary = input.boundarySeq
          if (boundary === 0) {
            for (const event of session.snapshotEvents()) {
              if (event.type === 'turn/end') boundary = event.seq
            }
          }
          const seed = buildTaskSeed(session, boundary, taskMode)
          const manifest: TaskManifest = {
            format: 'dsh-opskit/1',
            id: input.id,
            name: input.name,
            description: input.description,
            version: '0.1.0',
            taskMode,
            ...(continueSession ? { bindings: { continueSession: { sessionId: session.id } } } : {}),
            ...(input.icon === undefined ? {} : { icon: input.icon }),
            ...(input.color === undefined ? {} : { color: input.color }),
            ...(input.naturalPrompt === undefined ? {} : { naturalPrompt: input.naturalPrompt }),
          }
          await writeTaskAsset(root, {
            manifest,
            agensMd: instructions,
            skills: input.skills === undefined ? new Map() : new Map(Object.entries(input.skills)),
            scripts: input.scripts === undefined ? new Map() : new Map(Object.entries(input.scripts)),
            seed,
            triggers,
          })
        }
        const savedManifest = (await readTaskAsset(root, input.id)).manifest
        const previousRecord = this.registry.tasks[input.id]
        this.registry.tasks[input.id] = {
          id: input.id,
          name: input.name,
          version: savedManifest.version,
          enabled: previousRecord?.enabled ?? triggers.some((trigger) => trigger.enabled),
          importedAt: previousRecord?.importedAt ?? new Date().toISOString(),
          ...(previousRecord?.lastRunAt === undefined ? {} : { lastRunAt: previousRecord.lastRunAt }),
            ...(savedManifest.icon === undefined ? {} : { icon: savedManifest.icon }),
          ...(savedManifest.color === undefined ? {} : { color: savedManifest.color }),
        }
        try {
          this.state.saveRegistry()
        } catch (error) {
          if (previousRecord === undefined) delete this.registry.tasks[input.id]
          else this.registry.tasks[input.id] = previousRecord
          if (existing === undefined) {
            rmSync(taskDir, { recursive: true, force: true })
          } else {
            try {
              await writeTaskMeta(taskDir, {
                manifest: existing.manifest,
                agensMd: existing.agensMd,
                triggers: existing.triggers,
              })
            } catch {
              // Keep the original persistence error; the asset may need repair.
            }
          }
          throw error
        }
        if (removedTriggerIds.length > 0) this.runtime.forget(removedTriggerIds)
        this.runtime.reload()
        return { ok: true, taskId: input.id, path: taskDir }
      }),
    }
    return tools.register(definition)
  }

  /** Read enabled tasks and their enabled triggers from disk, synchronously. */
  private syncEngineTasks(): EngineTask[] {
    const tasks: EngineTask[] = []
    for (const [taskId, record] of Object.entries(this.registry.tasks)) {
      if (!record.enabled) continue
      const triggersPath = join(this.root, 'ops', taskId, 'triggers.yml')
      if (!existsSync(triggersPath)) continue
      const parsed = parseYaml(readFileSync(triggersPath, 'utf8')) as { triggers?: TaskTrigger[] }
      const triggers = (parsed.triggers ?? [])
        .map(normalizeTriggerFilter)
        .filter((trigger) => trigger.enabled)
      if (triggers.length > 0) tasks.push({ taskId, triggers })
    }
    return tasks
  }

  /** Reject trigger ids already used by another task before anything is written. */
  private async assertTriggerIdsAvailable(taskId: string | undefined, triggers: readonly TaskTrigger[]): Promise<void> {
    const ids = new Set<string>()
    for (const trigger of triggers) {
      if (typeof trigger.id !== 'string' || trigger.id.trim() === '') {
        throw new Error('trigger id must be a non-empty string')
      }
      if (ids.has(trigger.id)) throw new Error(`duplicate trigger id: ${trigger.id}`)
      ids.add(trigger.id)
    }
    if (ids.size === 0) return
    for (const otherId of Object.keys(this.registry.tasks)) {
      if (otherId === taskId) continue
      const path = join(this.root, 'ops', otherId, 'triggers.yml')
      if (!existsSync(path)) continue
      const parsed = parseYaml(readFileSync(path, 'utf8')) as { triggers?: TaskTrigger[] }
      for (const trigger of parsed.triggers ?? []) {
        if (ids.has(trigger.id)) {
          throw new Error(`trigger id '${trigger.id}' is already used by task '${otherId}'`)
        }
      }
    }
  }

  // ---- route handlers -----------------------------------------------------


  private handleTasks(req: IncomingMessage, res: ServerResponse): void {
    if (!this.requireMethod(req, res, 'GET')) return
    sendJson(res, 200, { ok: true, tasks: Object.values(this.registry.tasks) })
  }

  private handleLogs(req: IncomingMessage, res: ServerResponse): void {
    if (!this.requireMethod(req, res, 'GET')) return
    const url = new URL(req.url ?? '', 'http://localhost')
    const limit = Math.min(500, Math.max(1, Number(url.searchParams.get('limit')) || 200))
    const offset = Math.max(0, Number(url.searchParams.get('offset')) || 0)
    const page = this.pluginLog?.read(limit, offset) ?? { entries: [], hasMore: false }
    sendJson(res, 200, { ok: true, entries: page.entries, hasMore: page.hasMore })
  }

  private async handleTasksRoute(req: IncomingMessage, res: ServerResponse): Promise<void> {
    const pathname = new URL(req.url ?? '', 'http://localhost').pathname
    const rest = pathname.slice(`${ROUTE_BASE}/tasks`.length)
    const parts = rest.split('/').filter((part) => part !== '')
    if (parts.length === 0) {
      this.handleTasks(req, res)
      return
    }
    const [taskId, action] = parts
    if (parts.length === 1 && (req.method === 'GET' || req.method === 'HEAD')) {
      await this.handleTaskDetail(req, res, taskId)
      return
    }
    if (parts.length === 2 && action === 'run' && req.method === 'POST') {
      await this.handleTaskRun(req, res, taskId)
      return
    }
    if (parts.length === 2 && action === 'delete' && req.method === 'POST') {
      await this.withWrite(() => this.handleTaskDelete(req, res, taskId))
      return
    }
    if (parts.length === 2 && action === 'edit' && req.method === 'POST') {
      await this.withWrite(() => this.handleTaskEdit(req, res, taskId))
      return
    }
    if (parts.length === 2 && action === 'runs' && (req.method === 'GET' || req.method === 'HEAD')) {
      await this.handleTaskRuns(req, res, taskId)
      return
    }
    sendJson(res, 404, { ok: false, error: 'expected /tasks, /tasks/<taskId>, /tasks/<taskId>/run, /tasks/<taskId>/delete, /tasks/<taskId>/edit, or /tasks/<taskId>/runs' })
  }

  private async handleTaskDetail(req: IncomingMessage, res: ServerResponse, taskId: string): Promise<void> {
    if (!this.requireMethod(req, res, 'GET')) return
    if (!/^[a-z0-9][a-z0-9-]*$/.test(taskId)) {
      sendJson(res, 404, { ok: false, error: `invalid task id: ${taskId}` })
      return
    }
    try {
      const task = await readTaskAsset(this.root, taskId)
      const record = this.registry.tasks[taskId]
      this.state.reloadRuns()
      const runMap = this.state.runMap
      const runs = Object.entries(runMap.runs)
        .filter(([, run]) => run.taskId === taskId)
        .map(([runId, run]) => ({ runId, sessionId: run.sessionId, createdAt: run.createdAt }))
      sendJson(res, 200, {
        ok: true,
        task: {
          id: taskId,
          name: task.manifest.name,
          description: task.manifest.description,
          version: task.manifest.version,
          taskMode: task.manifest.taskMode ?? 'safe-copy',
          continueSession: task.manifest.bindings?.continueSession !== undefined,
          icon: task.manifest.icon ?? '',
          color: task.manifest.color ?? '',
          naturalPrompt: task.manifest.naturalPrompt ?? '',
          enabled: record?.enabled ?? false,
          lastRunAt: record?.lastRunAt,
          instructions: task.agensMd,
          triggers: task.triggers,
          skills: [...task.skills.keys()],
          scripts: [...task.scripts.keys()],
          runs,
        },
      })
    } catch (error) {
      sendJson(res, 404, { ok: false, error: error instanceof Error ? error.message : String(error) })
    }
  }

  private async handleTaskRun(req: IncomingMessage, res: ServerResponse, taskId: string): Promise<void> {
    if (!this.requireMethod(req, res, 'POST')) return
    const record = this.registry.tasks[taskId]
    if (record === undefined) {
      sendJson(res, 404, { ok: false, error: `unknown task: ${taskId}` })
      return
    }
    this.logInfo('manual run requested', { taskId })
    try {
      const event = normalizeEvent('manual', new Date().toISOString(), {})
      const result = await dispatchReplay(this.ctx, taskId, event, {
        root: this.root,
        keepAlive: (sessionId, handle) => { this.replay.remember(sessionId, handle) },
        createAgent: (options) => this.replay.createAgent(options),
        resolveSourceAgent: (sessionId) => this.replay.resolveSourceSession(sessionId),
      })
      if (result.ok) {
        this.state.reloadRegistry()
        if (result.warning !== undefined) this.logError('manual run bookkeeping incomplete', { taskId, warning: result.warning })
        else this.logInfo('manual run dispatched', { taskId, sessionId: result.sessionId })
      } else {
        this.logError('manual run failed', { taskId, error: result.error })
      }
      sendJson(res, result.ok ? 200 : 400, result)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      this.logError('manual run exception', { taskId, error: message })
      sendJson(res, 400, { ok: false, error: message })
    }
  }

  private async handleTaskRuns(req: IncomingMessage, res: ServerResponse, taskId: string): Promise<void> {
    if (!this.requireMethod(req, res, 'GET')) return
    const url = new URL(req.url ?? '', 'http://localhost')
    const limit = Math.min(50, Math.max(1, Number(url.searchParams.get('limit')) || 10))
    const offset = Math.max(0, Number(url.searchParams.get('offset')) || 0)
    this.state.reloadRuns()
      const runMap = this.state.runMap
    const all = Object.entries(runMap.runs)
      .filter(([, run]) => run.taskId === taskId)
      .sort((a, b) => b[1].createdAt.localeCompare(a[1].createdAt))
    const runs = all.slice(offset, offset + limit).map(([runId, run]) => ({
      runId,
      sessionId: run.sessionId,
      createdAt: run.createdAt,
    }))
    sendJson(res, 200, { ok: true, runs, hasMore: offset + limit < all.length })
  }

  private async handleTaskEdit(req: IncomingMessage, res: ServerResponse, taskId: string): Promise<void> {
    if (!this.requireMethod(req, res, 'POST')) return
    if (!/^[a-z0-9][a-z0-9-]*$/.test(taskId)) {
      sendJson(res, 404, { ok: false, error: `invalid task id: ${taskId}` })
      return
    }
    let body: unknown
    try {
      body = await readJsonBody(req)
    } catch (error) {
      sendJson(res, 400, { ok: false, error: error instanceof Error ? error.message : String(error) })
      return
    }
    if (!isPlainObject(body)) {
      sendJson(res, 400, { ok: false, error: 'body must be a JSON object' })
      return
    }
    if (body.materialize === true) {
      await this.handleTaskEditMaterialize(res, taskId, body)
      return
    }
    await this.handleTaskEditLlm(res, taskId, body)
  }

  /** Manual edit: update metadata in place. The seed and taskMode stay untouched. */
  private async handleTaskEditMaterialize(
    res: ServerResponse,
    taskId: string,
    body: Record<string, unknown>,
  ): Promise<void> {
    try {
      const meta = body.meta
      if (!isPlainObject(meta)) {
        sendJson(res, 400, { ok: false, error: 'meta must be a JSON object' })
        return
      }
      const existing = await readTaskAsset(this.root, taskId)
      const name = typeof meta.name === 'string' && meta.name.trim() !== '' ? meta.name : existing.manifest.name
      const description = typeof meta.description === 'string' ? meta.description : existing.manifest.description
      const rawTriggers = Array.isArray(meta.triggers) && meta.triggers.length > 0
        ? meta.triggers as TaskTrigger[]
        : existing.triggers
      const triggers = rawTriggers.map(normalizeTriggerFilter)
      validateTaskTriggers(triggers)
      await this.assertTriggerIdsAvailable(taskId, triggers)
      const removed = existing.triggers
        .map((trigger) => trigger.id)
        .filter((id) => !triggers.some((trigger) => trigger.id === id))
      const taskDir = await materializeTaskEdit(this.root, taskId, {
        name,
        description,
        ...(typeof meta.instructions === 'string' && meta.instructions.trim() !== ''
          ? { instructions: meta.instructions }
          : {}),
        triggers,
        ...(typeof meta.icon === 'string' ? { icon: meta.icon } : {}),
        ...(typeof meta.color === 'string' ? { color: meta.color } : {}),
        ...(typeof meta.naturalPrompt === 'string' ? { naturalPrompt: meta.naturalPrompt } : {}),
      })
      this.state.reloadRegistry()
      if (removed.length > 0) this.runtime.forget(removed)
      this.runtime.reload()
      this.logInfo('task metadata edited', { taskId })
      sendJson(res, 200, { ok: true, path: taskDir })
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      this.logError('task edit failed', { taskId, error: message })
      sendJson(res, 400, { ok: false, error: message })
    }
  }

  /** Natural-language edit: open a fresh session and let the model re-set the task. */
  private async handleTaskEditLlm(
    res: ServerResponse,
    taskId: string,
    body: Record<string, unknown>,
  ): Promise<void> {
    try {
      const task = await readTaskAsset(this.root, taskId)
      const taskDir = join(this.root, 'ops', taskId)
      const sessionId = `session-${randomUUID()}`
      const handle = await this.replay.createAgent({
        sessionId,
        defaultPreset: 'deployment',
        meta: {
          cwd: taskDir,
          ...(task.manifest.bindings?.agentPreset?.hint === undefined
            ? {}
            : { agentPreset: task.manifest.bindings.agentPreset.hint }),
        },
      })
      this.replay.remember(sessionId, handle)
      const description = typeof body.description === 'string' ? body.description : ''
      const wants = {
        ...(typeof body.icon === 'string' ? { icon: body.icon } : {}),
        ...(typeof body.color === 'string' ? { color: body.color } : {}),
        ...(typeof body.naturalPrompt === 'string' && body.naturalPrompt !== ''
          ? { naturalPrompt: body.naturalPrompt }
          : {}),
      }
      const prompt = buildEditPrompt(task, description, wants)
      try {
        handle.agent.followup({
          id: randomUUID(),
          role: 'user',
          content: [{ type: 'text', text: prompt }],
          source: { kind: 'plugin:maintainall' },
        })
      } catch (error) {
        this.replay.forget(sessionId)
        try {
          await (handle as { dispose?: () => void | Promise<void> }).dispose?.()
        } catch {
          // Rollback is best effort; report the original failure.
        }
        throw error
      }
      this.logInfo('edit session created', { taskId, sessionId })
      sendJson(res, 200, { ok: true, sessionId })
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      this.logError('task edit failed', { taskId, error: message })
      sendJson(res, 400, { ok: false, error: message })
    }
  }

  private async handleTaskDelete(req: IncomingMessage, res: ServerResponse, taskId: string): Promise<void> {
    if (!this.requireMethod(req, res, 'POST')) return
    try { assertTaskId(taskId) } catch { sendJson(res, 404, { ok: false, error: 'unknown task' }); return }
    const record = this.registry.tasks[taskId]
    if (record === undefined) {
      sendJson(res, 404, { ok: false, error: `unknown task: ${taskId}` })
      return
    }
    try {
      const triggerIds: string[] = []
      try {
        const task = await readTaskAsset(this.root, taskId)
        triggerIds.push(...task.triggers.map((trigger) => trigger.id))
      } catch {
        // The asset may already be missing; the registry/run-map cleanup below still applies.
      }
      if (this.runtime.active) {
        for (const id of this.runtime.triggerIdsForTask(taskId)) {
          if (!triggerIds.includes(id)) triggerIds.push(id)
        }
      }
      // Remove the registry entry and fence the engine before deleting the
      // directory, so no new dispatch can observe a task whose files are gone.
      delete this.registry.tasks[taskId]
      try {
        this.state.saveRegistry()
      } catch (error) {
        this.registry.tasks[taskId] = record
        throw error
      }
      try {
        this.runtime.reload()
      } catch (error) {
        this.registry.tasks[taskId] = record
        this.state.saveRegistry()
        try {
          this.runtime.reload()
        } catch {
          // Best effort; the original reload failure is reported below.
        }
        throw error
      }
      try {
        rmSync(join(this.root, 'ops', taskId), { recursive: true, force: true })
      } catch (error) {
        this.registry.tasks[taskId] = record
        this.state.saveRegistry()
        this.runtime.reload()
        throw error
      }
      try {
        this.runtime.forget(triggerIds)
      } catch (error) {
        this.logError('task deleted but trigger state cleanup failed', {
          taskId,
          error: error instanceof Error ? error.message : String(error),
        })
      }
      try {
        this.state.reloadRuns()
      const runMap = this.state.runMap
        for (const [runId, run] of Object.entries(runMap.runs)) {
          if (run.taskId === taskId) delete runMap.runs[runId]
        }
        this.state.saveRuns()
      } catch (error) {
        this.logError('task deleted but run-map cleanup failed', {
          taskId,
          error: error instanceof Error ? error.message : String(error),
        })
      }
      if (!this.runtime.active) {
        // No engine owns trigger state yet; clean it directly on this path.
        try {
          const triggerState = loadTriggerState(this.root)
          let triggerStateChanged = false
          for (const triggerId of triggerIds) {
            if (delete triggerState.schedules[triggerId]) triggerStateChanged = true
            if (delete triggerState.triggers[triggerId]) triggerStateChanged = true
            if (delete triggerState.filewatch[triggerId]) triggerStateChanged = true
            if (delete triggerState.exec[triggerId]) triggerStateChanged = true
          }
          if (triggerStateChanged) saveTriggerState(this.root, triggerState)
        } catch (error) {
          this.logError('task deleted but trigger state cleanup failed', {
            taskId,
            error: error instanceof Error ? error.message : String(error),
          })
        }
      }
      this.logInfo('task deleted', { taskId })
      sendJson(res, 200, { ok: true })
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      this.logError('task delete failed', { taskId, error: message })
      sendJson(res, 400, { ok: false, error: message })
    }
  }

  private async handleSave(req: IncomingMessage, res: ServerResponse): Promise<void> {
    if (!this.requireMethod(req, res, 'POST')) return
    let body: unknown
    try {
      body = await readJsonBody(req)
    } catch (error) {
      sendJson(res, 400, { ok: false, error: error instanceof Error ? error.message : String(error) })
      return
    }
    if (!isPlainObject(body)) {
      sendJson(res, 400, { ok: false, error: 'body must be a JSON object' })
      return
    }
    const { sessionId, boundarySeq, meta } = body
    if (typeof sessionId !== 'string' || sessionId === '') {
      sendJson(res, 400, { ok: false, error: 'sessionId must be a non-empty string' })
      return
    }
    if (typeof boundarySeq !== 'number' || !Number.isInteger(boundarySeq) || boundarySeq < 0) {
      sendJson(res, 400, { ok: false, error: 'boundarySeq must be a non-negative integer' })
      return
    }
    if (!isPlainObject(meta)) {
      sendJson(res, 400, { ok: false, error: 'meta must be a JSON object' })
      return
    }
    if (meta.auto === true) {
      try {
        const agents = this.ctx.get('agents') as unknown as AgentsFace
        const agent = agents.get(sessionId)
        if (agent === undefined) throw new Error('no live agent for session: ' + sessionId)
        const events = agent.session.snapshotEvents()
        const lastSeq = events.length > 0 ? (events[events.length - 1]?.seq ?? 0) : 0
        // The dialog submits 0 for "latest"; honor an explicit earlier boundary
        // when the caller retries with one (for example the tool's
        // fitting-boundary hint after a seed-budget rejection).
        const cut = boundarySeq === 0 ? lastSeq : boundarySeq
        const description = typeof meta.description === 'string' ? meta.description : ''
        const wants = {
          ...(typeof meta.icon === 'string' ? { icon: meta.icon } : {}),
          ...(typeof meta.color === 'string' ? { color: meta.color } : {}),
          ...(typeof meta.naturalPrompt === 'string' ? { naturalPrompt: meta.naturalPrompt } : {}),
        }
        const editTaskId = typeof meta.editTaskId === 'string' && meta.editTaskId !== ''
          ? meta.editTaskId
          : undefined
        if (meta.continueSession !== undefined && typeof meta.continueSession !== 'boolean') {
          throw new Error('continueSession must be a boolean')
        }
        const continueSession = meta.continueSession === true
        if (continueSession && meta.editTaskId !== undefined) {
          throw new Error('the continuation replay target is fixed at creation; it cannot be set by an edit prompt')
        }
        const taskMode = typeof meta.taskMode === 'string' ? meta.taskMode : 'safe-copy'
        if (taskMode !== 'safe-copy' && taskMode !== 'compact' && taskMode !== 'fresh' && taskMode !== 'auto') {
          throw new Error('taskMode must be safe-copy, compact, fresh, or auto')
        }
        // Measure the replay seed before injecting the save prompt. A concrete
        // mode that cannot fit fails here with the measured numbers instead of
        // spending a model turn only to fail in `ops_save_task`.
        for (const field of ['agentPresetHint', 'permissionPresetHint'] as const) {
          if (meta[field] !== undefined && typeof meta[field] !== 'string') {
            throw new Error(`${field} must be a string when present`)
          }
        }
        validateContinuationCreation({
          continueSession,
          taskMode,
          ...(typeof meta.agentPresetHint === 'string' ? { agentPresetHint: meta.agentPresetHint } : {}),
          ...(typeof meta.permissionPresetHint === 'string' ? { permissionPresetHint: meta.permissionPresetHint } : {}),
        })
        let seed: SavePromptSeed | undefined
        let seedUnavailable: string | undefined
        if (editTaskId === undefined && taskMode !== 'fresh' && !continueSession) {
          try {
            const summary = summarizeSessionSeed(agent.session, cut)
            seed = {
              boundarySeq: cut,
              safeCopyBytes: summary.safeCopyBytes,
              compactBytes: summary.compactBytes,
              safeCopyEventCount: summary.eventCount,
              compactEventCount: summary.compactEventCount,
              maxBytes: MAX_SEED_BYTES,
              maxEvents: MAX_EVENT_COUNT,
            }
            if (taskMode !== 'auto') assertSeedBudget(agent.session, summary, taskMode)
          } catch (error) {
            // `auto` may still choose `fresh`; a concrete capture mode cannot.
            if (taskMode !== 'auto') throw error
            seedUnavailable = error instanceof Error ? error.message : String(error)
          }
        }
        const prompt = editTaskId === undefined
          ? buildSavePrompt(description, cut, taskMode, wants, seed, seedUnavailable, continueSession)
          : buildEditPrompt(await readTaskAsset(this.root, editTaskId), description, wants)
        agent.followup({
          id: randomUUID(),
          role: 'user',
          content: [{ type: 'text', text: prompt }],
          source: { kind: 'plugin:maintainall' },
        })
        sendJson(res, 200, { ok: true, mode: 'llm' })
      } catch (error) {
        sendJson(res, 400, { ok: false, error: error instanceof Error ? error.message : String(error) })
      }
      return
    }
    if (meta.materialize === true) {
      try {
        if (meta.triggers !== undefined && !Array.isArray(meta.triggers)) {
          throw new Error('triggers must be an array')
        }
        if (meta.continueSession !== undefined && typeof meta.continueSession !== 'boolean') {
          throw new Error('continueSession must be a boolean')
        }
        const rawTriggers = Array.isArray(meta.triggers) ? meta.triggers as TaskTrigger[] : []
        const triggers = rawTriggers.map(normalizeTriggerFilter)
        validateTaskTriggers(triggers)
        await this.assertTriggerIdsAvailable(typeof meta.id === 'string' ? meta.id : undefined, triggers)
        const sessions = this.ctx.get('sessions') as unknown as SaveSessionsFace
        let cut = boundarySeq
        if (cut === 0) {
          const events = sessions.get(sessionId)?.snapshotEvents() ?? []
          cut = events.length > 0 ? (events[events.length - 1]?.seq ?? 0) : 0
        }
        const taskDir = await materializeTaskFromSave(this.root, sessions, {
          sessionId,
          boundarySeq: cut,
          meta: { ...(meta as unknown as SaveTaskMeta), triggers },
        })
        this.state.reloadRegistry()
        this.runtime.reload()
        sendJson(res, 200, { ok: true, path: taskDir })
      } catch (error) {
        sendJson(res, 400, { ok: false, error: error instanceof Error ? error.message : String(error) })
      }
      return
    }
    sendJson(res, 400, { ok: false, error: 'save requires auto:true or materialize:true' })
  }

  private async handleImport(req: IncomingMessage, res: ServerResponse): Promise<void> {
    if (!this.requireMethod(req, res, 'POST')) return
    let body: unknown
    try {
      body = await readJsonBody(req)
    } catch (error) {
      sendJson(res, 400, { ok: false, error: error instanceof Error ? error.message : String(error) })
      return
    }
    if (!isPlainObject(body) || typeof body.zipPath !== 'string' || body.zipPath === '') {
      sendJson(res, 400, { ok: false, error: 'zipPath must be a non-empty string' })
      return
    }
    try {
      let bindings: { agentPreset?: string; permissionPreset?: string } | undefined
      if (body.bindings !== undefined) {
        if (!isPlainObject(body.bindings)) throw new Error('bindings must be an object')
        const agentPreset = body.bindings.agentPreset
        const permissionPreset = body.bindings.permissionPreset
        if (agentPreset !== undefined && typeof agentPreset !== 'string') throw new Error('bindings.agentPreset must be a string')
        if (permissionPreset !== undefined && typeof permissionPreset !== 'string') throw new Error('bindings.permissionPreset must be a string')
        bindings = {
          ...(agentPreset === undefined ? {} : { agentPreset }),
          ...(permissionPreset === undefined ? {} : { permissionPreset }),
        }
      }
      const imported = await importTask(this.root, body.zipPath, {
        bindings,
        validateTriggers: async (triggers) => {
          validateTaskTriggers(triggers)
          await this.assertTriggerIdsAvailable(undefined, triggers)
        },
      })
      const manifest = parseManifest(readFileSync(join(imported.path, 'manifest.yml'), 'utf8'))
      const previousRecord = this.registry.tasks[imported.taskId]
      try {
        this.registry.tasks[imported.taskId] = {
          id: imported.taskId,
          name: manifest.name,
          version: manifest.version,
          enabled: false,
          importedAt: new Date().toISOString(),
          ...(manifest.icon === undefined ? {} : { icon: manifest.icon }),
          ...(manifest.color === undefined ? {} : { color: manifest.color }),
        }
        this.state.saveRegistry()
        this.runtime.reload()
      } catch (error) {
        if (previousRecord === undefined) delete this.registry.tasks[imported.taskId]
        else this.registry.tasks[imported.taskId] = previousRecord
        try {
          this.state.saveRegistry()
        } catch {
          // Best effort; the original failure is reported below.
        }
        rmSync(imported.path, { recursive: true, force: true })
        throw error
      }
      sendJson(res, 200, { ok: true, taskId: imported.taskId, path: imported.path })
    } catch (error) {
      sendJson(res, 400, { ok: false, error: error instanceof Error ? error.message : String(error) })
    }
  }

  private async handleExport(req: IncomingMessage, res: ServerResponse): Promise<void> {
    if (!this.requireMethod(req, res, 'GET')) return
    const pathname = new URL(req.url ?? '', 'http://localhost').pathname
    const taskId = pathname.slice(`${ROUTE_BASE}/export/`.length)
    if (!/^[a-z0-9][a-z0-9-]*$/.test(taskId)) {
      sendJson(res, 404, { ok: false, error: 'expected /export/<taskId>' })
      return
    }
    try {
      const outDir = join(this.root, 'storages', 'exports')
      mkdirSync(outDir, { recursive: true, mode: 0o700 })
      const zipPath = await exportTask(this.root, taskId, outDir)
      sendJson(res, 200, { ok: true, path: zipPath })
    } catch (error) {
      sendJson(res, 400, { ok: false, error: error instanceof Error ? error.message : String(error) })
    }
  }

  private async handleTriggerToggle(req: IncomingMessage, res: ServerResponse): Promise<void> {
    if (!this.requireMethod(req, res, 'POST')) return
    const pathname = new URL(req.url ?? '', 'http://localhost').pathname
    const rest = pathname.slice(`${ROUTE_BASE}/triggers/`.length)
    const parts = rest.split('/').filter((part) => part !== '')
    const [taskId, action] = parts
    if (parts.length !== 2 || taskId === undefined || (action !== 'enable' && action !== 'disable')) {
      sendJson(res, 404, { ok: false, error: 'expected /triggers/<taskId>/(enable|disable)' })
      return
    }
    const record = this.registry.tasks[taskId]
    if (record === undefined) {
      sendJson(res, 404, { ok: false, error: `unknown task: ${taskId}` })
      return
    }
    let previous = record.enabled
    let originalTriggers: TaskTrigger[] | undefined
    let current: (typeof this.registry.tasks)[string] | undefined
    try {
      if (action === 'enable') {
        const task = await readTaskAsset(this.root, taskId)
        validateTaskTriggers(task.triggers)
        await this.assertTriggerIdsAvailable(taskId, task.triggers)
        if (task.triggers.length > 0 && task.triggers.every((trigger) => !trigger.enabled)) {
          originalTriggers = task.triggers
          await writeTaskMeta(join(this.root, 'ops', taskId), {
            manifest: task.manifest,
            agensMd: task.agensMd,
            triggers: task.triggers.map((trigger) => ({ ...trigger, enabled: true })),
          })
        }
      }
      // Other dispatch/handler completions may have replaced this.registry
      // while the asset was read above; re-read the record before mutating it.
      current = this.registry.tasks[taskId]
      if (current === undefined) throw new Error(`task deleted during toggle: ${taskId}`)
      previous = current.enabled
      current.enabled = action === 'enable'
      this.state.saveRegistry()
      this.runtime.reload()
    } catch (error) {
      current = this.registry.tasks[taskId]
      if (current !== undefined) {
        current.enabled = previous
        this.state.saveRegistry()
      }
      if (originalTriggers !== undefined) {
        try {
          const task = await readTaskAsset(this.root, taskId)
          await writeTaskMeta(join(this.root, 'ops', taskId), {
            manifest: task.manifest,
            agensMd: task.agensMd,
            triggers: originalTriggers,
          })
        } catch {
          // Restoration is best effort; the original error is reported below.
        }
      }
      try {
        this.runtime.reload()
      } catch {
        // The atomic engine rebuild keeps the previous index on failure.
      }
      this.logError('trigger toggle rejected', {
        taskId,
        error: error instanceof Error ? error.message : String(error),
      })
      sendJson(res, 400, { ok: false, error: error instanceof Error ? error.message : String(error) })
      return
    }
    sendJson(res, 200, { ok: true, task: current })
  }

  private async handleWebhook(req: IncomingMessage, res: ServerResponse): Promise<void> {
    if (!this.requireMethod(req, res, 'POST')) return
    const pathname = new URL(req.url ?? '', 'http://localhost').pathname
    const triggerId = pathname.slice(`${ROUTE_BASE}/webhook/`.length)
    if (triggerId === '' || triggerId.includes('/')) {
      sendJson(res, 404, { ok: false, error: 'expected /webhook/<triggerId>' })
      return
    }
    const chunks: Buffer[] = []
    let size = 0
    for await (const chunk of req as AsyncIterable<Buffer>) {
      size += chunk.length
      if (size > 1024 * 1024) {
        sendJson(res, 413, { ok: false, error: 'request body too large' })
        return
      }
      chunks.push(chunk)
    }
    const body = Buffer.concat(chunks).toString('utf8')
    const headers = req.headers as Record<string, string | string[] | undefined>
    let dispatched = false
    try {
      dispatched = await this.runtime.webhook(triggerId, pathname, headers, body)
    } catch (error) {
      this.logError('webhook trigger failed', {
        triggerId,
        error: error instanceof Error ? error.message : String(error),
      })
      sendJson(res, 500, { ok: false, error: 'webhook trigger failed' })
      return
    }
    if (!dispatched) {
      sendJson(res, 404, { ok: false, error: 'no matching webhook trigger' })
      return
    }
    sendJson(res, 200, { ok: true })
  }

  private requireMethod(req: IncomingMessage, res: ServerResponse, method: string): boolean {
    if (req.method === method || (method === 'GET' && req.method === 'HEAD')) return true
    sendJson(res, 405, { ok: false, error: 'method not allowed' })
    return false
  }
}

/**
 * Wire the host plugin into a dsh composition. Equivalent to
 * `ctx.plugin(MaintainAllService, config)`.
 */
export function apply(ctx: Context, config: MaintainAllConfig = {}): void {
  ctx.plugin(MaintainAllService, config)
}

export default MaintainAllService
