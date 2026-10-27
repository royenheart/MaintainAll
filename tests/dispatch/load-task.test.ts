import test from 'node:test'
import assert from 'node:assert/strict'

import { parseSeedFile } from '../../src/dispatch/load-task.ts'

test('parseSeedFile normalizes a contiguous seed that starts after seq 0', () => {
  const seed = parseSeedFile([
    '{"type":"session","cwd":"/tmp/ops"}',
    '{"type":"turn/start","seq":5,"data":{"turn":1}}',
    '{"type":"turn/end","seq":6,"data":{}}',
  ].join('\n'))
  assert.equal(seed.cwd, '/tmp/ops')
  assert.deepEqual(seed.events.map((event) => event.seq), [0, 1])
})

test('parseSeedFile accepts durable-only gaps and normalizes them', () => {
  const seed = parseSeedFile([
    '{"type":"session","cwd":"/tmp/ops"}',
    '{"type":"turn/start","seq":4,"data":{"turn":1}}',
    '{"type":"user/message","seq":9,"data":{"content":"hi"}}',
    '{"type":"turn/end","seq":261,"data":{}}',
  ].join('\n'))
  assert.deepEqual(seed.events.map((event) => event.seq), [0, 1, 2])
})

test('parseSeedFile rejects a non-increasing sequence', () => {
  assert.throws(() => parseSeedFile([
    '{"type":"session","cwd":"/tmp/ops"}',
    '{"type":"turn/start","seq":5,"data":{"turn":1}}',
    '{"type":"turn/end","seq":5,"data":{}}',
  ].join('\n')), /strictly increasing/)
})
