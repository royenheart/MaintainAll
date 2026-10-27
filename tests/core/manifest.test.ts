import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  computeChecksums,
  parseManifest,
  rewriteManifestForImport,
  sha256Hex,
  validateManifest,
} from '../../src/core/manifest.ts'
import type { TaskManifest } from '../../src/core/contract.ts'

const VALID_YAML = `
format: dsh-opskit/1
id: restart-nginx
name: Restart nginx
description: Restart nginx when the config changes
version: 1.2.3
requires:
  dsh: ">=0.1.0"
  tools: [bash, fs.read]
  mcpServers:
    - { name: docker, optional: true }
  secrets:
    - { name: api-token, env: API_TOKEN }
checksums:
  AGENTS.md: deadbeef
`

test('parseManifest: happy path parses and validates', () => {
  const manifest = parseManifest(VALID_YAML)
  assert.equal(manifest.format, 'dsh-opskit/1')
  assert.equal(manifest.id, 'restart-nginx')
  assert.equal(manifest.name, 'Restart nginx')
  assert.equal(manifest.version, '1.2.3')
  assert.deepEqual(manifest.requires?.tools, ['bash', 'fs.read'])
  assert.deepEqual(manifest.requires?.secrets, [{ name: 'api-token', env: 'API_TOKEN' }])
})

test('parseManifest: reads legacy taskMode auto as fresh', () => {
  assert.equal(parseManifest(`${VALID_YAML}\ntaskMode: auto\n`).taskMode, 'fresh')
})

test('parseManifest: rejects YAML that is not a mapping', () => {
  assert.throws(() => parseManifest('- just\n- a\n- list\n'), /invalid task manifest/)
})

test('validateManifest: rejects a bad id', () => {
  const base = { format: 'dsh-opskit/1', name: 'x', version: '1.0.0' }
  for (const id of ['', '-leading-hyphen', 'Upper', 'has_underscore', 'has space']) {
    assert.throws(() => validateManifest({ ...base, id }), /invalid task manifest: id/, id)
  }
})

test('validateManifest: rejects non-string metadata scalars', () => {
  const base = { format: 'dsh-opskit/1', id: 'ok', name: 'x', version: '1.0.0' }
  for (const field of ['icon', 'color', 'naturalPrompt'] as const) {
    assert.throws(() => validateManifest({ ...base, [field]: { bad: true } }), new RegExp(`invalid task manifest: ${field}`))
  }
})

test('validateManifest: rejects a bad format', () => {
  assert.throws(
    () =>
      validateManifest({
        format: 'dsh-opskit/2',
        id: 'ok',
        name: 'x',
        version: '1.0.0',
      }),
    /invalid task manifest: format/,
  )
})

test('validateManifest: rejects bad name and version', () => {
  const base = { format: 'dsh-opskit/1', id: 'ok', name: 'x', version: '1.0.0' }
  assert.throws(() => validateManifest({ ...base, name: '' }), /name/)
  assert.throws(() => validateManifest({ ...base, version: 'not-semver' }), /version/)
})

test('validateManifest: accepts minimal manifest and defaults description', () => {
  const manifest = validateManifest({
    format: 'dsh-opskit/1',
    id: 'ok',
    name: 'x',
    version: '0.1.0',
  })
  assert.equal(manifest.description, '')
})

test('computeChecksums: sha256 hex of each file content', () => {
  const files = new Map([
    ['AGENTS.md', 'hello'],
    ['scripts/run.sh', 'echo hi\n'],
  ])
  const checksums = computeChecksums(files)
  assert.deepEqual(Object.keys(checksums).sort(), ['AGENTS.md', 'scripts/run.sh'])
  assert.equal(checksums['AGENTS.md'], sha256Hex('hello'))
  assert.equal(
    checksums['AGENTS.md'],
    '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824',
  )
  assert.equal(checksums['scripts/run.sh'], sha256Hex('echo hi\n'))
})

test('rewriteManifestForImport: replaces bindings, keeps secrets, does not mutate input', () => {
  const manifest = parseManifest(VALID_YAML)
  manifest.bindings = { agentPreset: { hint: 'standard' }, permissionPreset: { hint: 'readonly' } }
  const before = JSON.parse(JSON.stringify(manifest)) as TaskManifest

  const rewritten = rewriteManifestForImport(manifest, {
    agentPreset: 'ops-local',
    permissionPreset: 'full',
  })

  assert.deepEqual(rewritten.bindings, {
    agentPreset: { hint: 'ops-local' },
    permissionPreset: { hint: 'full' },
  })
  assert.deepEqual(rewritten.requires?.secrets, [{ name: 'api-token', env: 'API_TOKEN' }])
  assert.deepEqual(manifest, before)
  assert.notEqual(rewritten, manifest)
})

test('rewriteManifestForImport: empty bindings drop the section', () => {
  const manifest = parseManifest(VALID_YAML)
  manifest.bindings = { agentPreset: { hint: 'standard' } }
  const rewritten = rewriteManifestForImport(manifest, {})
  assert.equal(rewritten.bindings, undefined)
})
