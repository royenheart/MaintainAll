import { test } from 'node:test'
import assert from 'node:assert/strict'
import { nextFire, parseCron } from '../../src/core/triggers/schedule.ts'

test('parseCron: wildcard and exact fields', () => {
  const parsed = parseCron('* * * * *')
  assert.equal(parsed.minute.length, 60)
  assert.equal(parsed.hour.length, 24)
  assert.equal(parsed.dayOfMonth.length, 31)
  assert.equal(parsed.month.length, 12)
  assert.deepEqual(parsed.dayOfWeek, [0, 1, 2, 3, 4, 5, 6])

  const exact = parseCron('30 9 15 6 2')
  assert.deepEqual(exact.minute, [30])
  assert.deepEqual(exact.hour, [9])
  assert.deepEqual(exact.dayOfMonth, [15])
  assert.deepEqual(exact.month, [6])
  assert.deepEqual(exact.dayOfWeek, [2])
})

test('parseCron: steps, ranges, and lists', () => {
  assert.deepEqual(parseCron('*/15 * * * *').minute, [0, 15, 30, 45])
  assert.deepEqual(parseCron('0-10/5 * * * *').minute, [0, 5, 10])
  assert.deepEqual(parseCron('1-3 * * * *').minute, [1, 2, 3])
  assert.deepEqual(parseCron('5,10,5 * * * *').minute, [5, 10])
  assert.deepEqual(parseCron('0 9-17 * * *').hour, [9, 10, 11, 12, 13, 14, 15, 16, 17])
  // 7 normalizes to Sunday (0).
  assert.deepEqual(parseCron('* * * * 7').dayOfWeek, [0])
  assert.deepEqual(parseCron('* * * * 1,7').dayOfWeek, [0, 1])
})

test('parseCron: malformed expressions throw', () => {
  assert.throws(() => parseCron('* * * *'), /5 fields/)
  assert.throws(() => parseCron('* * * * * *'), /5 fields/)
  assert.throws(() => parseCron('60 * * * *'), /out of range/)
  assert.throws(() => parseCron('*/0 * * * *'), /step/)
  assert.throws(() => parseCron('5-1 * * * *'), /range start > end/)
  assert.throws(() => parseCron('a * * * *'), /invalid number/)
  assert.throws(() => parseCron('1,,2 * * * *'), /empty list entry/)
  assert.throws(() => parseCron('* * 32 * *'), /out of range/)
  assert.throws(() => parseCron('* 24 * * *'), /out of range/)
  // Stepped single values must not silently become empty match sets.
  assert.throws(() => parseCron('70/2 * * * *'), /out of range/)
  assert.throws(() => parseCron('* * * * 8/2'), /out of range/)
})

test('parseCron: a/n steps from a to the field maximum', () => {
  const parsed = parseCron('5/15 * * * *')
  assert.deepEqual(parsed.minute, [5, 20, 35, 50])
})

test('nextFire: minute stepping', () => {
  const parsed = parseCron('*/15 * * * *')
  const after = new Date('2026-08-23T00:07:30.000Z')
  assert.equal(nextFire(parsed, after).toISOString(), '2026-08-23T00:15:00.000Z')
})

test('nextFire: daily schedule, strictly after', () => {
  const parsed = parseCron('0 9 * * *')
  assert.equal(
    nextFire(parsed, new Date('2026-08-23T08:59:59.000Z')).toISOString(),
    '2026-08-23T09:00:00.000Z',
  )
  // Exactly at a fire time, the next fire is the following day.
  assert.equal(
    nextFire(parsed, new Date('2026-08-23T09:00:00.000Z')).toISOString(),
    '2026-08-24T09:00:00.000Z',
  )
})

test('nextFire: skips non-matching hours and months', () => {
  const parsed = parseCron('30 14 1 9 *')
  assert.equal(
    nextFire(parsed, new Date('2026-08-23T00:00:00.000Z')).toISOString(),
    '2026-09-01T14:30:00.000Z',
  )
})

test('nextFire: day-of-week matching, including 7 as Sunday', () => {
  // 2026-08-23 is a Sunday; 2026-08-24 is a Monday.
  const monday = parseCron('0 0 * * 1')
  assert.equal(
    nextFire(monday, new Date('2026-08-23T00:00:00.000Z')).toISOString(),
    '2026-08-24T00:00:00.000Z',
  )
  const sunday7 = parseCron('0 0 * * 7')
  assert.equal(
    nextFire(sunday7, new Date('2026-08-24T00:00:00.000Z')).toISOString(),
    '2026-08-30T00:00:00.000Z',
  )
})

test('nextFire: dom/dow both restricted use OR semantics', () => {
  // Midnight on the 1st of the month OR on a Monday.
  const parsed = parseCron('0 0 1 * 1')
  // 2026-08-23 (Sun) -> Monday 2026-08-24 wins over Sep 1.
  assert.equal(
    nextFire(parsed, new Date('2026-08-23T00:00:00.000Z')).toISOString(),
    '2026-08-24T00:00:00.000Z',
  )
  // After Monday, the next Monday (Aug 31) wins over Sep 1.
  assert.equal(
    nextFire(parsed, new Date('2026-08-24T00:00:00.000Z')).toISOString(),
    '2026-08-31T00:00:00.000Z',
  )
  // After Aug 31, Sep 1 (Tue, day-of-month match) is next.
  assert.equal(
    nextFire(parsed, new Date('2026-08-31T00:00:00.000Z')).toISOString(),
    '2026-09-01T00:00:00.000Z',
  )
})

test('nextFire: a stepped day star keeps dsh day semantics', () => {
  // `*/2` starts with `*`, so day-of-month and day-of-week must both match:
  // only Mondays whose date is odd. 2026-08-24 is a Monday with an even date.
  const parsed = parseCron('0 0 */2 * 1')
  assert.equal(parsed.dayOfMonthStar, true)
  assert.equal(parsed.dayOfWeekStar, false)
  assert.equal(
    nextFire(parsed, new Date('2026-08-23T00:00:00.000Z')).toISOString(),
    '2026-08-31T00:00:00.000Z',
  )
})

test('nextFire: timezone offset east and west of UTC', () => {
  const parsed = parseCron('0 9 * * *')
  // UTC+8: local 08:30 -> next local 09:00 == 01:00 UTC.
  assert.equal(
    nextFire(parsed, new Date('2026-08-23T00:30:00.000Z'), 480).toISOString(),
    '2026-08-23T01:00:00.000Z',
  )
  // UTC-5 midnight: local 01:00 -> next local midnight == 05:00 UTC next day.
  const midnight = parseCron('0 0 * * *')
  assert.equal(
    nextFire(midnight, new Date('2026-08-23T06:00:00.000Z'), -300).toISOString(),
    '2026-08-24T05:00:00.000Z',
  )
})

test('nextFire: Feb 29 leaps within the four-year horizon', () => {
  const parsed = parseCron('0 0 29 2 *')
  assert.equal(
    nextFire(parsed, new Date('2026-08-23T00:00:00.000Z')).toISOString(),
    '2028-02-29T00:00:00.000Z',
  )
})
