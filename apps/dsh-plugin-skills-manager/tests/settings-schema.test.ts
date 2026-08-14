import { describe, it } from 'node:test'
import assert from 'node:assert/strict'

import {
  fromStoreData,
  normalizeSection,
  overrideFieldFor,
  resetScopeInSection,
  SETTINGS_NAMESPACE,
  setOverrideInSection,
  setOverridesInSection,
  toStoreData,
} from '../src/core/settings-schema.ts'
import { withOverride } from '../src/core/scope.ts'

describe('normalizeSection', () => {
  it('returns empty for missing/foreign input', () => {
    assert.deepEqual(normalizeSection(undefined), { global: {}, workspaces: {}, sessions: {} })
    assert.deepEqual(normalizeSection(null), { global: {}, workspaces: {}, sessions: {} })
    assert.deepEqual(normalizeSection('x'), { global: {}, workspaces: {}, sessions: {} })
  })

  it('keeps boolean values and valid names across all scopes', () => {
    assert.deepEqual(normalizeSection({
      global: { foo: false, bar: true },
      workspaces: { '/ws/a': { baz: false } },
      sessions: { s1: { qux: true } },
    }), {
      global: { foo: false, bar: true },
      workspaces: { '/ws/a': { baz: false } },
      sessions: { s1: { qux: true } },
    })
  })

  it('drops non-boolean values and invalid names', () => {
    assert.deepEqual(normalizeSection({
      global: { good: true, bad_name: false, nope: 1 },
      workspaces: { '/ws/a': { 'bad/name': false, ok: true } },
    }), {
      global: { good: true },
      workspaces: { '/ws/a': { ok: true } },
      sessions: {},
    })
  })

  it('drops scoped entries whose overrides normalize to empty', () => {
    assert.deepEqual(normalizeSection({ workspaces: { '/ws/a': { bad_name: false } } }), {
      global: {},
      workspaces: {},
      sessions: {},
    })
  })
})

describe('store round-trip', () => {
  it('converts a section to store data and back losslessly', () => {
    const section = {
      global: { foo: false },
      workspaces: { '/ws/a': { bar: true } },
      sessions: { s1: { baz: false } },
    }
    const store = toStoreData(section)
    assert.equal(store.global.get('foo'), false)
    assert.equal(store.workspaces.get('/ws/a')?.get('bar'), true)
    assert.equal(store.sessions.get('s1')?.get('baz'), false)
    assert.deepEqual(fromStoreData(store), section)
  })

  it('an empty section maps to an empty store', () => {
    const store = toStoreData({})
    assert.equal(store.global.size, 0)
    assert.equal(store.workspaces.size, 0)
    assert.equal(store.sessions.size, 0)
  })
})

describe('SETTINGS_NAMESPACE', () => {
  it('is the stable namespace id', () => {
    assert.equal(SETTINGS_NAMESPACE, 'skills-manager')
  })
})

describe('overrideFieldFor / setOverrideInSection', () => {
  it('maps each scope kind to the right settings field', () => {
    assert.equal(overrideFieldFor('global'), 'global')
    assert.equal(overrideFieldFor('workspace'), 'workspaces')
    assert.equal(overrideFieldFor('session'), 'sessions')
  })

  it('writes a global override into the global field', () => {
    const { field, value } = setOverrideInSection({}, 'global', undefined, 'foo', false)
    assert.equal(field, 'global')
    assert.deepEqual(value, { foo: false })
  })

  it('writes a WORKSPACE override into the workspaces field (not sessions)', () => {
    const { field, value } = setOverrideInSection({}, 'workspace', '/ws/a', 'foo', true)
    assert.equal(field, 'workspaces')
    assert.deepEqual(value, { '/ws/a': { foo: true } })
  })

  it('writes a SESSION override into the sessions field', () => {
    const { field, value } = setOverrideInSection({}, 'session', 's1', 'foo', false)
    assert.equal(field, 'sessions')
    assert.deepEqual(value, { s1: { foo: false } })
  })

  it('merges into existing scope maps', () => {
    const section = { workspaces: { '/ws/a': { bar: true } } }
    const { field, value } = setOverrideInSection(section, 'workspace', '/ws/a', 'foo', false)
    assert.equal(field, 'workspaces')
    assert.deepEqual(value, { '/ws/a': { bar: true, foo: false } })
  })

  it('setOverridesInSection batches every name into one field value', () => {
    const { field, value } = setOverridesInSection({}, 'global', undefined, ['a', 'b', 'c'], false)
    assert.equal(field, 'global')
    assert.deepEqual(value, { a: false, b: false, c: false })
  })

  it('setOverridesInSection merges a batch into an existing scoped map', () => {
    const section = { workspaces: { '/ws/a': { keep: true } } }
    const { field, value } = setOverridesInSection(section, 'workspace', '/ws/a', ['x', 'y'], true)
    assert.equal(field, 'workspaces')
    assert.deepEqual(value, { '/ws/a': { keep: true, x: true, y: true } })
  })
})

describe('resetScopeInSection', () => {
  it('clears the whole global field', () => {
    const section = { global: { a: false } }
    const { field, value } = resetScopeInSection(section, 'global', undefined)
    assert.equal(field, 'global')
    assert.deepEqual(value, {})
  })

  it('removes only the named workspace, keeping others', () => {
    const section = { workspaces: { '/ws/a': { x: false }, '/ws/b': { y: false } } }
    const { field, value } = resetScopeInSection(section, 'workspace', '/ws/a')
    assert.equal(field, 'workspaces')
    assert.deepEqual(value, { '/ws/b': { y: false } })
  })

  it('removes only the named session, keeping others', () => {
    const section = { sessions: { s1: { x: false }, s2: { y: false } } }
    const { field, value } = resetScopeInSection(section, 'session', 's1')
    assert.equal(field, 'sessions')
    assert.deepEqual(value, { s2: { y: false } })
  })
})
