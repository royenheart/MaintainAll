/**
 * Task asset writing and reading under `ops/<task-id>/`.
 * Pure node built-ins plus `yaml`; no dsh imports.
 *
 * Layout per task:
 * ```
 * ops/<task-id>/
 * ├── manifest.yml
 * ├── AGENTS.md
 * ├── .agents/skills/...
 * ├── scripts/...
 * ├── seed/session.jsonl
 * ├── triggers.yml
 * └── runs/
 * ```
 */

import { randomUUID } from 'node:crypto'
import { existsSync } from 'node:fs'
import { mkdir, open, readFile, readdir, rename, rm } from 'node:fs/promises'
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path'
import { parse as parseYaml, stringify } from 'yaml'
import { normalizeTriggerFilter } from './triggers/normalize.ts'
import type { SeedEvent, TaskManifest, TaskSeed, TaskTrigger } from './contract.ts'
import { assertTaskId, parseManifest, validateManifest } from './manifest.ts'
import { MAX_EVENT_COUNT, MAX_SEED_BYTES, validateSeedBounds, validateSeedCwd } from './seed.ts'

/** In-memory form of one task asset. */
export interface TaskAssetInput {
  manifest: TaskManifest
  /** Contents of `AGENTS.md`. */
  agensMd: string
  /** Task-relative paths (`.agents/skills/<name>/SKILL.md`) to file contents. */
  skills: Map<string, string>
  /** Task-relative paths (`scripts/<file>`) to file contents. */
  scripts: Map<string, string>
  /** Replay seed; absent for `taskMode: 'fresh'` tasks. */
  seed?: TaskSeed | null
  triggers: TaskTrigger[]
}

/**
 * Write a file atomically: content goes to a tmp file in the same directory,
 * is fsynced, then renamed over the target. Parent directories are created
 * with mode 0o700 and the file with mode 0o600.
 */
export async function writeFileAtomic(path: string, content: string | Uint8Array): Promise<void> {
  await mkdir(dirname(path), { recursive: true, mode: 0o700 })
  const tmp = `${path}.tmp-${process.pid}-${Math.random().toString(36).slice(2)}`
  try {
    const handle = await open(tmp, 'w', 0o600)
    try {
      await handle.writeFile(content)
      await handle.sync()
    } finally {
      await handle.close()
    }
    await rename(tmp, path)
  } catch (err) {
    await rm(tmp, { force: true })
    throw err
  }
}

/** Read a seed-sized file through one handle so the cap applies to the bytes actually read. */
async function readSeedFile(path: string): Promise<string> {
  const handle = await open(path, 'r')
  try {
    const size = (await handle.stat()).size
    if (size > MAX_SEED_BYTES) throw new Error('invalid seed: seed is too large')
    const buffer = Buffer.alloc(size)
    let offset = 0
    while (offset < size) {
      const { bytesRead } = await handle.read(buffer, offset, size - offset, offset)
      if (bytesRead === 0) throw new Error('invalid seed: seed file changed while reading')
      offset += bytesRead
    }
    return buffer.toString('utf8')
  } finally {
    await handle.close()
  }
}

/** Serialize a seed to `seed/session.jsonl` text: session header, then one JSON event per line. */
export function serializeSeed(seed: TaskSeed): string {
  validateSeedCwd(seed.cwd)
  if (seed.events.length > MAX_EVENT_COUNT) throw new Error('invalid seed: too many events')
  const lines = [JSON.stringify({ type: 'session', cwd: seed.cwd })]
  for (const event of seed.events) lines.push(JSON.stringify(event))
  const text = lines.join('\n') + '\n'
  if (Buffer.byteLength(text, 'utf8') > MAX_SEED_BYTES) throw new Error('invalid seed: seed is too large')
  return text
}

/** Parse `seed/session.jsonl` text back into a {@link TaskSeed}. Throws on malformed input. */
export function parseSeed(text: string): TaskSeed {
  if (Buffer.byteLength(text, 'utf8') > MAX_SEED_BYTES) throw new Error('invalid seed: seed is too large')
  const lines = text.split('\n').filter((line) => line.trim() !== '')
  if (lines.length === 0) throw new Error('invalid seed: session.jsonl is empty')
  let header: unknown
  try {
    header = JSON.parse(lines[0])
  } catch (cause) {
    throw new Error('invalid seed: first line is not valid JSON', { cause })
  }
  const h = header as Record<string, unknown>
  if (typeof h !== 'object' || h === null || h.type !== 'session' || typeof h.cwd !== 'string' || h.cwd.trim() === '') {
    throw new Error('invalid seed: first line must be {"type":"session","cwd":...} with a non-empty cwd')
  }
  const events: SeedEvent[] = lines.slice(1).map((line, index) => {
    try {
      return JSON.parse(line) as SeedEvent
    } catch (cause) {
      throw new Error(`invalid seed: line ${index + 2} is not valid JSON`, { cause })
    }
  })
  const seed = { cwd: h.cwd, events }
  validateSeedBounds(seed)
  return seed
}

/** Serialize trigger declarations to `triggers.yml` text. */
export function serializeTriggers(triggers: TaskTrigger[]): string {
  return stringify({ triggers: triggers.map(normalizeTriggerFilter) })
}

/** Parse `triggers.yml` text into trigger declarations. Throws on malformed input. */
export function parseTriggers(text: string): TaskTrigger[] {
  const doc: unknown = parseYaml(text)
  if (doc === undefined || doc === null) return []
  if (typeof doc !== 'object' || Array.isArray(doc)) {
    throw new Error('invalid triggers.yml: must be a mapping')
  }
  const list = (doc as Record<string, unknown>).triggers
  if (list === undefined || list === null) return []
  if (!Array.isArray(list)) {
    throw new Error('invalid triggers.yml: triggers must be an array')
  }
  return list.map((item, index) => {
    const t = item as Record<string, unknown>
    if (typeof t !== 'object' || t === null || Array.isArray(t)) {
      throw new Error(`invalid triggers.yml: trigger ${index} must be a mapping`)
    }
    if (typeof t.id !== 'string' || t.id === '') {
      throw new Error(`invalid triggers.yml: trigger ${index} needs a non-empty id`)
    }
    if (typeof t.source !== 'string') {
      throw new Error(`invalid triggers.yml: trigger ${JSON.stringify(t.id)} needs a source`)
    }
    if (typeof t.enabled !== 'boolean') {
      throw new Error(`invalid triggers.yml: trigger ${JSON.stringify(t.id)} needs enabled: boolean`)
    }
    return t as unknown as TaskTrigger
  })
}

/** Resolve a task-relative path, rejecting anything that escapes `taskDir`. */
function resolveUnder(taskDir: string, rel: string): string {
  const abs = resolve(taskDir, rel)
  const contained = relative(taskDir, abs)
  if (contained === '' || contained === '..' || contained.startsWith('..' + sep) || isAbsolute(contained)) {
    throw new Error(`unsafe task asset path: ${JSON.stringify(rel)}`)
  }
  return abs
}

/** Validate an asset subtree before any file is written. */
function validateAssetEntries(
  taskDir: string,
  prefix: string,
  entries: Map<string, string>,
): Array<[string, string]> {
  const result: Array<[string, string]> = []
  for (const [rel, content] of entries) {
    if (rel.includes('\\') || !rel.startsWith(prefix)) {
      throw new Error(`unsafe task asset path: ${JSON.stringify(rel)}`)
    }
    const segments = rel.slice(prefix.length).split('/')
    if (segments.some((segment) => segment === '' || segment === '.' || segment === '..')) {
      throw new Error(`unsafe task asset path: ${JSON.stringify(rel)}`)
    }
    result.push([resolveUnder(taskDir, rel), content])
  }
  return result
}

/**
 * Write every file of a task asset into `taskDir` (atomically, tmp + rename).
 * Creates `.agents/skills/`, `scripts/`, `seed/`, and `runs/` even when empty.
 */
export async function writeTaskDir(taskDir: string, input: TaskAssetInput): Promise<void> {
  assertTaskId(input.manifest.id)
  const skills = validateAssetEntries(taskDir, '.agents/skills/', input.skills)
  const scripts = validateAssetEntries(taskDir, 'scripts/', input.scripts)
  await mkdir(join(taskDir, '.agents', 'skills'), { recursive: true, mode: 0o700 })
  await mkdir(join(taskDir, 'scripts'), { recursive: true, mode: 0o700 })
  await mkdir(join(taskDir, 'seed'), { recursive: true, mode: 0o700 })
  await mkdir(join(taskDir, 'runs'), { recursive: true, mode: 0o700 })

  await writeFileAtomic(join(taskDir, 'manifest.yml'), stringify(input.manifest))
  await writeFileAtomic(join(taskDir, 'AGENTS.md'), input.agensMd)
  for (const [path, content] of skills) {
    await writeFileAtomic(path, content)
  }
  for (const [path, content] of scripts) {
    await writeFileAtomic(path, content)
  }
  if (input.seed !== undefined && input.seed !== null) {
    if (input.seed.cwd.trim() === '') throw new Error('seed cwd must be non-empty')
    await writeFileAtomic(join(taskDir, 'seed', 'session.jsonl'), serializeSeed(input.seed))
  }
  await writeFileAtomic(join(taskDir, 'triggers.yml'), serializeTriggers(input.triggers))
}

/**
 * Write only the metadata files of a task asset (`manifest.yml`,
 * `AGENTS.md`, and `triggers.yml`). The seed, skills, scripts, and runs
 * directories are left untouched, so edits never replace a captured replay
 * trajectory with the editing session's events.
 */
export async function writeTaskMeta(
  taskDir: string,
  input: Pick<TaskAssetInput, 'manifest' | 'agensMd' | 'triggers'>,
): Promise<void> {
  assertTaskId(input.manifest.id)
  const manifest = validateManifest(input.manifest)
  await mkdir(taskDir, { recursive: true, mode: 0o700 })
  await writeFileAtomic(join(taskDir, 'manifest.yml'), stringify(manifest))
  await writeFileAtomic(join(taskDir, 'AGENTS.md'), input.agensMd)
  await writeFileAtomic(join(taskDir, 'triggers.yml'), serializeTriggers(input.triggers))
}

/**
 * Create `ops/<task-id>/` under `root` and write the task asset into it.
 * The manifest is validated first; returns the task directory path.
 */
export async function writeTaskAsset(root: string, input: TaskAssetInput): Promise<string> {
  assertTaskId(input.manifest.id)
  const manifest = validateManifest(input.manifest)
  const taskDir = join(root, 'ops', manifest.id)
  const opsDir = join(root, 'ops')
  await mkdir(opsDir, { recursive: true, mode: 0o700 })
  const tempDir = join(opsDir, `.tmp-${randomUUID()}`)
  try {
    await writeTaskDir(tempDir, { ...input, manifest })
    // rename is the commit point: an existing non-empty target fails instead
    // of being deleted and partially overwritten.
    await rename(tempDir, taskDir)
  } catch (error) {
    await rm(tempDir, { recursive: true, force: true })
    throw error
  }
  return taskDir
}

/** Recursively collect files under `taskDir/<prefix>` keyed by task-relative posix path. */
async function readTree(taskDir: string, prefix: string): Promise<Map<string, string>> {
  const out = new Map<string, string>()
  const walk = async (dir: string): Promise<void> => {
    let entries
    try {
      entries = await readdir(dir, { withFileTypes: true })
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code === 'ENOENT') return
      throw err
    }
    for (const entry of entries) {
      const abs = join(dir, entry.name)
      if (entry.isDirectory()) {
        await walk(abs)
      } else if (entry.isFile()) {
        out.set(relative(taskDir, abs).split(sep).join('/'), await readFile(abs, 'utf8'))
      }
    }
  }
  await walk(join(taskDir, prefix))
  return out
}

/** Read the task asset at `ops/<taskId>/` under `root` back into memory. */
export async function readTaskAsset(root: string, taskId: string): Promise<TaskAssetInput> {
  assertTaskId(taskId)
  const taskDir = join(root, 'ops', taskId)
  const manifest = parseManifest(await readFile(join(taskDir, 'manifest.yml'), 'utf8'))
  const agensMd = await readFile(join(taskDir, 'AGENTS.md'), 'utf8')
  const skills = await readTree(taskDir, join('.agents', 'skills'))
  const scripts = await readTree(taskDir, 'scripts')
  const seedPath = join(taskDir, 'seed', 'session.jsonl')
  const seed = existsSync(seedPath) ? parseSeed(await readSeedFile(seedPath)) : undefined
  const triggers = parseTriggers(await readFile(join(taskDir, 'triggers.yml'), 'utf8'))
    .map(normalizeTriggerFilter)
  return { manifest, agensMd, skills, scripts, seed, triggers }
}

/** Sorted task ids (directory names) under `ops/`; empty when `ops/` does not exist. */
export async function listTaskAssets(root: string): Promise<string[]> {
  const opsDir = join(root, 'ops')
  if (!existsSync(opsDir)) return []
  const entries = await readdir(opsDir, { withFileTypes: true })
  return entries
    .filter((entry) => entry.isDirectory() && !entry.name.startsWith('.'))
    .map((entry) => entry.name)
    .sort()
}
