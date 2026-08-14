import { describe, it } from 'node:test'
import assert from 'node:assert/strict'

import {
  filterEnabledSkills,
  GLOBAL_SOURCES,
  identifySkills,
  isGlobalSource,
  isManagedSource,
  isSkillName,
  MANAGED_SOURCES,
  managedSkills,
  WORKSPACE_SOURCES,
} from '../src/core/skill-filter.ts'

const skills = [
  { name: 'project-skill', source: 'project-agents' },
  { name: 'dsh-skill', source: 'project-dsh' },
  { name: 'user-agent-skill', source: 'user-agents' },
  { name: 'user-dsh-skill', source: 'user-dsh' },
  { name: 'claude-skill', source: 'claude' },
  { name: 'codex-skill', source: 'codex' },
  { name: 'bundled-skill', source: 'bundled' },
  { name: 'runtime-skill', source: 'runtime' },
]

describe('isManagedSource', () => {
  it('accepts only .agents and dsh roots', () => {
    for (const source of MANAGED_SOURCES) assert.equal(isManagedSource(source), true, source)
    for (const source of ['claude', 'codex', 'bundled', 'runtime', 'custom', 'cursor']) {
      assert.equal(isManagedSource(source), false, source)
    }
  })
})

describe('isGlobalSource / source classification', () => {
  it('classifies user-level sources as global and project sources as workspace', () => {
    for (const source of GLOBAL_SOURCES) assert.equal(isGlobalSource(source), true, source)
    for (const source of WORKSPACE_SOURCES) assert.equal(isGlobalSource(source), false, source)
    // Both partitions together cover the managed set, nothing else.
    assert.deepEqual([...GLOBAL_SOURCES, ...WORKSPACE_SOURCES].sort(), [...MANAGED_SOURCES].sort())
  })

  it('rejects unmanaged sources as non-global', () => {
    for (const source of ['bundled', 'runtime', 'custom', 'claude', 'codex']) {
      assert.equal(isGlobalSource(source), false, source)
    }
  })
})

describe('isSkillName', () => {
  it('accepts kebab-case names', () => {
    for (const name of ['foo', 'foo-bar', 'a1', 'a-1-b']) assert.equal(isSkillName(name), true, name)
  })

  it('rejects non-kebab names', () => {
    for (const name of ['Foo', '-foo', 'foo-', 'foo--bar', 'foo_bar', 'foo.bar', '']) {
      assert.equal(isSkillName(name), false, JSON.stringify(name))
    }
  })
})

describe('identifySkills', () => {
  it('partitions managed vs ignored and sorts by name', () => {
    const { managed, ignored } = identifySkills(skills)
    assert.deepEqual(managed.map((s) => s.name), [
      'dsh-skill',
      'project-skill',
      'user-agent-skill',
      'user-dsh-skill',
    ])
    assert.deepEqual(ignored.map((s) => s.name), [
      'bundled-skill',
      'claude-skill',
      'codex-skill',
      'runtime-skill',
    ])
  })

  it('drops managed-source skills with invalid names', () => {
    const { managed } = identifySkills([
      { name: 'Bad_Name', source: 'project-agents' },
      { name: 'ok', source: 'project-agents' },
    ])
    assert.deepEqual(managed.map((s) => s.name), ['ok'])
  })
})

describe('managedSkills / filterEnabledSkills', () => {
  it('managedSkills returns only recognised skills', () => {
    assert.deepEqual(managedSkills(skills).map((s) => s.name), [
      'dsh-skill',
      'project-skill',
      'user-agent-skill',
      'user-dsh-skill',
    ])
  })

  it('filterEnabledSkills applies the injected predicate', () => {
    const out = filterEnabledSkills(skills, (name) => name !== 'project-skill')
    assert.deepEqual(out.map((s) => s.name), ['dsh-skill', 'user-agent-skill', 'user-dsh-skill'])
  })
})
