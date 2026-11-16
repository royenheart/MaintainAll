import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { homedir, tmpdir } from 'node:os'
import { join } from 'node:path'
import {
  AtomicJsonFile,
  loadRegistryState,
  loadRunMapState,
  loadTriggerState,
  pluginDataRoot,
  saveRegistryState,
  saveRunMapState,
  saveTriggerState,
} from '../../src/core/storage.ts'

function tmpRoot(): string {
  return mkdtempSync(join(tmpdir(), 'maintainall-core-storage-'))
}

test('pluginDataRoot: honors DSH_HOME', () => {
  assert.equal(
    pluginDataRoot({ DSH_HOME: '/data/dsh' }),
    join('/data/dsh', '@royenheart', 'dsh-plugin-maintainall'),
  )
})

test('pluginDataRoot: falls back to ~/.dsh', () => {
  const root = pluginDataRoot({})
  assert.ok(root.endsWith(join('.dsh', '@royenheart', 'dsh-plugin-maintainall')), root)
})

test('AtomicJsonFile: write then read round-trips', () => {
  const file = new AtomicJsonFile<{ n: number }>(join(tmpRoot(), 'sub', 'state.json'))
  assert.equal(file.read(), undefined)
  file.write({ n: 42 })
  assert.deepEqual(file.read(), { n: 42 })
  file.write({ n: 7 })
  assert.deepEqual(file.read(), { n: 7 })
})

test('AtomicJsonFile: file mode 0o600 and directory mode 0o700', () => {
  const root = tmpRoot()
  const path = join(root, 'storages', 'state.json')
  new AtomicJsonFile(path).write({ ok: true })
  assert.equal(statSync(path).mode & 0o777, 0o600)
  assert.equal(statSync(join(root, 'storages')).mode & 0o777, 0o700)
})

test('AtomicJsonFile: corrupted JSON throws a clear error', () => {
  const path = join(tmpRoot(), 'broken.json')
  writeFileSync(path, '{ not json')
  assert.throws(() => new AtomicJsonFile(path).read(), /corrupted JSON state file/)
})

test('registry/trigger/run-map states: defaults when absent', () => {
  const root = tmpRoot()
  assert.deepEqual(loadRegistryState(root), { version: 1, tasks: {} })
  assert.deepEqual(loadTriggerState(root), {
    version: 2,
    triggers: {},
    schedules: {},
    filewatch: {},
    exec: {},
  })
  assert.deepEqual(loadRunMapState(root), { version: 1, runs: {} })
})

test('loadTriggerState: drops non-integer filewatch offsets', () => {
  const root = tmpRoot()
  saveTriggerState(root, {
    version: 2,
    triggers: {},
    schedules: {},
    filewatch: {
      t1: {
        '/var/log/app.log': { offset: 1.5 },
        '/var/log/ok.log': { offset: 2 },
      },
    },
    exec: {},
  })
  const state = loadTriggerState(root)
  assert.deepEqual(state.filewatch, { t1: { '/var/log/ok.log': { offset: 2 } } })
})

test('registry/trigger/run-map states: save and load round-trip', () => {
  const root = tmpRoot()
  saveRegistryState(root, {
    version: 1,
    tasks: {
      'restart-nginx': {
        id: 'restart-nginx',
        name: 'Restart nginx',
        version: '1.0.0',
        enabled: true,
        importedAt: '2026-08-23T00:00:00.000Z',
      },
    },
  })
  saveTriggerState(root, {
    version: 2,
    triggers: { t1: { fireTimestamps: [] } },
    schedules: {},
    filewatch: { t1: { '/var/log/app.log': { offset: 128 } } },
    exec: {},
  })
  saveRunMapState(root, {
    version: 1,
    runs: { r1: { taskId: 'restart-nginx', sessionId: 's1', cwd: '/tmp/r1', createdAt: 'now' } },
  })

  assert.equal(loadRegistryState(root).tasks['restart-nginx'].enabled, true)
  assert.equal(loadTriggerState(root).filewatch.t1!['/var/log/app.log']!.offset, 128)
  assert.equal(loadRunMapState(root).runs.r1.sessionId, 's1')
  // written under storages/ as plain JSON
  const raw = JSON.parse(readFileSync(join(root, 'storages', 'registry.json'), 'utf8'))
  assert.equal(raw.version, 1)
})

test('pluginDataRoot: expands tilde and whitespace like dsh home resolution', () => {
  assert.equal(pluginDataRoot({ DSH_HOME: '~/ops-home' }), join(homedir(), 'ops-home', '@royenheart', 'dsh-plugin-maintainall'))
  assert.equal(pluginDataRoot({ DSH_HOME: '   ' }), join(homedir(), '.dsh', '@royenheart', 'dsh-plugin-maintainall'))
})
