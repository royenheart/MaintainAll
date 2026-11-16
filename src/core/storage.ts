/**
 * Plugin data root resolution and atomically written JSON state files.
 * Pure node built-ins only; no dsh imports.
 */

import { homedir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import {
  existsSync,
  mkdirSync,
  openSync,
  closeSync,
  fsyncSync,
  readFileSync,
  renameSync,
  writeFileSync,
} from 'node:fs'
import type { RegistryState, RunMapState, TaskRegistryRecord, TriggerState } from './contract.ts'
import { assertTaskId } from './manifest.ts'

/** Package-scoped directory name under the dsh home. */
const PLUGIN_DIR = join('@royenheart', 'dsh-plugin-maintainall')

/**
 * Plugin data root: `$DSH_HOME/@royenheart/dsh-plugin-maintainall` when
 * `DSH_HOME` is set, otherwise `~/.dsh/@royenheart/dsh-plugin-maintainall`.
 */
export function pluginDataRoot(env: NodeJS.ProcessEnv = process.env): string {
  const raw = env.DSH_HOME
  const configured = raw !== undefined && raw.trim() !== '' ? raw : undefined
  const base = configured === undefined
    ? join(homedir(), '.dsh')
    : configured === '~'
      ? homedir()
      : configured.startsWith('~/') || configured.startsWith('~\\')
        ? join(homedir(), configured.slice(2))
        : configured
  return join(resolve(base), PLUGIN_DIR)
}

/**
 * A JSON file written atomically: content goes to a tmp file in the same
 * directory, is fsynced, then renamed over the target. Directories are
 * created with mode 0o700 and files with mode 0o600.
 */
export class AtomicJsonFile<T> {
  readonly path: string

  constructor(path: string) {
    this.path = path
  }

  /**
   * Read and parse the file. Returns `undefined` when the file does not
   * exist; throws a descriptive error when the content is not valid JSON.
   */
  read(): T | undefined {
    if (!existsSync(this.path)) return undefined
    const text = readFileSync(this.path, 'utf8')
    try {
      return JSON.parse(text) as T
    } catch (cause) {
      throw new Error(`corrupted JSON state file: ${this.path}`, { cause })
    }
  }

  /** Serialize `value` and atomically replace the file. */
  write(value: T): void {
    const dir = dirname(this.path)
    mkdirSync(dir, { recursive: true, mode: 0o700 })
    const tmp = `${this.path}.tmp-${process.pid}-${Math.random().toString(36).slice(2)}`
    writeFileSync(tmp, JSON.stringify(value, null, 2), { mode: 0o600 })
    const fd = openSync(tmp, 'r')
    try {
      fsyncSync(fd)
    } finally {
      closeSync(fd)
    }
    renameSync(tmp, this.path)
  }
}

function stateFile<S extends { version: number }>(root: string, name: string, defaults: S) {
  const file = new AtomicJsonFile<S>(join(root, 'storages', name))
  return {
    load(): S {
      const state = file.read()
      return state === undefined ? { ...defaults } : { ...defaults, ...state }
    },
    save(state: S): void {
      file.write(state)
    },
  }
}

const registry = (root: string) =>
  stateFile<RegistryState>(root, 'registry.json', { version: 1, tasks: {} })

const trigger = (root: string) =>
  stateFile<TriggerState>(root, 'trigger-state.json', {
    version: 2,
    triggers: {},
    schedules: {},
    filewatch: {},
    exec: {},
  })

const runMap = (root: string) =>
  stateFile<RunMapState>(root, 'run-map.json', { version: 1, runs: {} })

/** Load `storages/registry.json`, dropping retired fields from older files. */
export function loadRegistryState(root: string): RegistryState {
  const state = registry(root).load() as RegistryState & Record<string, unknown>
  const tasks: Record<string, TaskRegistryRecord> = {}
  for (const [id, value] of Object.entries(state.tasks ?? {})) {
    try {
      assertTaskId(id)
    } catch {
      continue
    }
    if (typeof value !== 'object' || value === null || Array.isArray(value)) continue
    const raw = value as Partial<TaskRegistryRecord>
    if (
      typeof raw.name !== 'string'
      || typeof raw.version !== 'string'
      || typeof raw.enabled !== 'boolean'
      || typeof raw.importedAt !== 'string'
    ) continue
    tasks[id] = {
      id,
      name: raw.name,
      version: raw.version,
      enabled: raw.enabled,
      importedAt: raw.importedAt,
      ...(typeof raw.lastRunAt === 'string' ? { lastRunAt: raw.lastRunAt } : {}),
      ...(typeof raw.icon === 'string' ? { icon: raw.icon } : {}),
      ...(typeof raw.color === 'string' ? { color: raw.color } : {}),
    }
  }
  return { version: 1, tasks }
}

/** Atomically persist `storages/registry.json`. */
export function saveRegistryState(root: string, state: RegistryState): void {
  registry(root).save(state)
}

/** Keep only structurally valid per-trigger filewatch offsets. */
function sanitizeFilewatch(value: unknown): TriggerState['filewatch'] {
  const result: TriggerState['filewatch'] = {}
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return result
  for (const [triggerId, paths] of Object.entries(value)) {
    if (typeof paths !== 'object' || paths === null || Array.isArray(paths)) continue
    const valid: Record<string, { offset: number; inode?: number }> = {}
    for (const [path, raw] of Object.entries(paths)) {
      if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) continue
      const state = raw as Record<string, unknown>
      if (typeof state.offset !== 'number' || !Number.isSafeInteger(state.offset) || state.offset < 0) continue
      valid[path] = {
        offset: state.offset,
        ...(typeof state.inode === 'number' && Number.isFinite(state.inode)
          ? { inode: state.inode }
          : {}),
      }
    }
    if (Object.keys(valid).length > 0) result[triggerId] = valid
  }
  return result
}

/** Load `storages/trigger-state.json`, migrating legacy v1 filewatch state. */
export function loadTriggerState(root: string): TriggerState {
  const state = trigger(root).load() as TriggerState & { version?: number }
  const section = (value: unknown): Record<string, unknown> =>
    typeof value === 'object' && value !== null && !Array.isArray(value)
      ? value as Record<string, unknown>
      : {}
  if (state.version === 2) {
    return {
      version: 2,
      triggers: section(state.triggers) as TriggerState['triggers'],
      schedules: section(state.schedules) as TriggerState['schedules'],
      filewatch: sanitizeFilewatch(state.filewatch),
      exec: section(state.exec) as TriggerState['exec'],
    }
  }
  // v1 keyed filewatch offsets by path, so they cannot be attached to a
  // trigger id safely. Drop only that legacy section; the next poll baselines.
  return {
    version: 2,
    triggers: section(state.triggers) as TriggerState['triggers'],
    schedules: section(state.schedules) as TriggerState['schedules'],
    filewatch: {},
    exec: section(state.exec) as TriggerState['exec'],
  }
}

/** Atomically persist `storages/trigger-state.json`. */
export function saveTriggerState(root: string, state: TriggerState): void {
  trigger(root).save(state)
}

/** Load `storages/run-map.json`, falling back to defaults when absent. */
export function loadRunMapState(root: string): RunMapState {
  return runMap(root).load()
}

/** Atomically persist `storages/run-map.json`. */
export function saveRunMapState(root: string, state: RunMapState): void {
  runMap(root).save(state)
}
