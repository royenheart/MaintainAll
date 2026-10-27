import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  filterJournalEntry,
  parseJournalJsonLine,
} from '../../src/core/triggers/journald.ts'

const LINE = JSON.stringify({
  _SYSTEMD_UNIT: 'nginx.service',
  PRIORITY: '3',
  MESSAGE: 'worker process exited',
  __REALTIME_TIMESTAMP: '1787443200000000', // 2026-08-23T00:00:00Z in micros
})

test('parseJournalJsonLine: maps systemd fields', () => {
  const entry = parseJournalJsonLine(LINE)!
  assert.equal(entry.unit, 'nginx.service')
  assert.equal(entry.priority, 3)
  assert.equal(entry.message, 'worker process exited')
  assert.equal(entry.timestamp, '2026-08-23T00:00:00.000Z')
})

test('parseJournalJsonLine: malformed input returns null', () => {
  assert.equal(parseJournalJsonLine('not json'), null)
  assert.equal(parseJournalJsonLine(''), null)
  assert.equal(parseJournalJsonLine('["a"]'), null)
})

test('parseJournalJsonLine: missing fields stay absent', () => {
  const entry = parseJournalJsonLine('{"MESSAGE":"hi","PRIORITY":"bogus"}')!
  assert.equal(entry.message, 'hi')
  assert.equal(entry.priority, undefined)
  assert.equal(entry.unit, undefined)
  assert.equal(entry.timestamp, undefined)
})

test('filterJournalEntry: unit exact match', () => {
  const entry = parseJournalJsonLine(LINE)!
  assert.equal(filterJournalEntry(entry, { unit: 'nginx.service' }), true)
  assert.equal(filterJournalEntry(entry, { unit: 'sshd.service' }), false)
  assert.equal(filterJournalEntry(entry, {}), true)
})

test('filterJournalEntry: priority threshold is severity-at-least (<=)', () => {
  const entry = parseJournalJsonLine(LINE)! // priority 3 (error)
  assert.equal(filterJournalEntry(entry, { priority: 3 }), true)
  assert.equal(filterJournalEntry(entry, { priority: 4 }), true)
  assert.equal(filterJournalEntry(entry, { priority: 2 }), false)
  // Entries without a priority never match a priority filter.
  const bare = parseJournalJsonLine('{"MESSAGE":"hi"}')!
  assert.equal(filterJournalEntry(bare, { priority: 6 }), false)
})

test('filterJournalEntry: regex on message, combined clauses', () => {
  const entry = parseJournalJsonLine(LINE)!
  assert.equal(filterJournalEntry(entry, { regex: 'exited' }), true)
  assert.equal(filterJournalEntry(entry, { regex: '^worker' }), true)
  assert.equal(filterJournalEntry(entry, { regex: 'oom' }), false)
  assert.equal(
    filterJournalEntry(entry, { unit: 'nginx.service', priority: 3, regex: 'exited' }),
    true,
  )
  assert.equal(
    filterJournalEntry(entry, { unit: 'nginx.service', priority: 2, regex: 'exited' }),
    false,
  )
})
