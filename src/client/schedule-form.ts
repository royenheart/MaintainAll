/**
 * Pure schedule-form helpers for the Save dialog.
 *
 * Keeping these functions out of the React entry makes the params contract
 * testable with `node --test` and keeps the client component focused on
 * rendering. No dsh imports and no React.
 */

import type { MaintainAllKey } from '../locales/keys.ts'

/** Schedule selectors offered by the save dialog. */
export type ScheduleKind = 'cron' | 'daily' | 'weekly' | 'every' | 'after' | 'at'

export const SCHEDULE_KINDS: Array<{ id: ScheduleKind; labelKey: MaintainAllKey }> = [
  { id: 'cron', labelKey: 'save.scheduleKind.cron' },
  { id: 'daily', labelKey: 'save.scheduleKind.daily' },
  { id: 'weekly', labelKey: 'save.scheduleKind.weekly' },
  { id: 'every', labelKey: 'save.scheduleKind.every' },
  { id: 'after', labelKey: 'save.scheduleKind.after' },
  { id: 'at', labelKey: 'save.scheduleKind.at' },
]

export interface ScheduleForm {
  kind: ScheduleKind
  cron: string
  timeZone: string
  time: string
  weekdays: string
  everySeconds: number
  afterSeconds: number
  atLocal: string
  /** Original stored params; preserved verbatim until a schedule field is edited. */
  legacyParams?: Record<string, unknown>
  /** Whether any schedule field was edited in this dialog session. */
  dirty?: boolean
}

export function browserTimeZone(): string {
  try {
    return new Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

/** Best-effort fixed-offset IANA zone for a legacy `timezoneOffsetMinutes`. */
export function timeZoneForOffset(minutes: number): string {
  if (minutes === 0) return 'UTC'
  if (minutes % 60 !== 0) return 'UTC'
  const hours = minutes / 60
  if (hours < -12 || hours > 12) return 'UTC'
  // IANA's Etc/GMT zones invert the sign: UTC+8 is Etc/GMT-8.
  return `Etc/GMT${hours > 0 ? '-' : '+'}${Math.abs(hours)}`
}

export function localInputValue(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

export function defaultScheduleForm(): ScheduleForm {
  return {
    kind: 'cron',
    cron: '',
    timeZone: browserTimeZone(),
    time: '02:00:00',
    weekdays: '1,2,3,4,5',
    everySeconds: 300,
    afterSeconds: 600,
    atLocal: '',
  }
}

function readZone(value: Record<string, unknown>): string | undefined {
  const zone = value['time_zone'] ?? value['timeZone']
  return typeof zone === 'string' && zone.trim() !== '' ? zone : undefined
}

/** Rebuild the editable schedule form from a stored trigger. */
export function scheduleFormOf(trigger: { params?: Record<string, unknown> } | undefined): ScheduleForm {
  const form = defaultScheduleForm()
  const params = trigger?.params
  if (params === undefined) return form
  // Preserve every stored selector shape (including unknown/legacy fields)
  // until the user actually edits a schedule field.
  form.legacyParams = JSON.parse(JSON.stringify(params)) as Record<string, unknown>
  const cron = params['cron']
  if (typeof cron === 'string') {
    form.kind = 'cron'
    form.cron = cron
    const zone = readZone(params)
    if (zone !== undefined) form.timeZone = zone
    else if (typeof params['timezoneOffsetMinutes'] === 'number') {
      form.timeZone = timeZoneForOffset(params['timezoneOffsetMinutes'])
    } else {
      // The legacy no-zone form was UTC; keep it explicit when editing.
      form.timeZone = 'UTC'
    }
    return form
  }
  if (typeof cron === 'object' && cron !== null) {
    const record = cron as Record<string, unknown>
    form.kind = 'cron'
    form.cron = typeof record['expression'] === 'string' ? record['expression'] : ''
    const zone = readZone(record)
    if (zone !== undefined) form.timeZone = zone
    return form
  }
  const daily = params['daily']
  if (typeof daily === 'object' && daily !== null) {
    const record = daily as Record<string, unknown>
    form.kind = 'daily'
    form.time = typeof record['time'] === 'string' ? record['time'] : form.time
    const zone = readZone(record)
    if (zone !== undefined) form.timeZone = zone
    return form
  }
  const weekly = params['weekly']
  if (typeof weekly === 'object' && weekly !== null) {
    const record = weekly as Record<string, unknown>
    form.kind = 'weekly'
    form.time = typeof record['time'] === 'string' ? record['time'] : form.time
    const zone = readZone(record)
    if (zone !== undefined) form.timeZone = zone
    if (Array.isArray(record['weekdays'])) {
      form.weekdays = record['weekdays'].filter((value): value is number => typeof value === 'number').join(',')
    }
    return form
  }
  const every = params['everySeconds'] ?? params['every_seconds']
  if (typeof every === 'number') {
    form.kind = 'every'
    form.everySeconds = every
    return form
  }
  const after = params['afterSeconds'] ?? params['after_seconds']
  if (typeof after === 'number') {
    form.kind = 'after'
    form.afterSeconds = after
    return form
  }
  const at = params['at']
  if (typeof at === 'string') {
    form.kind = 'at'
    form.timeZone = browserTimeZone()
    form.atLocal = localInputValue(at)
    return form
  }
  if (typeof at === 'object' && at !== null) {
    const record = at as Record<string, unknown>
    const date = typeof record['date'] === 'string' ? record['date'] : ''
    const time = typeof record['time'] === 'string' ? record['time'] : ''
    const zone = readZone(record)
    if (zone !== undefined) form.timeZone = zone
    if (date !== '' && time !== '') {
      form.kind = 'at'
      form.atLocal = `${date}T${time.length === 5 ? `${time}:00` : time.slice(0, 8)}`
    }
  }
  return form
}

/** Build the host-facing `params` object for one schedule form. */
export function scheduleParamsOf(form: ScheduleForm): Record<string, unknown> {
  if (form.legacyParams !== undefined && form.dirty !== true) {
    return JSON.parse(JSON.stringify(form.legacyParams)) as Record<string, unknown>
  }
  switch (form.kind) {
    case 'cron':
      return { cron: { expression: form.cron, time_zone: form.timeZone } }
    case 'daily':
      return { daily: { time: form.time, time_zone: form.timeZone } }
    case 'weekly': {
      const weekdays = [...new Set(
        form.weekdays
          .split(',')
          .map((value) => Number(value.trim()))
          .filter((value) => Number.isInteger(value) && value >= 1 && value <= 7),
      )].sort((a, b) => a - b)
      return { weekly: { time: form.time, time_zone: form.timeZone, weekdays } }
    }
    case 'every':
      return { everySeconds: Math.max(60, Math.floor(form.everySeconds)) }
    case 'after':
      return { afterSeconds: Math.max(1, Math.floor(form.afterSeconds)) }
    case 'at': {
      const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})(?::(\d{2}))?$/.exec(form.atLocal)
      if (match === null) return { at: form.atLocal }
      return {
        at: {
          date: match[1],
          time: `${match[2]}:${match[3] ?? '00'}`,
          time_zone: form.timeZone || browserTimeZone(),
        },
      }
    }
  }
}

export const TIME_ZONE_OPTIONS: string[] = (() => {
  const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] }
  try {
    return intl.supportedValuesOf?.('timeZone') ?? []
  } catch {
    return []
  }
})()
