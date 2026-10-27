/**
 * Run workspace materialization.
 *
 * Each replayed run gets a fresh working directory under
 * `ops/<task-id>/runs/<timestamp>-<runid>/` so the replayed agent can write
 * freely without touching the task asset or earlier runs. Task-local files
 * (`AGENTS.md`, `.agents/skills/`, `scripts/`) are copied — never symlinked —
 * into the run cwd so a run is self-contained and safe to archive. An empty
 * `.agents/skills/` is not copied: it carries no skill, and omitting it keeps
 * the run cwd from becoming an empty skill project root for dsh's watcher.
 *
 * Pure node built-ins only; no dsh imports.
 */

import { randomBytes } from 'node:crypto'
import { existsSync, readdirSync } from 'node:fs'
import { cp, mkdir, rm } from 'node:fs/promises'
import { join } from 'node:path'

/** Files/directories copied from the task asset into every run cwd. */
const RUN_CWD_ENTRIES: readonly string[] = ['AGENTS.md', join('.agents', 'skills'), 'scripts']

/** Two-digit padding for the timestamp components. */
function pad2(value: number): string {
  return String(value).padStart(2, '0')
}

/** Filesystem-safe local-time timestamp: `YYYYMMDD-HHMMSS`. */
export function runTimestamp(now: Date): string {
  const date = `${now.getFullYear()}${pad2(now.getMonth() + 1)}${pad2(now.getDate())}`
  const time = `${pad2(now.getHours())}${pad2(now.getMinutes())}${pad2(now.getSeconds())}`
  return `${date}-${time}`
}

/**
 * Create a fresh run cwd for `taskId` under the plugin data `root`:
 * `ops/<task-id>/runs/<ts>-<runid>/`, then copy the task's `AGENTS.md`,
 * `.agents/skills/`, and `scripts/` into it when present. Copies dereference
 * symlinks, so the run cwd never contains links back into the task asset.
 *
 * @param root - plugin data root (the directory holding `ops/`).
 * @param taskId - task whose asset directory provides the copied entries.
 * @param now - run start instant; injectable for deterministic tests.
 * @returns the absolute path of the new run cwd.
 */
export async function createRunCwd(root: string, taskId: string, now = new Date()): Promise<string> {
  const taskDir = join(root, 'ops', taskId)
  const runId = randomBytes(4).toString('hex')
  const runCwd = join(taskDir, 'runs', `${runTimestamp(now)}-${runId}`)
  try {
    await mkdir(runCwd, { recursive: true })

    for (const entry of RUN_CWD_ENTRIES) {
      const source = join(taskDir, entry)
      if (!existsSync(source)) continue
      if (entry === join('.agents', 'skills') && readdirSync(source).length === 0) continue
      await cp(source, join(runCwd, entry), {
        recursive: true,
        // Copy through symlinks: the run cwd owns plain files, never links.
        dereference: true,
        verbatimSymlinks: false,
      })
    }
    return runCwd
  } catch (error) {
    await rm(runCwd, { recursive: true, force: true }).catch(() => {})
    throw error
  }
}
