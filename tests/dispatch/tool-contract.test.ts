import test from 'node:test'
import assert from 'node:assert/strict'

import { TASK_TRIGGER_SOURCES } from '../../src/core/contract.ts'
import {
  OPS_SAVE_TASK_TRIGGER_GUIDE,
  OPS_SAVE_TASK_TRIGGER_SCHEMA,
  SAVE_PROMPT_TRIGGER_LINES,
  TRIGGER_EXAMPLES,
  TRIGGER_EXAMPLE_LINES,
} from '../../src/dispatch/tool-contract.ts'
import { validateTaskTriggers } from '../../src/dispatch/save.ts'

test('tool contract: the trigger schema is closed and derives every trigger source', () => {
  const schema = OPS_SAVE_TASK_TRIGGER_SCHEMA as {
    type: string
    additionalProperties: boolean
    required: string[]
    properties: Record<string, { type?: string; enum?: string[]; description?: string }>
  }
  assert.equal(schema.type, 'object')
  assert.equal(schema.additionalProperties, false)
  assert.deepEqual(schema.required, ['id', 'source', 'enabled'])
  assert.deepEqual(schema.properties['source']?.enum, [...TASK_TRIGGER_SOURCES])
  assert.equal(schema.properties['params']?.type, 'object')
  assert.equal(schema.properties['filter']?.type, 'object')
  assert.equal(schema.properties['when']?.type, 'string')
  for (const variant of ['cron', 'daily', 'weekly', 'everySeconds', 'afterSeconds', 'at']) {
    assert.match(schema.properties['params']?.description ?? '', new RegExp(variant))
  }
})

test('tool contract: emitted examples parse as JSON and pass host validation', () => {
  assert.equal(TRIGGER_EXAMPLE_LINES.length, TRIGGER_EXAMPLES.length)
  for (const line of TRIGGER_EXAMPLE_LINES) {
    assert.match(line, /^- .+: \{/)
    const parsed = JSON.parse(line.slice(line.indexOf('{'))) as Record<string, unknown>
    validateTaskTriggers([parsed as never])
  }
  assert.ok(OPS_SAVE_TASK_TRIGGER_GUIDE.includes(TRIGGER_EXAMPLE_LINES[0]!))
})

test('tool contract: guide and prompt explain params, filter, and every schedule variant', () => {
  for (const text of [OPS_SAVE_TASK_TRIGGER_GUIDE, SAVE_PROMPT_TRIGGER_LINES.join('\n')]) {
    for (const source of TASK_TRIGGER_SOURCES) {
      assert.ok(text.includes(source), `missing trigger source ${source}`)
    }
    for (const variant of ['cron', 'daily', 'weekly', 'everySeconds', 'afterSeconds', 'at']) {
      assert.ok(text.includes(variant), `missing schedule variant ${variant}`)
    }
    assert.match(text, /everySeconds/)
    assert.match(text, /Monday=1|ISO weekdays/)
    assert.match(text, /is the trigger kind/)
    assert.match(text, /params/)
    assert.match(text, /filter/)
  }
})

test('tool contract: schedule rules stay under params and selectors under filter', () => {
  const prompt = SAVE_PROMPT_TRIGGER_LINES.join('\n')
  assert.match(prompt, /Schedule uses exactly one rule in `params`/)
  assert.match(prompt, /filewatch uses `filter\.path`/)
  assert.match(prompt, /exec uses `filter\.command`/)
  assert.match(prompt, /docker uses `filter\.container`/)
  assert.match(prompt, /journald uses `filter\.regex`/)
  assert.match(prompt, /webhook uses `filter\.token`/)
  // A prompt that collapsed the distinction into `source` would fail above.
  assert.doesNotMatch(prompt, /source is the (cron|path|command)/)
})
