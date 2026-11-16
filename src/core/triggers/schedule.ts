/**
 * Cron parsing and next-fire computation for the `schedule` trigger source.
 *
 * Supports the classic 5-field cron format — minute, hour, day-of-month,
 * month, day-of-week — with `*`, `*\/n`, `a-b`, `a-b/n`, exact numbers, and
 * comma lists. Day-of-week accepts 0-7 where both 0 and 7 mean Sunday.
 *
 * Day-of-month and day-of-week follow Vixie semantics with an explicit star
 * flag, matching dsh's schedule dialect: when either field's source text
 * starts with `*`, both fields must match; when neither is a star, either
 * field matching is enough. The flag is kept separately from the matched
 * value set because `*` and `*\/2` both produce a subset but mean different
 * things to the day rule.
 *
 * `nextFire` works in the timezone identified by `timezoneOffsetMinutes`
 * (minutes east of UTC, e.g. 480 for UTC+8) and returns a UTC instant. This
 * fixed-offset path is the legacy `cron-offset` rule; new rules use an IANA
 * zone through `schedule-time.ts`. Everything is pure date arithmetic — no
 * timers, no IO.
 */

export interface ParsedCron {
  minute: number[]
  hour: number[]
  dayOfMonth: number[]
  month: number[]
  dayOfWeek: number[]
  /** Whether the day-of-month source text starts with `*`. */
  dayOfMonthStar: boolean
  /** Whether the day-of-week source text starts with `*`. */
  dayOfWeekStar: boolean
}

type CronFieldName = 'minute' | 'hour' | 'dayOfMonth' | 'month' | 'dayOfWeek'

interface FieldSpec {
  min: number
  max: number
  /** Values to remap after parsing (day-of-week 7 -> 0). */
  normalize?: (value: number) => number
}

const FIELD_SPECS: Record<CronFieldName, FieldSpec> = {
  minute: { min: 0, max: 59 },
  hour: { min: 0, max: 23 },
  dayOfMonth: { min: 1, max: 31 },
  month: { min: 1, max: 12 },
  dayOfWeek: { min: 0, max: 7, normalize: (value) => (value === 7 ? 0 : value) },
}

function parseIntStrict(raw: string, field: string): number {
  if (!/^\d+$/.test(raw)) {
    throw new Error(`cron ${field}: invalid number '${raw}'`)
  }
  return Number(raw)
}

function parseField(field: CronFieldName, raw: string): number[] {
  const spec = FIELD_SPECS[field]
  const values = new Set<number>()
  for (const part of raw.split(',')) {
    if (part === '') {
      throw new Error(`cron ${field}: empty list entry`)
    }
    const [rangeRaw, stepRaw, ...extra] = part.split('/')
    if (extra.length > 0) {
      throw new Error(`cron ${field}: too many '/' in '${part}'`)
    }
    let step = 1
    if (stepRaw !== undefined) {
      step = parseIntStrict(stepRaw, field)
      if (step < 1) {
        throw new Error(`cron ${field}: step must be >= 1 in '${part}'`)
      }
    }
    let lo: number
    let hi: number
    if (rangeRaw === '*') {
      lo = spec.min
      hi = spec.max
    } else if (rangeRaw !== undefined && rangeRaw.includes('-')) {
      const [a, b, ...rest] = rangeRaw.split('-')
      if (rest.length > 0 || a === undefined || b === undefined || a === '' || b === '') {
        throw new Error(`cron ${field}: invalid range '${rangeRaw}'`)
      }
      lo = parseIntStrict(a, field)
      hi = parseIntStrict(b, field)
      if (lo > hi) {
        throw new Error(`cron ${field}: range start > end in '${rangeRaw}'`)
      }
    } else if (rangeRaw !== undefined) {
      lo = parseIntStrict(rangeRaw, field)
      // `a/n` steps from a to the field maximum; bare `a` is exact.
      hi = stepRaw !== undefined ? spec.max : lo
    } else {
      throw new Error(`cron ${field}: invalid entry '${part}'`)
    }
    if (lo < spec.min || lo > spec.max || hi < spec.min || hi > spec.max) {
      throw new Error(`cron ${field}: value out of range ${spec.min}-${spec.max} in '${part}'`)
    }
    for (let value = lo; value <= hi; value += step) {
      values.add(spec.normalize ? spec.normalize(value) : value)
    }
  }
  return [...values].sort((a, b) => a - b)
}

const FIELD_ORDER: CronFieldName[] = ['minute', 'hour', 'dayOfMonth', 'month', 'dayOfWeek']

/**
 * Parse a 5-field cron expression into sorted match lists per field.
 * Throws on any malformed field.
 */
export function parseCron(expr: string): ParsedCron {
  const fields = expr.trim().split(/\s+/)
  if (fields.length !== 5) {
    throw new Error(`cron expression must have 5 fields, got ${fields.length}`)
  }
  const parsed = {} as ParsedCron
  for (let i = 0; i < FIELD_ORDER.length; i++) {
    const name = FIELD_ORDER[i]!
    parsed[name] = parseField(name, fields[i]!)
  }
  parsed.dayOfMonthStar = fields[2]!.startsWith('*')
  parsed.dayOfWeekStar = fields[4]!.startsWith('*')
  return parsed
}

const MINUTE_MS = 60_000
const DAY_MS = 86_400_000
/** Search horizon: the 400-year Gregorian cycle plus a day. */
export const CRON_SEARCH_DAYS = 366 * 400 + 100

/** Vixie day rule: both restricted means OR, either star means AND. */
export function cronDayMatches(parsed: ParsedCron, day: number, weekday: number): boolean {
  const domOk = parsed.dayOfMonth.includes(day)
  const dowOk = parsed.dayOfWeek.includes(weekday)
  return parsed.dayOfMonthStar || parsed.dayOfWeekStar ? domOk && dowOk : domOk || dowOk
}

/**
 * Compute the next UTC instant strictly after `after` at which `parsed`
 * fires, evaluated in the timezone `timezoneOffsetMinutes` east of UTC
 * (default UTC). Throws when nothing matches within 400 years.
 */
export function nextFire(parsed: ParsedCron, after: Date, timezoneOffsetMinutes = 0): Date {
  const offsetMs = timezoneOffsetMinutes * MINUTE_MS
  // Work in "local" time: shift the UTC instant into the target zone so UTC
  // calendar getters read local wall-clock fields.
  const localNow = after.getTime() + offsetMs
  // First candidate: the next whole minute (cron has minute resolution).
  const firstCandidate = Math.floor(localNow / MINUTE_MS) * MINUTE_MS + MINUTE_MS

  let dayStart = Math.floor(firstCandidate / DAY_MS) * DAY_MS
  for (let day = 0; day < CRON_SEARCH_DAYS; day++) {
    const date = new Date(dayStart)
    const monthOk = parsed.month.includes(date.getUTCMonth() + 1)
    if (monthOk) {
      const dayOk = cronDayMatches(parsed, date.getUTCDate(), date.getUTCDay())
      if (dayOk) {
        for (const hour of parsed.hour) {
          for (const minute of parsed.minute) {
            const candidate = dayStart + (hour * 60 + minute) * MINUTE_MS
            if (candidate >= firstCandidate) {
              return new Date(candidate - offsetMs)
            }
          }
        }
      }
    }
    dayStart += DAY_MS
  }
  throw new Error('cron expression has no fire time within 400 years')
}
