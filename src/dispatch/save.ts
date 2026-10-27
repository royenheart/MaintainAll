/**
 * Save pipeline: materialize a save request into a task asset.
 *
 * The materialize path reads the session's durable events up to `boundarySeq`,
 * cuts the replay seed, builds the manifest from `meta`, and writes the task
 * directory. The model-driven extraction of
 * skills/scripts/AGENTS.md is intentionally left out of this pass; callers
 * may supply those files in `meta` directly. No dsh imports.
 */

import { existsSync } from 'node:fs'
import { rm } from 'node:fs/promises'
import { TASK_TRIGGER_SOURCES } from '../core/contract.ts'
import { join } from 'node:path'
import type { SeedEvent, TaskManifest, TaskMode, TaskTrigger } from '../core/contract.ts'
import { compactSeedEvents, extractSeedEvents, validateSeedCwd } from '../core/seed.ts'
import { readTaskAsset, writeTaskAsset, writeTaskMeta } from '../core/task-writer.ts'
import { loadRegistryState, saveRegistryState } from '../core/storage.ts'
import { normalizeTriggerFilter } from '../core/triggers/normalize.ts'
import { validateCel } from '../core/triggers/condition.ts'
import { firstScheduledAt, parseScheduleRule } from '../core/triggers/schedule-time.ts'

/** Minimal session face needed by the save pipeline. */
export interface SaveSessionFace {
  readonly id: string
  readonly header: { readonly cwd?: string }
  /** dsh Session snapshot API; `events` is not a Session member. */
  snapshotEvents(): ReadonlyArray<{ readonly type: string; readonly seq: number; readonly data?: unknown }>
}

/** Minimal session store face needed by the save pipeline. */
export interface SaveSessionsFace {
  get(id: string): SaveSessionFace | undefined
}

/** Fields the Save dialog collects and posts in `meta`. */
export interface SaveTaskMeta {
  id: string
  name: string
  description: string
  version?: string
  instructions?: string
  triggers: TaskTrigger[]
  skills?: Record<string, string>
  scripts?: Record<string, string>
  agentPresetHint?: string
  permissionPresetHint?: string
  taskMode?: TaskMode
  icon?: string
  color?: string
  naturalPrompt?: string
}

const TASK_TRIGGER_SOURCE_SET = new Set<string>(TASK_TRIGGER_SOURCES)
const WEBHOOK_TRIGGER_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/
const RESERVED_TRIGGER_IDS = new Set([
  '__proto__', 'prototype', 'constructor', 'toString', 'toLocaleString', 'valueOf',
  'hasOwnProperty', 'isPrototypeOf', 'propertyIsEnumerable',
  '__defineGetter__', '__defineSetter__', '__lookupGetter__', '__lookupSetter__',
])

/** Reject a trigger set the engine could not index or arm. */
export function validateTaskTriggers(triggers: readonly TaskTrigger[]): void {
  const ids = new Set<string>()
  for (const trigger of triggers) {
    if (typeof trigger.id !== 'string' || trigger.id.trim() === '' || RESERVED_TRIGGER_IDS.has(trigger.id)
      || /[\0\r\n]/.test(trigger.id)) {
      throw new Error('trigger id must be a non-empty string and must not be reserved')
    }
    if (trigger.source === 'webhook' && !WEBHOOK_TRIGGER_ID_RE.test(trigger.id)) {
      throw new Error(`webhook trigger id must match ${WEBHOOK_TRIGGER_ID_RE.source}`)
    }
    if (ids.has(trigger.id)) throw new Error(`duplicate trigger id: ${trigger.id}`)
    ids.add(trigger.id)
    if (!TASK_TRIGGER_SOURCE_SET.has(trigger.source)) {
      throw new Error(`trigger ${trigger.id}: unsupported source '${String(trigger.source)}'`)
    }
    if (typeof trigger.enabled !== 'boolean') {
      throw new Error(`trigger ${trigger.id}: enabled must be a boolean`)
    }
    if (trigger.filter !== undefined && (typeof trigger.filter !== 'object' || trigger.filter === null || Array.isArray(trigger.filter))) {
      throw new Error(`trigger ${trigger.id}: filter must be an object`)
    }
    const filter = (trigger.filter ?? {}) as Record<string, unknown>
    if (trigger.source === 'filewatch' && (typeof filter.path !== 'string' || filter.path.trim() === '')) {
      throw new Error(`trigger ${trigger.id}: filewatch filter.path must be a non-empty string`)
    }
    if (trigger.source === 'exec' && (typeof filter.command !== 'string' || filter.command.trim() === '')) {
      throw new Error(`trigger ${trigger.id}: exec filter.command must be a non-empty string`)
    }
    if (trigger.source === 'docker') {
      if (filter.container !== undefined && (typeof filter.container !== 'string' || filter.container === '')) {
        throw new Error(`trigger ${trigger.id}: docker filter.container must be a non-empty string`)
      }
      if (filter.events !== undefined
        && (!Array.isArray(filter.events)
          || filter.events.some((event) => typeof event !== 'string' || event === ''))) {
        throw new Error(`trigger ${trigger.id}: docker filter.events must be an array of non-empty strings`)
      }
    }
    if (trigger.source === 'webhook') {
      if (filter.path !== undefined && typeof filter.path !== 'string') {
        throw new Error(`trigger ${trigger.id}: webhook filter.path must be a string`)
      }
      if (typeof filter.token !== 'string' || filter.token === '') {
        throw new Error(`trigger ${trigger.id}: webhook filter.token must be a non-empty string`)
      }
    }
    if (trigger.when !== undefined && typeof trigger.when !== 'string') {
      throw new Error(`trigger ${trigger.id}: when must be a string`)
    }
    try {
      validateCel(trigger.when)
    } catch (error) {
      throw new Error(`trigger ${trigger.id}: invalid when: ${error instanceof Error ? error.message : String(error)}`)
    }
    if ((trigger.source === 'filewatch' || trigger.source === 'journald')
      && typeof filter.regex === 'string' && filter.regex !== '') {
      try {
        new RegExp(filter.regex)
      } catch (error) {
        throw new Error(`trigger ${trigger.id}: invalid filter.regex: ${error instanceof Error ? error.message : String(error)}`)
      }
    }
    if (trigger.rate !== undefined) {
      const rate = trigger.rate
      if (typeof rate !== 'object' || rate === null || Array.isArray(rate)
        || typeof rate.minIntervalSeconds !== 'number'
        || !Number.isFinite(rate.minIntervalSeconds) || rate.minIntervalSeconds < 0
        || typeof rate.maxPerHour !== 'number'
        || !Number.isFinite(rate.maxPerHour) || rate.maxPerHour < 0) {
        throw new Error(`trigger ${trigger.id}: rate must contain non-negative numeric minIntervalSeconds/maxPerHour`)
      }
    }
    if (trigger.source !== 'schedule') continue
    try {
      const rule = parseScheduleRule(trigger.params)
      firstScheduledAt(rule, Date.now())
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      throw new Error(`trigger ${trigger.id}: ${message}`)
    }
  }
}

/** Validate and normalize `meta` into a `TaskManifest`. */
export function manifestFromMeta(meta: SaveTaskMeta): TaskManifest {
  if (!/^[a-z0-9][a-z0-9-]*$/.test(meta.id)) {
    throw new Error(`invalid task id: ${meta.id}`)
  }
  if (meta.name.trim() === '') throw new Error('task name must not be empty')
  if (meta.taskMode === 'auto') throw new Error('auto is a request mode; choose safe-copy, compact, or fresh')
  return {
    format: 'dsh-opskit/1',
    id: meta.id,
    name: meta.name,
    description: meta.description,
    version: meta.version ?? '0.1.0',
    ...(meta.taskMode === undefined ? {} : { taskMode: meta.taskMode }),
    ...(meta.icon === undefined ? {} : { icon: meta.icon }),
    ...(meta.color === undefined ? {} : { color: meta.color }),
    ...(meta.naturalPrompt === undefined ? {} : { naturalPrompt: meta.naturalPrompt }),
    ...(meta.agentPresetHint !== undefined || meta.permissionPresetHint !== undefined
      ? {
          bindings: {
            ...(meta.agentPresetHint !== undefined ? { agentPreset: { hint: meta.agentPresetHint } } : {}),
            ...(meta.permissionPresetHint !== undefined
              ? { permissionPreset: { hint: meta.permissionPresetHint } }
              : {}),
          },
        }
      : {}),
  }
}

/** Cut the replay seed from a session's durable events. */
export function seedFromSession(session: SaveSessionFace, boundarySeq: number): { cwd: string; events: SeedEvent[] } {
  const cwd = validateSeedCwd(session.header.cwd)
  const events = extractSeedEvents(
    session.snapshotEvents().map((event) => ({ type: event.type, seq: event.seq, data: event.data })),
    boundarySeq,
  )
  return { cwd, events }
}

/**
 * Materialize one pending save request into `ops/<task-id>/`.
 * The task registry is updated and persisted. Returns the task directory.
 */
export async function materializeTaskFromSave(
  root: string,
  sessions: SaveSessionsFace,
  request: { sessionId: string; boundarySeq: number; meta: SaveTaskMeta },
): Promise<string> {
  const session = sessions.get(request.sessionId)
  if (session === undefined) throw new Error(`unknown session: ${request.sessionId}`)
  const taskMode = request.meta.taskMode ?? 'safe-copy'
  if (taskMode === 'auto') throw new Error('auto is a request mode; choose safe-copy, compact, or fresh')
  const rawSeed = taskMode === 'fresh'
    ? undefined
    : seedFromSession(session, request.boundarySeq)
  const seed = rawSeed === undefined || taskMode !== 'compact'
    ? rawSeed
    : { cwd: rawSeed.cwd, events: compactSeedEvents(rawSeed.events) }
  const triggers = request.meta.triggers.map(normalizeTriggerFilter)
  validateTaskTriggers(triggers)
  const manifest = manifestFromMeta(request.meta)
  if (existsSync(join(root, 'ops', manifest.id))) {
    throw new Error(`task already exists: ${manifest.id}; edit it instead of materializing a new asset`)
  }
  const taskDir = await writeTaskAsset(root, {
    manifest,
    agensMd: request.meta.instructions ?? defaultAgentsMd(manifest),
    skills: request.meta.skills === undefined ? new Map() : new Map(Object.entries(request.meta.skills)),
    scripts: request.meta.scripts === undefined ? new Map() : new Map(Object.entries(request.meta.scripts)),
    seed,
    triggers,
  })
  const registry = loadRegistryState(root)
  registry.tasks[manifest.id] = {
    id: manifest.id,
    name: manifest.name,
    version: manifest.version,
    enabled: triggers.some((trigger) => trigger.enabled),
    importedAt: new Date().toISOString(),
    ...(manifest.icon === undefined ? {} : { icon: manifest.icon }),
    ...(manifest.color === undefined ? {} : { color: manifest.color }),
  }
  try {
    saveRegistryState(root, registry)
  } catch (error) {
    await rm(taskDir, { recursive: true, force: true })
    throw error
  }
  return taskDir
}

/** Fields a manual task edit may update. `taskMode` and the seed are not
 * editable: the replay trajectory is captured once at creation time and is
 * only replaced when the task is deleted and re-created from a real session.
 */
export interface EditTaskMeta {
  name: string
  description: string
  instructions?: string
  triggers?: TaskTrigger[]
  icon?: string
  color?: string
  naturalPrompt?: string
}

/**
 * Apply a manual edit to an existing task asset. Only the metadata files are
 * rewritten; `seed/`, `.agents/skills/`, `scripts/`, and `runs/` are kept.
 * The registry record is updated (name/icon/color/enabled) and persisted.
 */
export async function materializeTaskEdit(
  root: string,
  taskId: string,
  meta: EditTaskMeta,
): Promise<string> {
  const triggers = meta.triggers?.map(normalizeTriggerFilter)
  if (triggers !== undefined) validateTaskTriggers(triggers)
  const existing = await readTaskAsset(root, taskId)
  // Rebuild the manifest from the fields that survive an edit. `checksums`
  // describe the imported zip and must not stay stale after files change.
  const manifest: TaskManifest = {
    format: existing.manifest.format,
    id: taskId,
    name: meta.name,
    description: meta.description,
    version: existing.manifest.version,
    ...(existing.manifest.taskMode === undefined ? {} : { taskMode: existing.manifest.taskMode }),
    ...(meta.icon === undefined
      ? (existing.manifest.icon === undefined ? {} : { icon: existing.manifest.icon })
      : { icon: meta.icon }),
    ...(meta.color === undefined
      ? (existing.manifest.color === undefined ? {} : { color: existing.manifest.color })
      : { color: meta.color }),
    ...(meta.naturalPrompt === undefined
      ? (existing.manifest.naturalPrompt === undefined ? {} : { naturalPrompt: existing.manifest.naturalPrompt })
      : { naturalPrompt: meta.naturalPrompt }),
    ...(existing.manifest.requires === undefined ? {} : { requires: existing.manifest.requires }),
    ...(existing.manifest.bindings === undefined ? {} : { bindings: existing.manifest.bindings }),
  }
  const taskDir = join(root, 'ops', taskId)
  await writeTaskMeta(taskDir, {
    manifest,
    agensMd: meta.instructions ?? existing.agensMd,
    triggers: triggers ?? existing.triggers,
  })
  try {
    const registry = loadRegistryState(root)
  const previous = registry.tasks[taskId]
  registry.tasks[taskId] = {
    id: taskId,
    name: manifest.name,
    version: manifest.version,
    enabled: previous?.enabled ?? (triggers ?? existing.triggers).some((trigger) => trigger.enabled),
    importedAt: previous?.importedAt ?? new Date().toISOString(),
    ...(previous?.lastRunAt === undefined ? {} : { lastRunAt: previous.lastRunAt }),
    ...(manifest.icon === undefined ? {} : { icon: manifest.icon }),
    ...(manifest.color === undefined ? {} : { color: manifest.color }),
  }
    saveRegistryState(root, registry)
  } catch (error) {
    await writeTaskMeta(taskDir, {
      manifest: existing.manifest,
      agensMd: existing.agensMd,
      triggers: existing.triggers,
    })
    throw error
  }
  return taskDir
}

function defaultAgentsMd(manifest: TaskManifest): string {
  return [
    `# ${manifest.name}`,
    '',
    manifest.description,
    '',
    '## Execution',
    '',
    'Follow the replay seed context and complete the requested ops task.',
    'Report what you did, what you changed, and any follow-up the user should know.',
    '',
  ].join('\n')
}
