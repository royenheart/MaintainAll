/**
 * Schedule rule parsing and IANA-zone fire-time computation.
 *
 * A schedule trigger declares exactly one rule:
 *
 * - `cron`: five-field Vixie cron in an explicit IANA zone;
 * - `daily`: a local wall-clock time in an explicit IANA zone;
 * - `weekly`: a local wall-clock time and ISO weekday set in an IANA zone;
 * - `everySeconds`: a fixed interval of at least one minute;
 * - `afterSeconds`: a one-shot delay from the first observation;
 * - `at`: a one-shot absolute instant (RFC 3339 with an offset, or an exact
 *   local date/time object with a zone).
 *
 * The legacy `cron` string with `timezoneOffsetMinutes` stays supported as a
 * fixed-offset `cron-offset` rule so previously saved tasks keep firing. The
 * resolver follows dsh's schedule semantics: daily and weekly skip a local
 * time that does not exist and use the earlier instant for an ambiguous one;
 * a five-field cron field whose source starts with `*` is a star for the
 * day-of-month/day-of-week rule. Everything here is pure: no timers, no IO,
 * and no dsh imports, so the core can be unit-tested directly.
 */

import { CRON_SEARCH_DAYS, cronDayMatches, nextFire, parseCron, type ParsedCron } from './schedule.ts'

/** One normalized schedule rule. */
export type ScheduleRule =
  | { kind: 'cron'; expression: string; timeZone: string }
  | { kind: 'cron-offset'; expression: string; timezoneOffsetMinutes: number }
  | { kind: 'daily'; time: string; timeZone: string }
  | { kind: 'weekly'; time: string; timeZone: string; weekdays: number[] }
  | { kind: 'every'; everySeconds: number }
  | { kind: 'after'; afterSeconds: number }
  | { kind: 'at'; at: string }

/** Minimum fixed interval, matching dsh's schedule dialect. */
export const MIN_EVERY_SECONDS = 60

const DAY_MS = 86_400_000
/**
 * dsh walks the 400-year Gregorian cycle, the longest period after which a
 * five-field cron's date pattern repeats; the same bound applies here.
 */
const MAX_SEARCH_DAYS = CRON_SEARCH_DAYS

const AT_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?(?:Z|[+-]\d{2}:\d{2})$/
const DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/
const TIME_PATTERN = /^([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d)(?:\.(\d{1,3}))?)?$/

interface LocalParts {
  year: number
  month: number
  day: number
  hour: number
  minute: number
  second: number
}

interface LocalTime {
  hour: number
  minute: number
  second: number
  millisecond?: number
}

const formatterCache = new Map<string, Intl.DateTimeFormat>()

function formatterFor(timeZone: string): Intl.DateTimeFormat {
  const cached = formatterCache.get(timeZone)
  if (cached !== undefined) return cached
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone,
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
  formatterCache.set(timeZone, formatter)
  return formatter
}

function localPartsAt(instantMs: number, timeZone: string): LocalParts {
  const parts = formatterFor(timeZone).formatToParts(new Date(instantMs))
  let year = 0
  let month = 0
  let day = 0
  let hour = 0
  let minute = 0
  let second = 0
  for (const part of parts) {
    switch (part.type) {
      case 'year': year = Number(part.value); break
      case 'month': month = Number(part.value); break
      case 'day': day = Number(part.value); break
      case 'hour': hour = Number(part.value); break
      case 'minute': minute = Number(part.value); break
      case 'second': second = Number(part.value); break
      default: break
    }
  }
  // Some ICU builds render midnight as 24 with hourCycle h23; normalize it.
  if (hour === 24) hour = 0
  return { year, month, day, hour, minute, second }
}

/** Offset of `timeZone` at `instantMs`, in milliseconds east of UTC. */
function offsetAt(instantMs: number, timeZone: string): number {
  const parts = localPartsAt(instantMs, timeZone)
  const asUtc = Date.UTC(
    parts.year,
    parts.month - 1,
    parts.day,
    parts.hour,
    parts.minute,
    parts.second,
  )
  return asUtc - Math.floor(instantMs / 1000) * 1000
}

/**
 * Resolve one local wall-clock value in `timeZone` to a UTC instant.
 *
 * A value skipped by a forward transition returns `undefined`; an ambiguous
 * value from a backward transition returns the earlier instant. Both match
 * dsh's schedule semantics.
 */
function localToUtc(
  timeZone: string,
  year: number,
  month: number,
  day: number,
  time: LocalTime,
): number | undefined {
  const target = Date.UTC(year, month - 1, day, time.hour, time.minute, time.second, time.millisecond ?? 0)
  const offsets = new Set<number>()
  for (const delta of [0, -DAY_MS, DAY_MS, -2 * DAY_MS, 2 * DAY_MS]) {
    offsets.add(offsetAt(target + delta, timeZone))
  }
  // Re-sample at each candidate so a transition between the sampled days is
  // represented by both of its offsets. Snapshot first: adding to a Set during
  // iteration would also visit the newly added offsets.
  const initialOffsets = [...offsets]
  for (const offset of initialOffsets) {
    offsets.add(offsetAt(target - offset, timeZone))
  }
  const candidates: number[] = []
  for (const offset of offsets) {
    const candidate = target - offset
    const parts = localPartsAt(candidate, timeZone)
    if (
      parts.year === year
      && parts.month === month
      && parts.day === day
      && parts.hour === time.hour
      && parts.minute === time.minute
      && parts.second === time.second
    ) {
      candidates.push(candidate)
    }
  }
  if (candidates.length === 0) return undefined
  return Math.min(...candidates)
}

function localDateOf(instantMs: number, timeZone: string): { year: number; month: number; day: number } {
  const parts = localPartsAt(instantMs, timeZone)
  return { year: parts.year, month: parts.month, day: parts.day }
}

function addLocalDays(
  date: { year: number; month: number; day: number },
  offset: number,
): { year: number; month: number; day: number } {
  const shifted = new Date(Date.UTC(date.year, date.month - 1, date.day + offset))
  return {
    year: shifted.getUTCFullYear(),
    month: shifted.getUTCMonth() + 1,
    day: shifted.getUTCDate(),
  }
}

/** ISO weekday (Monday 1 through Sunday 7) of one local calendar date. */
function isoWeekday(date: { year: number; month: number; day: number }): number {
  const weekday = new Date(Date.UTC(date.year, date.month - 1, date.day)).getUTCDay()
  return weekday === 0 ? 7 : weekday
}

function nextDaily(
  time: LocalTime,
  timeZone: string,
  afterMs: number,
): number | undefined {
  const start = localDateOf(afterMs, timeZone)
  for (let offset = 0; offset <= MAX_SEARCH_DAYS; offset++) {
    const date = addLocalDays(start, offset)
    const candidate = localToUtc(timeZone, date.year, date.month, date.day, time)
    if (candidate !== undefined && candidate > afterMs) return candidate
  }
  return undefined
}

function nextWeekly(
  time: LocalTime,
  weekdays: readonly number[],
  timeZone: string,
  afterMs: number,
): number | undefined {
  const allowed = new Set(weekdays)
  const start = localDateOf(afterMs, timeZone)
  for (let offset = 0; offset <= MAX_SEARCH_DAYS; offset++) {
    const date = addLocalDays(start, offset)
    if (!allowed.has(isoWeekday(date))) continue
    const candidate = localToUtc(timeZone, date.year, date.month, date.day, time)
    if (candidate !== undefined && candidate > afterMs) return candidate
  }
  return undefined
}

function nextCron(
  parsed: ParsedCron,
  timeZone: string,
  afterMs: number,
): number | undefined {
  const start = localDateOf(afterMs, timeZone)
  for (let offset = 0; offset <= MAX_SEARCH_DAYS; offset++) {
    const date = addLocalDays(start, offset)
    if (!parsed.month.includes(date.month)) continue
    if (!cronDayMatches(parsed, date.day, isoWeekday(date) % 7)) continue
    for (const hour of parsed.hour) {
      for (const minute of parsed.minute) {
        const candidate = localToUtc(timeZone, date.year, date.month, date.day, {
          hour,
          minute,
          second: 0,
        })
        if (candidate !== undefined && candidate > afterMs) return candidate
      }
    }
  }
  return undefined
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function requireString(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`${field} must be a non-empty string`)
  }
  return value.trim()
}

function requireInteger(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value)) {
    throw new Error(`${field} must be an integer`)
  }
  return value
}

/** Canonicalize and validate one IANA time zone. */
export function canonicalTimeZone(value: string): string {
  const trimmed = value.trim()
  if (trimmed === '') throw new Error('time_zone must be a non-empty IANA zone')
  if (/^[+-]\d{2}(?::?\d{2})?$/.test(trimmed)) {
    throw new Error(`invalid time_zone '${value}', expected an IANA zone`)
  }
  try {
    return new Intl.DateTimeFormat('en-US', { timeZone: trimmed }).resolvedOptions().timeZone
  } catch {
    throw new Error(`invalid time_zone '${value}'`)
  }
}

/** Normalize `HH:mm` or `HH:mm:ss` to `HH:mm:ss`, rejecting invalid clocks. */
export function normalizeLocalTime(value: string): string {
  const match = TIME_PATTERN.exec(value.trim())
  if (match === null) throw new Error(`invalid local time '${value}', expected HH:mm:ss`)
  const hour = Number(match[1])
  const minute = Number(match[2])
  const second = match[3] === undefined ? 0 : Number(match[3])
  const base = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:${String(second).padStart(2, '0')}`
  return match[4] === undefined ? base : `${base}.${match[4].padEnd(3, '0')}`
}

function parseLocalTime(value: string): LocalTime {
  const normalized = normalizeLocalTime(value)
  const [clock, fraction] = normalized.split('.')
  const [hour, minute, second] = clock.split(':').map(Number) as [number, number, number]
  return { hour, minute, second, ...(fraction === undefined ? {} : { millisecond: Number(fraction) }) }
}

function validateCalendarDate(year: number, month: number, day: number, field: string): void {
  const date = new Date(Date.UTC(year, month - 1, day))
  if (
    date.getUTCFullYear() !== year
    || date.getUTCMonth() !== month - 1
    || date.getUTCDate() !== day
  ) {
    throw new Error(`${field} is not a valid calendar date`)
  }
}

/** Parse an RFC 3339 instant with an explicit offset and normalize it to UTC. */
export function normalizeAtInstant(value: string): string {
  const trimmed = value.trim()
  if (!AT_PATTERN.test(trimmed)) {
    throw new Error('at must be an RFC 3339 date-time with an explicit offset, for example 2026-11-01T09:00:00+08:00')
  }
  const datePart = trimmed.slice(0, 10)
  const timePart = trimmed.slice(11, 19)
  const dateMatch = DATE_PATTERN.exec(datePart)
  const timeMatch = /^([01]\d|2[0-3]):([0-5]\d):([0-5]\d)$/.exec(timePart)
  if (dateMatch === null || timeMatch === null) throw new Error(`invalid at value '${value}'`)
  validateCalendarDate(Number(dateMatch[1]), Number(dateMatch[2]), Number(dateMatch[3]), 'at')
  const offset = /([+-])(\d{2}):(\d{2})$/.exec(trimmed)
  if (offset !== null) {
    const offsetHours = Number(offset[2])
    const offsetMinutes = Number(offset[3])
    if (offsetHours > 23 || offsetMinutes > 59) throw new Error(`invalid offset in at value '${value}'`)
  }
  const instant = Date.parse(trimmed)
  if (!Number.isFinite(instant)) throw new Error(`invalid at value '${value}'`)
  return new Date(instant).toISOString()
}

function parseLocalAt(value: Record<string, unknown>): string {
  const dateRaw = requireString(value['date'], 'at.date')
  const timeRaw = requireString(value['time'], 'at.time')
  const timeZoneRaw = value['time_zone'] ?? value['timeZone']
  if (typeof timeZoneRaw !== 'string') throw new Error('at.time_zone must be a string')
  const timeZone = canonicalTimeZone(timeZoneRaw)
  const dateMatch = DATE_PATTERN.exec(dateRaw)
  if (dateMatch === null) throw new Error(`invalid at.date '${dateRaw}'`)
  const year = Number(dateMatch[1])
  const month = Number(dateMatch[2])
  const day = Number(dateMatch[3])
  validateCalendarDate(year, month, day, 'at.date')
  const time = parseLocalTime(timeRaw)
  const instant = localToUtc(timeZone, year, month, day, time)
  if (instant === undefined) {
    throw new Error(`at.date/time does not exist in ${timeZone}`)
  }
  return new Date(instant).toISOString()
}

function readTimeZone(value: Record<string, unknown>): string | undefined {
  const raw = value['time_zone'] ?? value['timeZone']
  if (raw === undefined) return undefined
  if (typeof raw !== 'string') throw new Error('time_zone must be a string')
  return canonicalTimeZone(raw)
}

function requireTimeZone(value: Record<string, unknown>, field: string): string {
  const zone = readTimeZone(value)
  if (zone === undefined) throw new Error(`${field}.time_zone is required`)
  return zone
}

function normalizeCron(expression: string): string {
  const fields = expression.trim().split(/\s+/)
  if (fields.length !== 5) throw new Error(`cron expression must have 5 fields, got ${fields.length}`)
  return fields.join(' ')
}

/**
 * Parse one `TaskTrigger.params` object into a normalized schedule rule.
 * Throws on a missing, malformed, or ambiguous selector.
 */
export function parseScheduleRule(params: Record<string, unknown> | undefined): ScheduleRule {
  if (!isRecord(params)) throw new Error('schedule params are required')

  const cronRaw = params['cron']
  const atRaw = params['at']
  const afterRaw = params['afterSeconds'] ?? params['after_seconds']
  const everyRaw = params['everySeconds'] ?? params['every_seconds']
  const dailyRaw = params['daily']
  const weeklyRaw = params['weekly']
  const selectors = [
    cronRaw !== undefined,
    atRaw !== undefined,
    afterRaw !== undefined,
    everyRaw !== undefined,
    dailyRaw !== undefined,
    weeklyRaw !== undefined,
  ].filter(Boolean).length
  if (selectors !== 1) {
    throw new Error('schedule params must contain exactly one of cron, at, afterSeconds, everySeconds, daily, weekly')
  }
  const outerZone = params['time_zone'] ?? params['timeZone']
  const offsetRaw = params['timezoneOffsetMinutes']
  if (cronRaw === undefined) {
    if (outerZone !== undefined) throw new Error('time_zone is only valid with cron')
    if (offsetRaw !== undefined) throw new Error('timezoneOffsetMinutes is only valid with cron')
  } else if (typeof cronRaw === 'object' && cronRaw !== null) {
    if (outerZone !== undefined) throw new Error('time_zone must be inside the cron object')
    if (offsetRaw !== undefined || (cronRaw as Record<string, unknown>)['timezoneOffsetMinutes'] !== undefined) {
      throw new Error('timezoneOffsetMinutes is not valid with cron.time_zone')
    }
  } else if (typeof cronRaw === 'string') {
    const zone = readTimeZone(params)
    if (zone !== undefined && offsetRaw !== undefined) {
      throw new Error('cron accepts either time_zone or timezoneOffsetMinutes, not both')
    }
  }

  if (cronRaw !== undefined) {
    if (typeof cronRaw === 'string') {
      const expression = normalizeCron(cronRaw)
      parseCron(expression)
      const timeZone = readTimeZone(params)
      if (timeZone !== undefined) return { kind: 'cron', expression, timeZone }
      const timezoneOffsetMinutes = offsetRaw === undefined ? 0 : requireInteger(offsetRaw, 'timezoneOffsetMinutes')
      if (timezoneOffsetMinutes < -1440 || timezoneOffsetMinutes > 1440) {
        throw new Error('timezoneOffsetMinutes must be between -1440 and 1440')
      }
      return { kind: 'cron-offset', expression, timezoneOffsetMinutes }
    }
    if (isRecord(cronRaw)) {
      const expression = normalizeCron(requireString(cronRaw['expression'], 'cron.expression'))
      parseCron(expression)
      return { kind: 'cron', expression, timeZone: requireTimeZone(cronRaw, 'cron') }
    }
    throw new Error('cron must be a string or an object with expression and time_zone')
  }

  if (atRaw !== undefined) {
    if (typeof atRaw === 'string') return { kind: 'at', at: normalizeAtInstant(atRaw) }
    if (isRecord(atRaw)) return { kind: 'at', at: parseLocalAt(atRaw) }
    throw new Error('at must be an RFC 3339 string or a local date/time object')
  }

  if (afterRaw !== undefined) {
    const afterSeconds = requireInteger(afterRaw, 'afterSeconds')
    if (afterSeconds <= 0) throw new Error('afterSeconds must be positive')
    return { kind: 'after', afterSeconds }
  }

  if (everyRaw !== undefined) {
    const everySeconds = requireInteger(everyRaw, 'everySeconds')
    if (everySeconds < MIN_EVERY_SECONDS) {
      throw new Error(`everySeconds must be at least ${MIN_EVERY_SECONDS}`)
    }
    return { kind: 'every', everySeconds }
  }

  if (dailyRaw !== undefined) {
    if (!isRecord(dailyRaw)) throw new Error('daily must be an object with time and time_zone')
    return {
      kind: 'daily',
      time: normalizeLocalTime(requireString(dailyRaw['time'], 'daily.time')),
      timeZone: requireTimeZone(dailyRaw, 'daily'),
    }
  }

  if (weeklyRaw !== undefined) {
    if (!isRecord(weeklyRaw)) throw new Error('weekly must be an object with time, time_zone, and weekdays')
    const weekdaysRaw = weeklyRaw['weekdays']
    if (!Array.isArray(weekdaysRaw) || weekdaysRaw.length === 0) {
      throw new Error('weekly.weekdays must be a non-empty array of ISO weekdays')
    }
    const weekdays = [...new Set(weekdaysRaw.map((value) => requireInteger(value, 'weekly.weekdays')))]
      .sort((a, b) => a - b)
    if (weekdays.some((value) => value < 1 || value > 7)) {
      throw new Error('weekly.weekdays values must be between 1 (Monday) and 7 (Sunday)')
    }
    return {
      kind: 'weekly',
      time: normalizeLocalTime(requireString(weeklyRaw['time'], 'weekly.time')),
      timeZone: requireTimeZone(weeklyRaw, 'weekly'),
      weekdays,
    }
  }

  throw new Error('schedule params must contain exactly one of cron, at, afterSeconds, everySeconds, daily, weekly')
}

/** Whether a rule fires more than once. */
export function isRecurringSchedule(rule: ScheduleRule): boolean {
  return rule.kind !== 'at' && rule.kind !== 'after'
}

/** Stable identity of a normalized rule; a change resets the committed target. */
export function scheduleRuleKey(rule: ScheduleRule): string {
  return JSON.stringify(rule)
}

/**
 * First committed fire instant for a rule, strictly after `nowMs` for
 * recurring rules and the declared instant for one-shots.
 */
export function firstScheduledAt(rule: ScheduleRule, nowMs: number): string {
  switch (rule.kind) {
    case 'at': return rule.at
    case 'after': return new Date(nowMs + rule.afterSeconds * 1000).toISOString()
    case 'every': return new Date(nowMs + rule.everySeconds * 1000).toISOString()
    default: {
      const next = nextScheduledAt(rule, nowMs)
      if (next === undefined) throw new Error('schedule rule has no future fire time within 400 years')
      return next
    }
  }
}

/**
 * Next fire instant strictly after `afterMs`, or `undefined` for one-shots
 * and for recurring rules with no representable future occurrence.
 */
export function nextScheduledAt(rule: ScheduleRule, afterMs: number): string | undefined {
  switch (rule.kind) {
    case 'at':
    case 'after':
      return undefined
    case 'every':
      return new Date(afterMs + rule.everySeconds * 1000).toISOString()
    case 'cron': {
      const parsed = parseCron(rule.expression)
      const next = nextCron(parsed, rule.timeZone, afterMs)
      return next === undefined ? undefined : new Date(next).toISOString()
    }
    case 'cron-offset': {
      try {
        return nextFire(parseCron(rule.expression), new Date(afterMs), rule.timezoneOffsetMinutes).toISOString()
      } catch {
        return undefined
      }
    }
    case 'daily': {
      const next = nextDaily(parseLocalTime(rule.time), rule.timeZone, afterMs)
      return next === undefined ? undefined : new Date(next).toISOString()
    }
    case 'weekly': {
      const next = nextWeekly(parseLocalTime(rule.time), rule.weekdays, rule.timeZone, afterMs)
      return next === undefined ? undefined : new Date(next).toISOString()
    }
  }
}

/** Normalized source-specific fields exposed to the CEL `when` expression. */
export function scheduleEventPayload(rule: ScheduleRule): Record<string, unknown> {
  switch (rule.kind) {
    case 'cron': return { cron: rule.expression, timeZone: rule.timeZone }
    case 'cron-offset': return { cron: rule.expression, timezoneOffsetMinutes: rule.timezoneOffsetMinutes }
    case 'daily': return { daily: { time: rule.time, timeZone: rule.timeZone } }
    case 'weekly': return {
      weekly: { time: rule.time, timeZone: rule.timeZone, weekdays: [...rule.weekdays] },
    }
    case 'every': return { everySeconds: rule.everySeconds }
    case 'after': return { afterSeconds: rule.afterSeconds }
    case 'at': return { at: rule.at }
  }
}
