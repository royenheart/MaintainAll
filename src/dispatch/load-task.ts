/**
 * Task asset loading for dispatch.
 *
 * Reads the materialized task directory (`ops/<task-id>/`) and returns the
 * pieces `dispatchReplay` needs: the parsed manifest and the compact seed.
 * No dsh imports; path and fs are Node builtins.
 */

import { closeSync, existsSync, fstatSync, openSync, readFileSync, readSync } from 'node:fs'
import { join } from 'node:path'
import type { SeedEvent, TaskManifest, TaskSeed } from '../core/contract.ts'
import { assertTaskId, parseManifest } from '../core/manifest.ts'
import { MAX_EVENT_COUNT, MAX_SEED_BYTES, validateSeedBounds } from '../core/seed.ts'

/** A materialized task asset ready for dispatch. */
export interface LoadedTask {
  manifest: TaskManifest
  seed?: TaskSeed
}

/**
 * Read `seed/session.jsonl`: the first line is the session header carrying
 * the seed cwd; remaining lines are durable seed events with contiguous seq.
 * The reader is intentionally strict — a malformed seed fails dispatch.
 */
export function parseSeedFile(text: string): TaskSeed {
  if (Buffer.byteLength(text, 'utf8') > MAX_SEED_BYTES) throw new Error('seed file is too large')
  const lines = text.split(/\r?\n/).filter((line) => line.trim() !== '')
  if (lines.length === 0) throw new Error('seed file is empty')
  const header = JSON.parse(lines[0]) as { type?: string; cwd?: unknown }
  if (header.type !== 'session' || typeof header.cwd !== 'string' || header.cwd.trim() === '') {
    throw new Error('seed file must start with a session header containing cwd')
  }
  if (lines.length - 1 > MAX_EVENT_COUNT) throw new Error('seed file has too many events')
  const rawEvents = lines.slice(1).map((line) => JSON.parse(line) as SeedEvent)
  for (let index = 1; index < rawEvents.length; index += 1) {
    const previous = rawEvents[index - 1]
    const current = rawEvents[index]
    // Durable-only seeds naturally skip non-durable events (chunks, runtime
    // context snapshots, notices), so gaps are expected; only reject a
    // sequence that is not strictly increasing.
    if (previous === undefined || current === undefined || current.seq <= previous.seq) {
      throw new Error(`seed event seq is not strictly increasing at line ${index + 2}`)
    }
  }
  // Session replay expects a seed contiguous from seq 0, so normalize the
  // durable-only sequence after accepting its gaps.
  const events = rawEvents.map((event, index) => ({ ...event, seq: index }))
  const seed = { cwd: header.cwd, events }
  validateSeedBounds(seed)
  return seed
}

/** Load one task asset from the plugin data root. */
export function loadTask(root: string, taskId: string): LoadedTask {
  assertTaskId(taskId)
  const taskDir = join(root, 'ops', taskId)
  const manifest = parseManifest(readFileSync(join(taskDir, 'manifest.yml'), 'utf8'))
  const seedPath = join(taskDir, 'seed', 'session.jsonl')
  let seed: TaskSeed | undefined
  if (existsSync(seedPath)) {
    const fd = openSync(seedPath, 'r')
    try {
      const size = fstatSync(fd).size
      if (size > MAX_SEED_BYTES) throw new Error('seed file is too large')
      const buffer = Buffer.alloc(size)
      let offset = 0
      while (offset < size) {
        const bytesRead = readSync(fd, buffer, offset, size - offset, offset)
        if (bytesRead === 0) throw new Error('seed file changed while reading')
        offset += bytesRead
      }
      seed = parseSeedFile(buffer.toString('utf8'))
    } finally {
      closeSync(fd)
    }
  }
  return { manifest, seed }
}
