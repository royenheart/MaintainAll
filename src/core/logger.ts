/**
 * Plugin-owned JSONL logger with size-based rotation and bounded retention.
 *
 * Logs are plain `maintainall.log` files under the plugin's `storages/logs`
 * directory. The logger is deliberately dependency-free so `src/core` tests
 * exercise it directly. Writes are synchronous append — the plugin's log
 * volume is low and the UI must be able to read the file immediately after a
 * route handles an error.
 */

import {
  appendFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  renameSync,
  statSync,
  unlinkSync,
} from 'node:fs'
import { join } from 'node:path'

export type PluginLogLevel = 'info' | 'warn' | 'error'

/** One parsed log record. */
export interface PluginLogEntry {
  ts: string
  level: PluginLogLevel
  msg: string
}

/** Result of a lazy-log read. */
export interface PluginLogPage {
  /** Newest-first entries for the requested page. */
  entries: PluginLogEntry[]
  /** True when older entries remain after this page. */
  hasMore: boolean
}

/** Rotation/retention defaults: 1 MiB per file, at most 8 archived files. */
export const DEFAULT_LOG_MAX_BYTES = 1024 * 1024
export const DEFAULT_LOG_MAX_FILES = 8

/** Base name of the live log file. */
export const LOG_FILE_NAME = 'maintainall.log'

/**
 * Append-only JSONL logger for the plugin.
 *
 * The live file is `maintainall.log`. On size overflow it is renamed to
 * `maintainall-<epoch-ms>.log` and a new live file starts. Startup cleanup
 * removes the oldest archived files beyond `maxFiles`.
 */
export class PluginLogger {
  private readonly dir: string
  private readonly maxBytes: number
  private readonly maxFiles: number

  constructor(dir: string, maxBytes: number = DEFAULT_LOG_MAX_BYTES, maxFiles: number = DEFAULT_LOG_MAX_FILES) {
    this.dir = dir
    this.maxBytes = maxBytes
    this.maxFiles = maxFiles
    mkdirSync(dir, { recursive: true, mode: 0o700 })
    this.cleanup()
  }

  private file(): string {
    return join(this.dir, LOG_FILE_NAME)
  }

  /** Append one record and rotate when the live file exceeds the cap. */
  private write(level: PluginLogLevel, msg: string): void {
    const record = JSON.stringify({ ts: new Date().toISOString(), level, msg })
    appendFileSync(this.file(), record + '\n', { encoding: 'utf8' })
    this.rotateIfNeeded()
  }

  info(msg: string): void {
    this.write('info', msg)
  }

  warn(msg: string): void {
    this.write('warn', msg)
  }

  error(msg: string): void {
    this.write('error', msg)
  }

  /**
   * Read one page of logs, newest first.
   * @param limit - maximum entries to return.
   * @param offset - number of newest entries already fetched.
   */
  read(limit = 200, offset = 0): PluginLogPage {
    const live = this.file()
    const archives = readdirSync(this.dir)
      .filter((name) => name.startsWith('maintainall-') && name.endsWith('.log'))
      .sort()
    const files = [...archives.map((name) => join(this.dir, name)), live]
    const lines = files.flatMap((file) =>
      existsSync(file)
        ? readFileSync(file, 'utf8').split('\n').filter((line) => line.trim() !== '')
        : [])

    const total = lines.length
    const start = Math.max(0, total - offset - limit)
    const end = Math.max(0, total - offset)
    const entries = lines.slice(start, end).reverse().flatMap((line) => {
      try {
        const parsed = JSON.parse(line) as { ts?: unknown; level?: unknown; msg?: unknown }
        if (typeof parsed.ts !== 'string' || typeof parsed.msg !== 'string') return []
        const level: PluginLogLevel = parsed.level === 'warn'
          ? 'warn'
          : parsed.level === 'error' ? 'error' : 'info'
        return [{ ts: parsed.ts, level, msg: parsed.msg }]
      } catch {
        return []
      }
    })
    return { entries, hasMore: start > 0 }
  }

  /** Rename the live file when it outgrows the cap and prune old archives. */
  private rotateIfNeeded(): void {
    let size = 0
    try {
      size = statSync(this.file()).size
    } catch {
      return
    }
    if (size <= this.maxBytes) return
    const archived = join(this.dir, `maintainall-${Date.now()}.log`)
    try {
      renameSync(this.file(), archived)
    } catch {
      return
    }
    this.cleanup()
  }

  /** Delete the oldest archived logs beyond `maxFiles`. */
  private cleanup(): void {
    const archives = readdirSync(this.dir)
      .filter((name) => name.startsWith('maintainall-') && name.endsWith('.log'))
      .sort()
    while (archives.length > this.maxFiles) {
      const oldest = archives.shift()
      if (oldest === undefined) break
      try {
        unlinkSync(join(this.dir, oldest))
      } catch {
        // Retention is best-effort; a locked archive survives one pass.
      }
    }
  }
}
