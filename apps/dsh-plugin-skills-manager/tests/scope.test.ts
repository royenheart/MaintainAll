import { describe, it } from 'node:test'
import assert from 'node:assert/strict'

import {
  allOverrideNames,
  disabledSkillNames,
  EMPTY_STORE,
  enabledSkillNames,
  explicitOverrides,
  resolveSkillState,
  scopeChain,
  withOverride,
  withoutOverride,
} from '../src/core/scope.ts'

const GLOBAL: { kind: 'global' } = { kind: 'global' }
const WORKSPACE = { kind: 'workspace' as const, key: '/ws/a' }
const SESSION = { kind: 'session' as const, key: 's1' }

describe('scopeChain', () => {
  it('is global-only for an empty view', () => {
    assert.deepEqual(scopeChain({}), [{ kind: 'global' }])
  })

  it('orders session > workspace > global', () => {
    assert.deepEqual(scopeChain({ workspacePath: '/ws/a', sessionId: 's1' }), [
      { kind: 'session', key: 's1' },
      { kind: 'workspace', key: '/ws/a' },
      { kind: 'global' },
    ])
  })
})

describe('resolveSkillState', () => {
  it('defaults to enabled when nothing overrides', () => {
    assert.deepEqual(resolveSkillState(EMPTY_STORE, 'foo', {}), {
      enabled: true,
      origin: 'default',
    })
  })

  it('honours the global override', () => {
    const data = withOverride(EMPTY_STORE, GLOBAL, 'foo', false)
    assert.deepEqual(resolveSkillState(data, 'foo', {}), { enabled: false, origin: 'global' })
    assert.deepEqual(resolveSkillState(data, 'bar', {}), { enabled: true, origin: 'default' })
  })

  it('lets a workspace override the global value', () => {
    let data = withOverride(EMPTY_STORE, GLOBAL, 'foo', false)
    data = withOverride(data, WORKSPACE, 'foo', true)
    assert.deepEqual(resolveSkillState(data, 'foo', { workspacePath: '/ws/a' }), {
      enabled: true,
      origin: 'workspace',
    })
    // a different workspace still inherits the global disable
    assert.deepEqual(resolveSkillState(data, 'foo', { workspacePath: '/ws/b' }), {
      enabled: false,
      origin: 'global',
    })
  })

  it('lets a session override workspace and global', () => {
    let data = withOverride(EMPTY_STORE, GLOBAL, 'foo', false)
    data = withOverride(data, WORKSPACE, 'foo', true)
    data = withOverride(data, SESSION, 'foo', false)
    assert.deepEqual(resolveSkillState(data, 'foo', { workspacePath: '/ws/a', sessionId: 's1' }), {
      enabled: false,
      origin: 'session',
    })
    // the same workspace without that session sees the workspace override
    assert.deepEqual(resolveSkillState(data, 'foo', { workspacePath: '/ws/a', sessionId: 's2' }), {
      enabled: true,
      origin: 'workspace',
    })
  })
})

describe('withOverride / withoutOverride', () => {
  it('is immutable and removes overrides cleanly', () => {
    const a = withOverride(EMPTY_STORE, GLOBAL, 'foo', false)
    assert.equal(a.global.get('foo'), false)
    assert.equal(EMPTY_STORE.global.size, 0)

    const b = withoutOverride(a, GLOBAL, 'foo')
    assert.equal(b.global.has('foo'), false)
    assert.equal(a.global.has('foo'), true)
  })

  it('keys workspace and session overrides separately', () => {
    let data = withOverride(EMPTY_STORE, WORKSPACE, 'foo', false)
    data = withOverride(data, SESSION, 'bar', true)
    assert.equal(data.workspaces.get('/ws/a')?.get('foo'), false)
    assert.equal(data.sessions.get('s1')?.get('bar'), true)
  })
})

describe('enabledSkillNames', () => {
  it('drops globally disabled skills', () => {
    const data = withOverride(EMPTY_STORE, GLOBAL, 'baz', false)
    assert.deepEqual(enabledSkillNames(data, ['foo', 'baz']), ['foo'])
  })

  it('re-enables a globally disabled skill at workspace scope', () => {
    let data = withOverride(EMPTY_STORE, GLOBAL, 'baz', false)
    data = withOverride(data, WORKSPACE, 'baz', true)
    assert.deepEqual(enabledSkillNames(data, ['foo', 'baz'], { workspacePath: '/ws/a' }), ['foo', 'baz'])
  })
})

describe('explicitOverrides', () => {
  it('returns the scope own decisions, sorted', () => {
    let data = withOverride(EMPTY_STORE, GLOBAL, 'zeta', true)
    data = withOverride(data, GLOBAL, 'alpha', false)
    assert.deepEqual([...explicitOverrides(data, GLOBAL).keys()], ['alpha', 'zeta'])
  })
})

describe('allOverrideNames / disabledSkillNames', () => {
  it('collects every overridden name across scopes, sorted', () => {
    let data = withOverride(EMPTY_STORE, GLOBAL, 'zeta', false)
    data = withOverride(data, WORKSPACE, 'alpha', true)
    data = withOverride(data, SESSION, 'mid', false)
    assert.deepEqual(allOverrideNames(data), ['alpha', 'mid', 'zeta'])
  })

  it('computes disabled names for a view through the override chain', () => {
    let data = withOverride(EMPTY_STORE, GLOBAL, 'a', false) // globally disabled
    data = withOverride(data, GLOBAL, 'b', true)              // globally enabled
    data = withOverride(data, WORKSPACE, 'a', true)           // workspace re-enables a
    data = withOverride(data, WORKSPACE, 'c', false)          // workspace disables c

    assert.deepEqual(disabledSkillNames(data, {}), ['a'])                 // global only
    assert.deepEqual(disabledSkillNames(data, { workspacePath: '/ws/a' }), ['c'])  // a re-enabled, c disabled
    assert.deepEqual(disabledSkillNames(data, { workspacePath: '/ws/b' }), ['a'])  // other workspace inherits global
  })

  it('resolves session overrides in disabledSkillNames', () => {
    let data = withOverride(EMPTY_STORE, GLOBAL, 'a', true)
    data = withOverride(data, SESSION, 'a', false)
    assert.deepEqual(disabledSkillNames(data, { sessionId: 's1' }), ['a'])
    assert.deepEqual(disabledSkillNames(data, { sessionId: 's2' }), [])
  })
})
