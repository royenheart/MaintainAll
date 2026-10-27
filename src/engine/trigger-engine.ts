/**
 * Host-facing trigger engine lifecycle.
 *
 * The engine is dependency-free (node built-ins plus `src/core/` only, no dsh
 * imports): the host feeds it source observations — timer ticks, docker event
 * lines, journald lines, webhook requests — and it runs the deterministic
 * trigger pipeline for each enabled task trigger:
 *
 *   source-native filter -> CEL `when` -> debounce/rate limit -> dispatch
 *
 * Dispatch is injected, so tests fake it and the host wires session creation.
 * The LLM never participates in the trigger decision. Runtime state (rate
 * limits, filewatch offsets, exec observations) persists to
 * `storages/trigger-state.json` under `opts.root` via `src/engine/state.ts`.
 *
 * Trigger field conventions (`TaskTrigger.filter` / `TaskTrigger.params`):
 * - schedule: exactly one of `params.cron` (string with optional
 *   `time_zone`/`timezoneOffsetMinutes`, or `{ expression, time_zone }`),
 *   `params.at`, `params.afterSeconds`, `params.everySeconds`,
 *   `params.daily`, or `params.weekly`. New rules use an explicit IANA zone;
 *   the committed target persists in `trigger-state.json`.
 * - filewatch: `filter.path` (file, or directory when `filter.glob` is set,
 *   resolved against `opts.root` when relative), `filter.glob` (`*` glob over
 *   relative paths), `filter.recursive` (walk subdirectories), `filter.regex`
 *   (line filter)
 * - docker: `filter.events`, `filter.container`
 * - journald: `filter.unit`, `filter.priority`, `filter.regex`
 * - webhook: `filter.path` (full request pathname; omit to match any path
 *   for the trigger id), `filter.token`
 * - exec: `filter.command`; the host runs it through a bounded subprocess
 */

import { readdirSync } from 'node:fs'
import { open, stat } from 'node:fs/promises'
import { join, relative, resolve, sep } from 'node:path'

/** Closed engine lifecycle state. */
export type EnginePhase = 'idle' | 'running' | 'stopped'

/** One serialized timer/source lane. */
type TickSource = 'schedule' | 'filewatch' | 'exec'

const DRAIN_TIMEOUT_MS = 5000

import type { ScheduleTriggerState, TaskTrigger, TriggerEvent, TriggerState } from '../core/contract.ts'
import { normalizeEvent } from '../core/triggers/event.ts'
import { evaluateCel } from '../core/triggers/condition.ts'
import {
  parseScheduleRule,
  scheduleEventPayload,
  scheduleRuleKey,
  type ScheduleRule,
} from '../core/triggers/schedule-time.ts'
import { FileWatchPoller, type FileWatchIO } from '../core/triggers/filewatch.ts'
import {
  parseDockerEvent,
  filterDockerEvent,
  toTriggerEvent,
  globToRegExp,
  type DockerEventFilter,
} from '../core/triggers/docker.ts'
import {
  parseJournalJsonLine,
  filterJournalEntry,
  type JournalFilter,
} from '../core/triggers/journald.ts'
import { verifyWebhookToken, parseWebhookBody } from '../core/triggers/webhook.ts'
import { ExecEdgeDetector } from '../core/triggers/exec.ts'
import { RateLimiter, rateStateOf, withRateState } from '../core/triggers/rate.ts'
import { pureScheduleTime, type ScheduleTime } from './schedule-time.ts'
import {
  loadTriggerStateFile,
  saveTriggerStateFile,
} from './state.ts'

/** One task as the engine sees it: an id plus its declared triggers. */
export interface EngineTask {
  taskId: string
  triggers: TaskTrigger[]
}

/** Injected dispatch sink; called only after a trigger fully fires. */
export interface TriggerDispatch {
  (taskId: string, event: TriggerEvent): Promise<void>
}

/** Injectable interval scheduler; defaults to the global timers. */
export interface EngineScheduler {
  setInterval(fn: () => void, ms: number): NodeJS.Timeout | number
  clearInterval(handle: NodeJS.Timeout | number): void
}

/** Result of one exec-source command run. */
export interface ExecResult {
  stdout: string
  stderr: string
  exitCode: number
}

/** Injected exec runner; the host owns the actual subprocess. */
export interface ExecRunner {
  (command: string): Promise<ExecResult>
}

export interface TriggerEngineOptions {
  /** Plugin data root; state persists to `<root>/storages/trigger-state.json`. */
  root: string
  /** Re-read on every `reload()`; must return the current enabled tasks. */
  tasks: () => EngineTask[]
  dispatch: TriggerDispatch
  now?: () => Date
  scheduler?: EngineScheduler
  /** Required for exec triggers to fire; without it exec ticks are no-ops. */
  exec?: ExecRunner
  /** Filewatch IO override; defaults to the real filesystem. */
  filewatchIo?: FileWatchIO
  /** Poll interval for filewatch/exec ticks, in milliseconds. */
  pollIntervalMs?: number
  /** Fire-time resolver override; defaults to the pure core. */
  scheduleTime?: ScheduleTime
  /** Report a background-tick failure instead of leaving a rejected promise. */
  onError?: (error: Error) => void
}

const DEFAULT_POLL_INTERVAL_MS = 5000
const SCHEDULE_TICK_MS = 1000

const defaultScheduler: EngineScheduler = {
  setInterval: (fn, ms) => setInterval(fn, ms),
  clearInterval: (handle) => clearInterval(handle as NodeJS.Timeout),
}

const defaultFilewatchIo: FileWatchIO = {
  async stat(path) {
    const s = await stat(path)
    return { size: s.size, mtimeMs: s.mtimeMs, inode: s.ino }
  },
  async read(path, start) {
    const handle = await open(path, 'r')
    try {
      const info = await handle.stat()
      if (info.size <= start) return { text: '', bytes: 0 }
      const length = info.size - start
      const buffer = Buffer.allocUnsafe(length)
      let read = 0
      while (read < length) {
        const { bytesRead } = await handle.read(buffer, read, length - read, start + read)
        if (bytesRead === 0) break
        read += bytesRead
      }
      const raw = buffer.subarray(0, read)
      const lastNewline = raw.lastIndexOf(0x0a)
      if (lastNewline < 0) return { text: '', bytes: 0 }
      const complete = raw.subarray(0, lastNewline + 1)
      return { text: complete.toString('utf8'), bytes: complete.length }
    } finally {
      await handle.close()
    }
  },
}

interface TriggerEntry {
  taskId: string
  trigger: TaskTrigger
}

interface ScheduleEntry {
  entry: TriggerEntry
  rule: ScheduleRule
  /** State object owned by this entry; never re-read by trigger id after reload. */
  state: ScheduleTriggerState
  /** Epoch milliseconds of the committed fire instant. */
  next: number
  /** One-shot already fired, or a recurring rule has no future target. */
  done: boolean
}

interface FilewatchEntry {
  entry: TriggerEntry
  /** One poller per watched absolute path. */
  pollers: Map<string, FileWatchPoller>
  /** Paths that already completed their baseline (first) poll. */
  primed: Set<string>
}

export class TriggerEngine {
  private readonly root: string
  private readonly tasksFn: () => EngineTask[]
  private readonly dispatchFn: TriggerDispatch
  private readonly nowFn: () => Date
  private readonly scheduler: EngineScheduler
  private readonly execRunner?: ExecRunner
  private readonly filewatchIo: FileWatchIO
  private readonly scheduleTime: ScheduleTime
  private readonly onError: (error: Error) => void
  /** Poll interval for filewatch/exec ticks, in milliseconds. */
  readonly pollIntervalMs: number

  private state: TriggerState
  private index = new Map<string, TriggerEntry>()
  private schedule: ScheduleEntry[] = []
  private filewatches: FilewatchEntry[] = []
  private execDetectors = new Map<string, ExecEdgeDetector>()
  private built = false
  private phase: EnginePhase = 'idle'
  private generation = 0
  private readonly triggerEpochs = new Map<string, number>()
  private readonly inFlight = new Map<TickSource, Promise<void>>()
  private readonly scheduleInFlight = new Map<string, Promise<boolean>>()
  private handles: Array<NodeJS.Timeout | number> = []

  constructor(opts: TriggerEngineOptions) {
    this.root = opts.root
    this.tasksFn = opts.tasks
    this.dispatchFn = opts.dispatch
    this.nowFn = opts.now ?? (() => new Date())
    this.scheduler = opts.scheduler ?? defaultScheduler
    if (opts.exec !== undefined) this.execRunner = opts.exec
    this.filewatchIo = opts.filewatchIo ?? defaultFilewatchIo
    this.scheduleTime = opts.scheduleTime ?? pureScheduleTime
    this.onError = opts.onError ?? ((error) => { console.error('[maintainall] trigger engine:', error) })
    this.pollIntervalMs = opts.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS
    this.state = loadTriggerStateFile(this.root)
  }

  /**
   * Arm the schedule tick (1s) and the filewatch/exec poll ticks
   * (`pollIntervalMs`) through the injected scheduler, and (re)build all
   * listener state from the current tasks.
   */
  async start(): Promise<void> {
    if (this.phase === 'running') return
    this.phase = 'running'
    this.generation += 1
    try {
      this.rebuild()
    } catch (error) {
      this.phase = 'idle'
      throw error
    }
    const runExclusive = (source: 'filewatch' | 'exec', tick: () => Promise<void>): void => {
      if (this.phase !== 'running' || this.inFlight.has(source)) return
      const task = tick()
        .catch((error: unknown) => {
          this.onError(error instanceof Error ? error : new Error(String(error)))
        })
        .finally(() => {
          if (this.inFlight.get(source) === task) this.inFlight.delete(source)
        })
      this.inFlight.set(source, task)
    }
    const runSchedule = (): void => {
      if (this.phase !== 'running') return
      void this.onScheduleTick().catch((error: unknown) => {
        this.onError(error instanceof Error ? error : new Error(String(error)))
      })
    }
    this.handles.push(
      this.scheduler.setInterval(runSchedule, SCHEDULE_TICK_MS),
      this.scheduler.setInterval(() => runExclusive('filewatch', () => this.onFilewatchTick()), this.pollIntervalMs),
      this.scheduler.setInterval(() => runExclusive('exec', () => this.onExecTick()), this.pollIntervalMs),
    )
  }

  /** Clear every armed interval, drain in-flight ticks, and flush state. */
  async stop(): Promise<void> {
    if (this.phase === 'stopped') return
    this.phase = 'stopped'
    this.generation += 1
    for (const handle of this.handles) {
      this.scheduler.clearInterval(handle)
    }
    this.handles = []
    const pending = [...this.inFlight.values(), ...this.scheduleInFlight.values()]
    if (pending.length > 0) {
      let timer: NodeJS.Timeout | undefined
      await Promise.race([
        Promise.allSettled(pending),
        new Promise<void>((resolve) => {
          timer = setTimeout(resolve, DRAIN_TIMEOUT_MS)
          timer.unref?.()
        }),
      ])
      if (timer !== undefined) clearTimeout(timer)
    }
    // If a filewatch batch is still in flight, the new offset has not been
    // committed. Keep the previous persisted offset so the next poll/start
    // re-reads that batch (at-least-once) instead of dropping it.
    if (!this.inFlight.has('filewatch')) this.persist()
  }

  /** Re-read tasks and rebuild listener state (schedule map, pollers). */
  reload(): void {
    if (this.phase !== 'running') return
    const previousGeneration = this.generation
    this.generation += 1
    try {
      this.rebuild()
    } catch (error) {
      // A failed rebuild leaves the old pollers/index in place; restore the
      // epoch so an in-flight tick can still finish and commit its batch.
      this.generation = previousGeneration
      throw error
    }
  }

  /** Trigger ids currently indexed for one task, including enabled-only entries. */
  triggerIdsForTask(taskId: string): string[] {
    return [...this.index.values()]
      .filter((entry) => entry.taskId === taskId)
      .map((entry) => entry.trigger.id)
  }

  /** Drop persisted runtime state for triggers that no longer exist. */
  forgetTriggers(triggerIds: readonly string[]): void {
    if (triggerIds.length === 0) return
    const removed = new Set(triggerIds)
    let changed = false
    for (const triggerId of removed) {
      this.triggerEpochs.set(triggerId, (this.triggerEpochs.get(triggerId) ?? 0) + 1)
      if (this.index.delete(triggerId)) changed = true
      this.execDetectors.delete(triggerId)
      if (delete this.state.schedules[triggerId]) changed = true
      if (delete this.state.triggers[triggerId]) changed = true
      if (delete this.state.filewatch[triggerId]) changed = true
      if (delete this.state.exec[triggerId]) changed = true
    }
    // Remove runtime entries immediately so a tick started before a later
    // reload cannot dispatch the removed trigger. Do not bump generation:
    // unrelated in-flight ticks must be allowed to commit their batches.
    this.schedule = this.schedule.filter((item) => !removed.has(item.entry.trigger.id))
    this.filewatches = this.filewatches.filter((watch) => !removed.has(watch.entry.trigger.id))
    if (changed) this.persist()
  }

  /**
   * Fire every schedule trigger whose committed target is due at `now`.
   *
   * A recurring rule fires once with the committed target even when the Host
   * was down through several occurrences, then advances strictly past `now`.
   * Advancing and persisting happen before dispatch so a crash cannot re-arm
   * the same occurrence inside the tick.
   */
  async onScheduleTick(now: Date = this.nowFn()): Promise<void> {
    if (this.phase !== 'running') return
    this.ensureBuilt()
    const nowMs = now.getTime()
    const generation = this.generation
    for (const item of this.schedule) {
      if (this.phase !== 'running' || generation !== this.generation) return
      if (item.done) continue
      if (item.next > nowMs) continue
      if (!this.index.has(item.entry.trigger.id)) continue
      if (this.scheduleInFlight.has(item.entry.trigger.id)) continue
      const occurrenceAt = new Date(item.next).toISOString()
      let nextIso: string | undefined
      try {
        if (item.rule.kind === 'every') {
          // Preserve the committed cadence across a late tick instead of
          // re-anchoring the interval to the tick time.
          const interval = item.rule.everySeconds * 1000
          let next = item.next + interval
          while (next <= nowMs) next += interval
          nextIso = new Date(next).toISOString()
        } else {
          nextIso = this.scheduleTime.next(item.rule, nowMs)
        }
      } catch (error) {
        // A transient resolver failure must not consume a recurring trigger;
        // keep the committed target and retry on the next tick.
        this.onError(new Error(`schedule-target-error: ${error instanceof Error ? error.message : String(error)}`))
        continue
      }
      const state = item.state
      const previousNext = item.next
      const previousDone = item.done
      const previousScheduledAt = state.scheduledAt
      const previousStateDone = state.done
      if (nextIso === undefined) {
        item.done = true
        state.done = true
      } else {
        const nextMs = Date.parse(nextIso)
        if (!Number.isFinite(nextMs) || nextMs <= item.next || nextMs <= nowMs) {
          this.onError(new Error(`schedule-target-error: invalid next target ${JSON.stringify(nextIso)}`))
          continue
        }
        item.next = nextMs
        state.scheduledAt = nextIso
      }
      try {
        this.persist()
      } catch (error) {
        item.next = previousNext
        item.done = previousDone
        state.scheduledAt = previousScheduledAt
        state.done = previousStateDone
        throw error
      }
      if (this.phase !== 'running' || generation !== this.generation) return
      const triggerId = item.entry.trigger.id
      const event = normalizeEvent('schedule', occurrenceAt, scheduleEventPayload(item.rule))
      const dispatch = this.accept(item.entry.taskId, item.entry.trigger, event)
        .catch((error: unknown) => {
          this.onError(error instanceof Error ? error : new Error(String(error)))
          return false
        })
      this.scheduleInFlight.set(triggerId, dispatch)
      try {
        await dispatch
      } finally {
        if (this.scheduleInFlight.get(triggerId) === dispatch) this.scheduleInFlight.delete(triggerId)
      }
    }
  }

  /** Poll every filewatch trigger once, emitting events for new lines. */
  async onFilewatchTick(now: Date = this.nowFn()): Promise<void> {
    if (this.phase !== 'running') return
    this.ensureBuilt()
    const generation = this.generation
    for (const watch of this.filewatches) {
      try {
        const filter = (watch.entry.trigger.filter ?? {}) as Record<string, unknown>
        const triggerId = watch.entry.trigger.id
        if (!this.index.has(triggerId)) continue
        const triggerEpoch = this.triggerEpochs.get(triggerId) ?? 0
        for (const path of this.resolveWatchPaths(filter)) {
          if (!this.index.has(triggerId)) continue
          const poller = this.pollerFor(watch, path)
          const result = watch.primed.has(path)
            ? await poller.poll(path)
            : await poller.prime(path)
          if (
            this.phase !== 'running'
            || generation !== this.generation
            || !this.index.has(triggerId)
            || (this.triggerEpochs.get(triggerId) ?? 0) !== triggerEpoch
          ) return
          if (!watch.primed.has(path)) {
            // Baseline poll: adopt the current end of file without emitting
            // historical lines.
            this.commitFilewatchOffset(triggerId, path, result)
            watch.primed.add(path)
            continue
          }
          for (const line of result.lines) {
            if (
              this.phase !== 'running'
              || generation !== this.generation
              || !this.index.has(triggerId)
              || (this.triggerEpochs.get(triggerId) ?? 0) !== triggerEpoch
            ) return
            const event = normalizeEvent('filewatch', now.toISOString(), { path, line })
            try {
              await this.accept(watch.entry.taskId, watch.entry.trigger, event)
            } catch (error) {
              this.onError(error instanceof Error ? error : new Error(String(error)))
            }
          }
          if (
            this.phase !== 'running'
            || generation !== this.generation
            || !this.index.has(triggerId)
            || (this.triggerEpochs.get(triggerId) ?? 0) !== triggerEpoch
          ) return
          // Commit only after every line was offered to accept(). A rate-state
          // persist during dispatch must not publish an offset for unprocessed
          // lines; crash/reload before this point re-reads the batch.
          this.commitFilewatchOffset(triggerId, path, result)
        }
      } catch (error) {
        this.onError(error instanceof Error ? error : new Error(String(error)))
      }
    }
    if (this.phase !== 'running' || generation !== this.generation) return
    this.persist()
  }

  /** Run each exec trigger's command once and fire on detected edges. */
  async onExecTick(now: Date = this.nowFn()): Promise<void> {
    if (this.phase !== 'running') return
    this.ensureBuilt()
    if (this.execRunner === undefined) return
    const generation = this.generation
    for (const entry of this.index.values()) {
      if (this.phase !== 'running' || generation !== this.generation) return
      if (entry.trigger.source !== 'exec') continue
      const triggerId = entry.trigger.id
      const triggerEpoch = this.triggerEpochs.get(triggerId) ?? 0
      const command = entry.trigger.filter?.command
      if (typeof command !== 'string' || command === '') continue
      try {
        const result = await this.execRunner(command)
        if (
          this.phase !== 'running'
          || generation !== this.generation
          || !this.index.has(triggerId)
          || (this.triggerEpochs.get(triggerId) ?? 0) !== triggerEpoch
        ) return
        const detector = this.execDetectorFor(entry.trigger.id)
        const edge = detector.update(result.stdout, result.stderr, result.exitCode, now)
        this.state.exec[entry.trigger.id] = {
          stdout: result.stdout,
          stderr: result.stderr,
          exitCode: result.exitCode,
        }
        this.persist()
        if (!edge) continue
        const event = normalizeEvent('exec', now.toISOString(), {
          command,
          stdout: result.stdout,
          stderr: result.stderr,
          exitCode: result.exitCode,
        })
        await this.accept(entry.taskId, entry.trigger, event)
      } catch (error) {
        this.onError(error instanceof Error ? error : new Error(String(error)))
      }
    }
  }

  /** Feed one JSON line of `docker events` output to all docker triggers. */
  async onDockerEvent(line: string): Promise<void> {
    if (this.phase !== 'running') return
    this.ensureBuilt()
    const raw = parseDockerEvent(line)
    if (raw === null) return
    const occurredAt =
      typeof raw.time === 'number' && Number.isFinite(raw.time)
        ? new Date(raw.time * 1000).toISOString()
        : this.nowFn().toISOString()
    const generation = this.generation
    for (const entry of this.index.values()) {
      if (this.phase !== 'running' || generation !== this.generation) return
      if (entry.trigger.source !== 'docker') continue
      const filter = (entry.trigger.filter ?? {}) as DockerEventFilter
      try {
        if (!filterDockerEvent(raw, filter)) continue
        await this.accept(entry.taskId, entry.trigger, toTriggerEvent(raw, occurredAt))
      } catch (error) {
        this.onError(error instanceof Error ? error : new Error(String(error)))
      }
    }
  }

  /** Feed one line of `journalctl -o json` output to all journald triggers. */
  async onJournaldLine(line: string): Promise<void> {
    if (this.phase !== 'running') return
    this.ensureBuilt()
    const parsed = parseJournalJsonLine(line)
    if (parsed === null) return
    const occurredAt = parsed.timestamp ?? this.nowFn().toISOString()
    const generation = this.generation
    for (const entry of this.index.values()) {
      if (this.phase !== 'running' || generation !== this.generation) return
      if (entry.trigger.source !== 'journald') continue
      const filter = (entry.trigger.filter ?? {}) as JournalFilter
      try {
        if (!filterJournalEntry(parsed, filter)) continue
        const payload: Record<string, unknown> = {
          unit: parsed.unit,
          priority: parsed.priority,
          message: parsed.message,
        }
        for (const key of Object.keys(payload)) {
          if (payload[key] === undefined) delete payload[key]
        }
        await this.accept(entry.taskId, entry.trigger, normalizeEvent('journald', occurredAt, payload))
      } catch (error) {
        this.onError(error instanceof Error ? error : new Error(String(error)))
      }
    }
  }

  /**
   * Match an incoming webhook request against the named trigger. Returns
   * true exactly when the request matched path and token, passed the `when`
   * expression and rate limits, and was dispatched.
   */
  async onWebhookRequest(
    triggerId: string,
    path: string,
    headers: Record<string, string | string[] | undefined>,
    body: string,
  ): Promise<boolean> {
    if (this.phase !== 'running') return false
    this.ensureBuilt()
    if (this.phase !== 'running') return false
    const entry = this.index.get(triggerId)
    if (entry === undefined || entry.trigger.source !== 'webhook') return false
    const filter = (entry.trigger.filter ?? {}) as Record<string, unknown>
    if (typeof filter.path === 'string' && filter.path !== path) return false
    if (typeof filter.token !== 'string' || !verifyWebhookToken(headers, filter.token)) {
      return false
    }
    const event = normalizeEvent('webhook', this.nowFn().toISOString(), {
      path,
      body: parseWebhookBody(body),
    })
    return this.accept(entry.taskId, entry.trigger, event)
  }

  /**
   * Shared acceptance pipeline: CEL `when`, then debounce/rate limits, then
   * dispatch. Returns true when the event was dispatched. Rate state is
   * persisted before dispatch so a dispatch failure cannot re-arm the
   * trigger inside the debounce window.
   */
  private async accept(taskId: string, trigger: TaskTrigger, event: TriggerEvent): Promise<boolean> {
    if (this.phase !== 'running') return false
    if (!evaluateCel(trigger.when, event)) return false
    if (trigger.rate !== undefined) {
      const limiter = new RateLimiter(
        rateStateOf(this.state, trigger.id),
        trigger.rate,
        this.nowFn,
      )
      const decision = limiter.tryFire()
      if (!decision.allowed) return false
      withRateState(this.state, trigger.id, decision.state)
      this.persist()
    }
    await this.dispatchFn(taskId, event)
    return true
  }

  /** Rebuild the trigger index and all per-source runtime state. */
  private rebuild(): void {
    const nextIndex = new Map<string, TriggerEntry>()
    for (const task of this.tasksFn()) {
      for (const trigger of task.triggers) {
        if (!trigger.enabled) continue
        if (nextIndex.has(trigger.id)) {
          throw new Error(`duplicate trigger id: ${trigger.id}`)
        }
        nextIndex.set(trigger.id, { taskId: task.taskId, trigger })
      }
    }

    const nowMs = this.nowFn().getTime()
    const nextSchedules = new Map<string, ScheduleTriggerState>(Object.entries(this.state.schedules))
    const nextSchedule: ScheduleEntry[] = []
    const nextFilewatches: FilewatchEntry[] = []
    const nextExecDetectors = new Map<string, ExecEdgeDetector>()
    for (const entry of nextIndex.values()) {
      switch (entry.trigger.source) {
        case 'schedule': {
          let rule: ScheduleRule
          try {
            rule = parseScheduleRule(entry.trigger.params)
          } catch (error) {
            const message = error instanceof Error ? error.message : String(error)
            throw new Error(`schedule trigger ${entry.trigger.id}: ${message}`)
          }
          const ruleKey = scheduleRuleKey(rule)
          let state = this.state.schedules[entry.trigger.id]
          const storedNext = state === undefined || state.ruleKey !== ruleKey
            ? Number.NaN
            : Date.parse(state.scheduledAt)
          if (state === undefined || state.ruleKey !== ruleKey || !Number.isFinite(storedNext)) {
            let first: string
            try {
              first = this.scheduleTime.first(rule, nowMs)
            } catch (error) {
              const message = error instanceof Error ? error.message : String(error)
              throw new Error(`schedule trigger ${entry.trigger.id}: ${message}`)
            }
            state = { scheduledAt: first, ruleKey }
            nextSchedules.set(entry.trigger.id, state)
          } else {
            nextSchedules.set(entry.trigger.id, state)
          }
          nextSchedule.push({
            entry,
            rule,
            state,
            next: Date.parse(state.scheduledAt),
            done: state.done === true,
          })
          break
        }
        case 'filewatch':
          nextFilewatches.push({ entry, pollers: new Map(), primed: new Set() })
          break
        case 'exec':
          nextExecDetectors.set(
            entry.trigger.id,
            new ExecEdgeDetector(this.state.exec[entry.trigger.id]),
          )
          break
        default:
          break
      }
    }

    // Commit only after the complete task set parsed successfully; a bad
    // later trigger must not leave a partially rebuilt engine.
    const schedulesChanged = nextSchedules.size !== Object.keys(this.state.schedules).length
      || [...nextSchedules].some(([id, state]) => this.state.schedules[id] !== state)
    this.index = nextIndex
    this.schedule = nextSchedule
    this.filewatches = nextFilewatches
    this.execDetectors = nextExecDetectors
    this.state.schedules = Object.fromEntries(nextSchedules)
    if (schedulesChanged) this.persist()
    this.built = true
  }

  private ensureBuilt(): void {
    if (!this.built) this.rebuild()
  }

  /** Persist one filewatch offset after its batch was fully offered. */
  private commitFilewatchOffset(
    triggerId: string,
    path: string,
    result: { offset: number; inode?: number },
  ): void {
    const store = this.state.filewatch[triggerId] ?? {}
    store[path] = { offset: result.offset }
    if (result.inode !== undefined) store[path]!.inode = result.inode
    this.state.filewatch[triggerId] = store
  }

  /**
   * Resolve the absolute paths a filewatch trigger polls. Without `glob` the
   * (root-relative) `path` is the single watched file; with `glob`, `path`
   * is a base directory walked (recursively when `recursive` is set) and
   * every file whose relative path matches the glob is watched.
   */
  private resolveWatchPaths(filter: Record<string, unknown>): string[] {
    if (typeof filter.path !== 'string' || filter.path === '') return []
    const base = resolve(this.root, filter.path)
    if (typeof filter.glob !== 'string' || filter.glob === '') return [base]
    const matcher = globToRegExp(filter.glob)
    const recursive = filter.recursive === true
    return this.walk(base, recursive).filter((file) =>
      matcher.test(this.relativePosix(base, file)),
    )
  }

  private walk(dir: string, recursive: boolean): string[] {
    let entries
    try {
      entries = readdirSync(dir, { withFileTypes: true })
    } catch {
      return []
    }
    const out: string[] = []
    for (const entry of entries) {
      const full = join(dir, entry.name)
      if (entry.isDirectory()) {
        if (recursive) out.push(...this.walk(full, recursive))
      } else if (entry.isFile()) {
        out.push(full)
      }
    }
    return out
  }

  private relativePosix(base: string, file: string): string {
    const rel = relative(base, file)
    return sep === '/' ? rel : rel.split(sep).join('/')
  }

  /** Get or create the poller for one path, restoring persisted offsets. */
  private pollerFor(watch: FilewatchEntry, path: string): FileWatchPoller {
    const existing = watch.pollers.get(path)
    if (existing !== undefined) return existing
    const persisted = this.state.filewatch[watch.entry.trigger.id]?.[path]
    const poller = new FileWatchPoller(this.filewatchIo, {
      regex: typeof watch.entry.trigger.filter?.regex === 'string'
        ? watch.entry.trigger.filter.regex
        : undefined,
      initialOffset: persisted?.offset,
      initialInode: persisted?.inode,
    })
    if (persisted !== undefined) {
      // A persisted offset means the baseline already happened in a previous
      // engine lifetime; resume emitting immediately.
      watch.primed.add(path)
    }
    watch.pollers.set(path, poller)
    return poller
  }

  private execDetectorFor(triggerId: string): ExecEdgeDetector {
    const existing = this.execDetectors.get(triggerId)
    if (existing !== undefined) return existing
    const detector = new ExecEdgeDetector(this.state.exec[triggerId])
    this.execDetectors.set(triggerId, detector)
    return detector
  }

  private persist(): void {
    saveTriggerStateFile(this.root, this.state)
  }
}
