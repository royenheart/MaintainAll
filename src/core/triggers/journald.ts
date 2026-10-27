/**
 * journald JSON stream parsing and source-native filtering.
 *
 * Pure functions over the lines produced by `journalctl -o json`; the host
 * owns the subprocess. Nothing here performs IO.
 */

export interface JournalEntry {
  unit?: string
  priority?: number
  message?: string
  /** RFC 3339 instant derived from `__REALTIME_TIMESTAMP`, when present. */
  timestamp?: string
}

export interface JournalFilter {
  /** Exact `_SYSTEMD_UNIT` match. */
  unit?: string
  /** Matches entries with priority <= this value (lower = more severe). */
  priority?: number
  /** Regex tested against the message. */
  regex?: string
}

const REGEX_CACHE = new Map<string, RegExp>()
const MAX_CACHE_ENTRIES = 256

function regexFor(pattern: string): RegExp {
  const cached = REGEX_CACHE.get(pattern)
  if (cached !== undefined) return cached
  const compiled = new RegExp(pattern)
  if (REGEX_CACHE.size >= MAX_CACHE_ENTRIES) REGEX_CACHE.clear()
  REGEX_CACHE.set(pattern, compiled)
  return compiled
}

/** Parse one line of `journalctl -o json` output. Returns null when malformed. */
export function parseJournalJsonLine(line: string): JournalEntry | null {
  let value: unknown
  try {
    value = JSON.parse(line)
  } catch {
    return null
  }
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return null
  }
  const raw = value as Record<string, unknown>
  const entry: JournalEntry = {}
  if (typeof raw._SYSTEMD_UNIT === 'string') {
    entry.unit = raw._SYSTEMD_UNIT
  }
  if (typeof raw.PRIORITY === 'string' || typeof raw.PRIORITY === 'number') {
    const priority = Number(raw.PRIORITY)
    if (Number.isInteger(priority)) {
      entry.priority = priority
    }
  }
  if (typeof raw.MESSAGE === 'string') {
    entry.message = raw.MESSAGE
  }
  if (typeof raw.__REALTIME_TIMESTAMP === 'string' || typeof raw.__REALTIME_TIMESTAMP === 'number') {
    const micros = Number(raw.__REALTIME_TIMESTAMP)
    if (Number.isFinite(micros)) {
      entry.timestamp = new Date(micros / 1000).toISOString()
    }
  }
  return entry
}

/**
 * Source-native journald filter. All present clauses must pass. `priority`
 * matches entries at least as severe as the threshold (priority <= filter).
 */
export function filterJournalEntry(entry: JournalEntry, filter: JournalFilter): boolean {
  if (filter.unit !== undefined && entry.unit !== filter.unit) {
    return false
  }
  if (filter.priority !== undefined) {
    if (entry.priority === undefined || entry.priority > filter.priority) {
      return false
    }
  }
  if (filter.regex !== undefined) {
    if (entry.message === undefined || !regexFor(filter.regex).test(entry.message)) {
      return false
    }
  }
  return true
}
