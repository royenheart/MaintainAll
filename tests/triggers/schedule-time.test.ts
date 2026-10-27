import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  firstScheduledAt,
  isRecurringSchedule,
  nextScheduledAt,
  parseScheduleRule,
  scheduleEventPayload,
  scheduleRuleKey,
} from '../../src/core/triggers/schedule-time.ts'

const NOW = Date.parse('2026-08-23T00:00:00.000Z')

test('schedule-rule: cron in an IANA zone fires at the local minute', () => {
  const rule = parseScheduleRule({
    cron: { expression: '0 9 * * *', time_zone: 'Asia/Shanghai' },
  })
  assert.deepEqual(rule, { kind: 'cron', expression: '0 9 * * *', timeZone: 'Asia/Shanghai' })
  assert.equal(firstScheduledAt(rule, NOW), '2026-08-23T01:00:00.000Z')
  assert.equal(nextScheduledAt(rule, Date.parse('2026-08-23T01:00:00.000Z')), '2026-08-24T01:00:00.000Z')
})

test('schedule-rule: legacy cron string keeps the fixed offset', () => {
  const rule = parseScheduleRule({ cron: '0 9 * * *', timezoneOffsetMinutes: 480 })
  assert.deepEqual(rule, {
    kind: 'cron-offset',
    expression: '0 9 * * *',
    timezoneOffsetMinutes: 480,
  })
  assert.equal(firstScheduledAt(rule, Date.parse('2026-08-23T00:30:00.000Z')), '2026-08-23T01:00:00.000Z')
})

test('schedule-rule: rejects conflicting zone fields and offset-only zones', () => {
  assert.throws(() => parseScheduleRule({
    cron: '0 9 * * *',
    time_zone: 'UTC',
    timezoneOffsetMinutes: 0,
  }), /not both/)
  assert.throws(() => parseScheduleRule({
    cron: { expression: '0 9 * * *', time_zone: 'UTC' },
    time_zone: 'UTC',
  }), /inside the cron object/)
  assert.throws(() => parseScheduleRule({
    daily: { time: '09:00:00', time_zone: 'UTC' },
    timezoneOffsetMinutes: 0,
  }), /only valid with cron/)
  assert.throws(() => parseScheduleRule({
    cron: { expression: '0 9 * * *', time_zone: 'UTC', timezoneOffsetMinutes: 0 },
  }), /not valid with cron/)
  assert.throws(() => parseScheduleRule({
    cron: { expression: '0 9 * * *', time_zone: '+08' },
  }), /IANA zone/)
})

test('schedule-rule: daily and weekly local wall-clock times', () => {
  const daily = parseScheduleRule({
    daily: { time: '09:30:00', time_zone: 'Asia/Shanghai' },
  })
  assert.equal(firstScheduledAt(daily, NOW), '2026-08-23T01:30:00.000Z')

  const weekly = parseScheduleRule({
    weekly: { time: '09:00:00', time_zone: 'Asia/Shanghai', weekdays: [3, 1, 3] },
  })
  assert.deepEqual(weekly, {
    kind: 'weekly',
    time: '09:00:00',
    timeZone: 'Asia/Shanghai',
    weekdays: [1, 3],
  })
  const first = firstScheduledAt(weekly, NOW)
  assert.equal(first, '2026-08-24T01:00:00.000Z')
  assert.equal(nextScheduledAt(weekly, Date.parse(first)), '2026-08-26T01:00:00.000Z')
})

test('schedule-rule: every and after are interval-based one-shots/repeats', () => {
  const every = parseScheduleRule({ everySeconds: 300 })
  assert.equal(isRecurringSchedule(every), true)
  assert.equal(firstScheduledAt(every, NOW), '2026-08-23T00:05:00.000Z')
  assert.equal(nextScheduledAt(every, Date.parse('2026-08-23T00:05:00.000Z')), '2026-08-23T00:10:00.000Z')

  const after = parseScheduleRule({ afterSeconds: 600 })
  assert.equal(isRecurringSchedule(after), false)
  assert.equal(firstScheduledAt(after, NOW), '2026-08-23T00:10:00.000Z')
  assert.equal(nextScheduledAt(after, NOW), undefined)
})

test('schedule-rule: absolute one-shots accept an offset or a local date/time', () => {
  const instant = parseScheduleRule({ at: '2026-11-01T09:00:00+08:00' })
  assert.deepEqual(instant, { kind: 'at', at: '2026-11-01T01:00:00.000Z' })

  const local = parseScheduleRule({
    at: { date: '2026-11-01', time: '09:00', time_zone: 'Asia/Shanghai' },
  })
  assert.deepEqual(local, { kind: 'at', at: '2026-11-01T01:00:00.000Z' })

  // A stored one-shot in the past still fires once on the next tick.
  assert.equal(firstScheduledAt(instant, NOW), '2026-11-01T01:00:00.000Z')
  assert.equal(nextScheduledAt(instant, NOW), undefined)
})

test('schedule-rule: DST gap skips the nonexistent local time', () => {
  // US DST starts 2026-03-08; 02:30 local does not exist in New York.
  const rule = parseScheduleRule({
    cron: { expression: '30 2 * * *', time_zone: 'America/New_York' },
  })
  assert.equal(
    firstScheduledAt(rule, Date.parse('2026-03-08T05:00:00.000Z')),
    '2026-03-09T06:30:00.000Z',
  )
})

test('schedule-rule: DST overlap uses the earlier instant and does not reuse the later one', () => {
  // US DST ends 2026-11-01; 01:30 occurs twice.
  const rule = parseScheduleRule({
    cron: { expression: '30 1 * * *', time_zone: 'America/New_York' },
  })
  assert.equal(
    firstScheduledAt(rule, Date.parse('2026-11-01T04:00:00.000Z')),
    '2026-11-01T05:30:00.000Z',
  )
  // After the earlier 01:30, the later 01:30 is not eligible; the next day wins.
  assert.equal(
    nextScheduledAt(rule, Date.parse('2026-11-01T05:45:00.000Z')),
    '2026-11-02T06:30:00.000Z',
  )
})

test('schedule-rule: the search horizon crosses a non-leap century', () => {
  const rule = parseScheduleRule({
    cron: { expression: '0 0 29 2 *', time_zone: 'UTC' },
  })
  // 2100 is not a leap year, so the next Feb 29 after 2096 is 2104.
  assert.equal(
    firstScheduledAt(rule, Date.parse('2096-03-01T00:00:00.000Z')),
    '2104-02-29T00:00:00.000Z',
  )
})

test('schedule-rule: a stepped-star day field keeps Vixie/dsh day semantics', () => {
  // `*/2` starts with `*`, so day-of-month and day-of-week must both match:
  // only Mondays whose date is odd. 2026-08-24 is a Monday with an even date.
  const rule = parseScheduleRule({
    cron: { expression: '0 0 */2 * 1', time_zone: 'UTC' },
  })
  assert.equal(firstScheduledAt(rule, NOW), '2026-08-31T00:00:00.000Z')
})

test('schedule-rule: malformed selectors are rejected', () => {
  assert.throws(() => parseScheduleRule(undefined), /params are required/)
  assert.throws(() => parseScheduleRule({}), /exactly one/)
  assert.throws(
    () => parseScheduleRule({ cron: '0 0 * * *', everySeconds: 60 }),
    /exactly one/,
  )
  assert.throws(
    () => parseScheduleRule({ cron: { expression: '0 0 * * *', time_zone: 'Mars/Olympus' } }),
    /invalid time_zone/,
  )
  assert.throws(
    () => parseScheduleRule({ cron: { expression: '0 0 * * *', time_zone: '+08:00' } }),
    /IANA zone/,
  )
  assert.throws(() => parseScheduleRule({ everySeconds: 59 }), /at least 60/)
  assert.throws(() => parseScheduleRule({ afterSeconds: 0 }), /positive/)
  assert.throws(() => parseScheduleRule({ at: '2026-11-01T09:00:00' }), /explicit offset/)
  assert.throws(() => parseScheduleRule({ at: '2026-02-30T09:00:00Z' }), /valid calendar date/)
  assert.throws(
    () => parseScheduleRule({ daily: { time: '24:00:00', time_zone: 'UTC' } }),
    /invalid local time/,
  )
  assert.throws(
    () => parseScheduleRule({ weekly: { time: '09:00', time_zone: 'UTC', weekdays: [] } }),
    /non-empty array/,
  )
  assert.throws(
    () => parseScheduleRule({ weekly: { time: '09:00', time_zone: 'UTC', weekdays: [0] } }),
    /between 1/,
  )
})

test('schedule-rule: rule key changes when the time zone or rule changes', () => {
  const shanghai = parseScheduleRule({
    cron: { expression: '0 9 * * *', time_zone: 'Asia/Shanghai' },
  })
  const tokyo = parseScheduleRule({
    cron: { expression: '0 9 * * *', time_zone: 'Asia/Tokyo' },
  })
  assert.notEqual(scheduleRuleKey(shanghai), scheduleRuleKey(tokyo))
  assert.equal(
    scheduleRuleKey(shanghai),
    scheduleRuleKey(parseScheduleRule({
      cron: { expression: '0 9 * * *', time_zone: 'Asia/Shanghai' },
    })),
  )
})

test('schedule-rule: event payload keeps the CEL-friendly fields', () => {
  const cron = parseScheduleRule({
    cron: { expression: '0 9 * * *', time_zone: 'Asia/Shanghai' },
  })
  assert.deepEqual(scheduleEventPayload(cron), {
    cron: '0 9 * * *',
    timeZone: 'Asia/Shanghai',
  })
  const weekly = parseScheduleRule({
    weekly: { time: '09:00:00', time_zone: 'Asia/Shanghai', weekdays: [1, 3] },
  })
  assert.deepEqual(scheduleEventPayload(weekly), {
    weekly: { time: '09:00:00', timeZone: 'Asia/Shanghai', weekdays: [1, 3] },
  })
})

test('schedule-rule: local fractional seconds are preserved', () => {
  const rule = parseScheduleRule({ daily: { time: '09:00:00.900', time_zone: 'UTC' } })
  assert.equal(
    firstScheduledAt(rule, Date.parse('2026-10-26T09:00:00.100Z')),
    '2026-10-26T09:00:00.900Z',
  )
  const at = parseScheduleRule({ at: { date: '2026-12-01', time: '09:00:00.500', time_zone: 'UTC' } })
  assert.equal(at.kind === 'at' ? at.at : '', '2026-12-01T09:00:00.500Z')
})
