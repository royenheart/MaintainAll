import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  browserTimeZone,
  defaultScheduleForm,
  localInputValue,
  scheduleFormOf,
  scheduleParamsOf,
  timeZoneForOffset,
} from '../../src/client/schedule-form.ts'

test('schedule form: defaults are a usable cron form', () => {
  const form = defaultScheduleForm()
  assert.equal(form.kind, 'cron')
  assert.equal(form.time, '02:00:00')
  assert.ok(form.timeZone !== '')
  assert.deepEqual(scheduleParamsOf(form), {
    cron: { expression: '', time_zone: form.timeZone },
  })
})

test('schedule form: reads every stored selector shape', () => {
  const legacyParams = { cron: '0 9 * * *', timezoneOffsetMinutes: 480 }
  const legacy = scheduleFormOf({ params: legacyParams })
  assert.equal(legacy.kind, 'cron')
  assert.equal(legacy.cron, '0 9 * * *')
  assert.equal(legacy.timeZone, 'Etc/GMT-8')
  assert.deepEqual(legacy.legacyParams, legacyParams)
  // A metadata-only edit must leave the stored trigger untouched.
  assert.deepEqual(scheduleParamsOf(legacy), legacyParams)

  assert.equal(scheduleFormOf({
    params: { cron: { expression: '30 2 * * *', time_zone: 'America/New_York' } },
  }).timeZone, 'America/New_York')

  // The legacy no-zone form was UTC; editing must not silently move it.
  assert.equal(scheduleFormOf({ params: { cron: '0 9 * * *' } }).timeZone, 'UTC')

  assert.equal(scheduleFormOf({
    params: { daily: { time: '09:30:00', time_zone: 'Asia/Shanghai' } },
  }).kind, 'daily')

  const weekly = scheduleFormOf({
    params: { weekly: { time: '09:00:00', time_zone: 'Asia/Shanghai', weekdays: [1, 3] } },
  })
  assert.equal(weekly.kind, 'weekly')
  assert.equal(weekly.weekdays, '1,3')

  assert.equal(scheduleFormOf({ params: { everySeconds: 300 } }).everySeconds, 300)
  assert.equal(scheduleFormOf({ params: { afterSeconds: 600 } }).afterSeconds, 600)

  const localAt = scheduleFormOf({
    params: { at: { date: '2026-11-01', time: '09:00:35', time_zone: 'Asia/Shanghai' } },
  })
  assert.equal(localAt.kind, 'at')
  assert.equal(localAt.atLocal, '2026-11-01T09:00:35')
  assert.equal(localAt.timeZone, 'Asia/Shanghai')
})

test('schedule form: builds canonical params for each selector', () => {
  const base = defaultScheduleForm()
  assert.deepEqual(scheduleParamsOf({ ...base, kind: 'cron', cron: '0 9 * * *', timeZone: 'Asia/Shanghai' }), {
    cron: { expression: '0 9 * * *', time_zone: 'Asia/Shanghai' },
  })
  assert.deepEqual(scheduleParamsOf({ ...base, kind: 'daily', time: '09:30:00', timeZone: 'Asia/Shanghai' }), {
    daily: { time: '09:30:00', time_zone: 'Asia/Shanghai' },
  })
  assert.deepEqual(scheduleParamsOf({
    ...base,
    kind: 'weekly',
    time: '09:00:00',
    timeZone: 'Asia/Shanghai',
    weekdays: '3,1,3,9',
  }), {
    weekly: { time: '09:00:00', time_zone: 'Asia/Shanghai', weekdays: [1, 3] },
  })
  assert.deepEqual(scheduleParamsOf({ ...base, kind: 'every', everySeconds: 5 }), { everySeconds: 60 })
  assert.deepEqual(scheduleParamsOf({ ...base, kind: 'after', afterSeconds: 0 }), { afterSeconds: 1 })

  const atLocal = '2026-11-01T09:00:35'
  assert.deepEqual(scheduleParamsOf({ ...base, kind: 'at', atLocal }), {
    at: { date: '2026-11-01', time: '09:00:35', time_zone: base.timeZone },
  })
})

test('schedule form: editing a schedule field migrates a legacy trigger', () => {
  const form = scheduleFormOf({
    params: { cron: '0 9 * * *', timezoneOffsetMinutes: 480 },
  })
  assert.deepEqual(scheduleParamsOf({ ...form, dirty: true, timeZone: 'Asia/Shanghai' }), {
    cron: { expression: '0 9 * * *', time_zone: 'Asia/Shanghai' },
  })
})

test('schedule form: legacy offsets map to fixed Etc/GMT zones when whole-hour', () => {
  assert.equal(timeZoneForOffset(0), 'UTC')
  assert.equal(timeZoneForOffset(480), 'Etc/GMT-8')
  assert.equal(timeZoneForOffset(-300), 'Etc/GMT+5')
  assert.equal(timeZoneForOffset(330), 'UTC')
  assert.equal(timeZoneForOffset(-780), 'UTC')
  assert.equal(browserTimeZone() !== '', true)
})

test('schedule form: datetime-local round-trips the same local clock', () => {
  const instant = new Date(2026, 0, 2, 3, 4, 5)
  assert.equal(localInputValue(instant.toISOString()), '2026-01-02T03:04:05')
})
