import { describe, it } from 'node:test'
import assert from 'node:assert/strict'

import {
  dictionaries,
  interpolate,
  NAMESPACE,
  placeholdersOf,
  validateDictionaries,
} from '../src/locales/index.ts'
import { SKILL_MANAGER_KEYS } from '../src/locales/keys.ts'

describe('dictionaries', () => {
  it('ships both zh and en', () => {
    assert.ok(dictionaries.zh)
    assert.ok(dictionaries.en)
  })

  it('covers every declared key in both languages', () => {
    for (const key of SKILL_MANAGER_KEYS) {
      assert.ok(key in dictionaries.zh, `zh missing ${key}`)
      assert.ok(key in dictionaries.en, `en missing ${key}`)
    }
  })

  it('has no extra keys in either language', () => {
    const declared = new Set<string>(SKILL_MANAGER_KEYS)
    for (const key of Object.keys(dictionaries.zh)) assert.ok(declared.has(key), `zh extra ${key}`)
    for (const key of Object.keys(dictionaries.en)) assert.ok(declared.has(key), `en extra ${key}`)
  })

  it('is fully valid per validateDictionaries', () => {
    assert.deepEqual(validateDictionaries(dictionaries.zh, dictionaries.en), [])
  })
})

describe('placeholdersOf / interpolate', () => {
  it('extracts placeholder names', () => {
    assert.deepEqual(placeholdersOf('Inherited from {scope}'), ['scope'])
    assert.deepEqual(placeholdersOf('no placeholders'), [])
  })

  it('interpolates and leaves unknown placeholders verbatim', () => {
    assert.equal(interpolate('Hello {name}', { name: 'x' }), 'Hello x')
    assert.equal(interpolate('Hello {name}', {}), 'Hello {name}')
  })
})

describe('NAMESPACE', () => {
  it('is skills-manager', () => {
    assert.equal(NAMESPACE, 'skills-manager')
  })
})
