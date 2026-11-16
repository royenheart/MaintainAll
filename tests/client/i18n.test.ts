import { test } from 'node:test'
import assert from 'node:assert/strict'
import { MAINTAINALL_KEYS } from '../../src/locales/keys.ts'
import { zh } from '../../src/locales/zh.ts'
import { en } from '../../src/locales/en.ts'

/** Sorted, deduplicated `{placeholder}` names found in a template. */
function placeholdersOf(template: string): string[] {
  const seen = new Set<string>()
  const re = /\{([a-zA-Z0-9_]+)\}/g
  let match: RegExpExecArray | null
  while ((match = re.exec(template)) !== null) seen.add(match[1])
  return [...seen].sort()
}

test('zh and en cover exactly MAINTAINALL_KEYS', () => {
  const expected = [...MAINTAINALL_KEYS].sort()
  assert.deepEqual(Object.keys(zh).sort(), expected, 'zh keys')
  assert.deepEqual(Object.keys(en).sort(), expected, 'en keys')
})

test('zh and en have no empty values', () => {
  for (const key of MAINTAINALL_KEYS) {
    assert.ok(zh[key].trim() !== '', `zh["${key}"] is empty`)
    assert.ok(en[key].trim() !== '', `en["${key}"] is empty`)
  }
})

test('zh and en placeholders match per key', () => {
  for (const key of MAINTAINALL_KEYS) {
    assert.deepEqual(
      placeholdersOf(zh[key]),
      placeholdersOf(en[key]),
      `placeholder mismatch for "${key}"`,
    )
  }
})
