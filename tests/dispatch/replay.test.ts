import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import { mkdtemp, readFile, readdir } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { dispatchReplay } from '../../src/dispatch/replay.ts'
import { writeTaskAsset } from '../../src/core/task-writer.ts'
import { loadRegistryState, loadRunMapState, saveRegistryState } from '../../src/core/storage.ts'

test('dispatchReplay creates a seeded session and persists run-map', async () => {
  const root = await mkdtemp(join(tmpdir(), 'maintainall-replay-'))
  const manifest = {
    format: 'dsh-opskit/1' as const,
    id: 'check-disk',
    name: 'Check disk',
    description: 'Check disk usage',
    version: '0.1.0',
    bindings: { agentPreset: { hint: 'ops' } },
  }
  await writeTaskAsset(root, {
    manifest,
    agensMd: 'Run df -h and report.',
    skills: new Map(),
    scripts: new Map(),
    seed: {
      cwd: '/home/user/ops/original',
      events: [
        { type: 'turn/start', seq: 0, data: { turn: 1 } },
        { type: 'user/message', seq: 1, data: { content: 'check disk' } },
        { type: 'turn/end', seq: 2, data: {} },
      ],
    },
    triggers: [{ id: 't1', source: 'schedule', params: { cron: '0 * * * *' }, enabled: true }],
  })
  const registry = loadRegistryState(root)
  registry.tasks['check-disk'] = {
    id: 'check-disk',
    name: 'Check disk',
    version: '0.1.0',
    enabled: true,
    importedAt: new Date().toISOString(),
  }
  saveRegistryState(root, registry)

  const created = { id: '', seed: [] as unknown[], meta: {} as Record<string, unknown>, followed: [] as unknown[] }
  const fakeAgents = {
    create: async (options: { sessionId: string; seed?: unknown[]; meta?: Record<string, unknown> }) => {
      created.id = options.sessionId
      created.seed = options.seed ?? []
      created.meta = options.meta ?? {}
      return {
        agent: {
          followup: (message: unknown) => { created.followed.push(message) },
        },
      }
    },
  }

  const result = await dispatchReplay({ agents: fakeAgents }, 'check-disk', {
    source: 'schedule',
    occurredAt: new Date().toISOString(),
    payload: { cron: '0 * * * *' },
  }, { root })

  assert.equal(result.ok, true)
  assert.match(created.id, /^session-/)
  assert.equal(created.meta.cwd?.toString().includes('runs'), true)
  assert.ok(created.seed.length > 0)
  assert.equal(created.followed.length, 1)
  const followup = created.followed[0] as { id?: string; role?: string; source?: { kind?: string } }
  assert.equal(followup.role, 'user')
  assert.equal(typeof followup.id, 'string')
  assert.notEqual(followup.id, '')
  assert.equal(followup.source?.kind, 'plugin:maintainall')

  const runMap = loadRunMapState(root)
  assert.equal(Object.keys(runMap.runs).length, 1)
  const run = Object.values(runMap.runs)[0]
  assert.equal(run?.taskId, 'check-disk')
  const runDir = run?.cwd
  assert.ok(runDir !== undefined && runDir.includes('runs'))
  assert.match(await readFile(join(runDir, 'AGENTS.md'), 'utf8'), /Run df -h and report\./)
  assert.equal(existsSync(join(runDir, '.agents/skills')), false)
})

test('dispatchReplay applies the permission preset and session title', async () => {
  const root = await mkdtemp(join(tmpdir(), 'maintainall-replay-preset-'))
  const manifest = {
    format: 'dsh-opskit/1' as const,
    id: 'restart-service',
    name: 'Restart service',
    description: 'Restart the service',
    version: '0.1.0',
    bindings: {
      agentPreset: { hint: 'ops' },
      permissionPreset: { hint: 'read-only' },
    },
  }
  await writeTaskAsset(root, {
    manifest,
    agensMd: 'Restart the service and verify.',
    skills: new Map(),
    scripts: new Map(),
    triggers: [],
  })
  const registry = loadRegistryState(root)
  registry.tasks['restart-service'] = {
    id: 'restart-service',
    name: 'Restart service',
    version: '0.1.0',
    enabled: true,
    importedAt: new Date().toISOString(),
  }
  saveRegistryState(root, registry)

  const session = { id: 'session-under-test' }
  const resolved: string[] = []
  const applied: Array<{ session: unknown; name: string }> = []
  const titles: string[] = []
  let created = false
  const fakeAgents = {
    create: async () => {
      created = true
      return {
        agent: {
          session,
          followup: () => {},
        },
        dispose: async () => {},
      }
    },
  }

  const result = await dispatchReplay({
    agents: fakeAgents,
    permissionPresets: {
      resolve(name: string) {
        resolved.push(name)
        return { name }
      },
      set(target: unknown, name: string) {
        applied.push({ session: target, name })
      },
    },
    sessionTitle: {
      rename(_target: unknown, title: string) {
        titles.push(title)
        return { title }
      },
    },
  }, 'restart-service', {
    source: 'schedule',
    occurredAt: '2026-08-23T12:00:00.000Z',
    payload: { cron: '0 12 * * *' },
  }, { root })

  assert.equal(result.ok, true)
  assert.equal(created, true)
  assert.deepEqual(resolved, ['read-only'])
  assert.deepEqual(applied, [{ session, name: 'read-only' }])
  assert.deepEqual(titles, ['Restart service · schedule'])
})

test('dispatchReplay rejects an unknown permission preset before creating a session', async () => {
  const root = await mkdtemp(join(tmpdir(), 'maintainall-replay-bad-preset-'))
  const manifest = {
    format: 'dsh-opskit/1' as const,
    id: 'bad-preset',
    name: 'Bad preset',
    description: 'Bad preset',
    version: '0.1.0',
    bindings: { permissionPreset: { hint: 'missing' } },
  }
  await writeTaskAsset(root, {
    manifest,
    agensMd: 'x',
    skills: new Map(),
    scripts: new Map(),
    triggers: [],
  })
  const registry = loadRegistryState(root)
  registry.tasks['bad-preset'] = {
    id: 'bad-preset',
    name: 'Bad preset',
    version: '0.1.0',
    enabled: true,
    importedAt: new Date().toISOString(),
  }
  saveRegistryState(root, registry)

  let created = false
  const result = await dispatchReplay({
    agents: {
      create: async () => {
        created = true
        return { agent: { followup: () => {} } }
      },
    },
    permissionPresets: {
      resolve() {
        throw new Error('unknown preset')
      },
      set() {},
    },
  }, 'bad-preset', {
    source: 'manual',
    occurredAt: new Date().toISOString(),
    payload: {},
  }, { root })

  assert.equal(result.ok, false)
  assert.match(result.error ?? '', /unknown permission preset/)
  assert.equal(created, false)
  assert.deepEqual(await readdir(join(root, 'ops', 'bad-preset', 'runs')), [])
})

test('dispatchReplay rolls back the created session when the first message fails', async () => {
  const root = await mkdtemp(join(tmpdir(), 'maintainall-replay-rollback-'))
  const manifest = {
    format: 'dsh-opskit/1' as const,
    id: 'rollback-task',
    name: 'Rollback task',
    description: 'Rollback task',
    version: '0.1.0',
  }
  await writeTaskAsset(root, {
    manifest,
    agensMd: 'x',
    skills: new Map(),
    scripts: new Map(),
    triggers: [],
  })
  const registry = loadRegistryState(root)
  registry.tasks['rollback-task'] = {
    id: 'rollback-task',
    name: 'Rollback task',
    version: '0.1.0',
    enabled: true,
    importedAt: new Date().toISOString(),
  }
  saveRegistryState(root, registry)

  let disposed = false
  const result = await dispatchReplay({
    agents: {
      create: async () => ({
        agent: {
          session: {},
          followup: () => {
            throw new Error('inbox unavailable')
          },
        },
        dispose: async () => {
          disposed = true
        },
      }),
    },
  }, 'rollback-task', {
    source: 'schedule',
    occurredAt: new Date().toISOString(),
    payload: {},
  }, { root })

  assert.equal(result.ok, false)
  assert.match(result.error ?? '', /inbox unavailable/)
  assert.equal(disposed, true)
  assert.deepEqual(loadRunMapState(root).runs, {})
  assert.deepEqual(await readdir(join(root, 'ops', 'rollback-task', 'runs')), [])
})

test('dispatchReplay fails closed when a declared permission preset has no service', async () => {
  const root = await mkdtemp(join(tmpdir(), 'maintainall-replay-no-preset-service-'))
  const manifest = {
    format: 'dsh-opskit/1' as const,
    id: 'no-preset-service',
    name: 'No preset service',
    description: 'No preset service',
    version: '0.1.0',
    bindings: { permissionPreset: { hint: 'read-only' } },
  }
  await writeTaskAsset(root, {
    manifest,
    agensMd: 'x',
    skills: new Map(),
    scripts: new Map(),
    triggers: [],
  })
  const registry = loadRegistryState(root)
  registry.tasks['no-preset-service'] = {
    id: 'no-preset-service',
    name: 'No preset service',
    version: '0.1.0',
    enabled: true,
    importedAt: new Date().toISOString(),
  }
  saveRegistryState(root, registry)

  let created = false
  const result = await dispatchReplay({
    agents: {
      create: async () => {
        created = true
        return { agent: { followup: () => {} } }
      },
    },
  }, 'no-preset-service', {
    source: 'manual',
    occurredAt: new Date().toISOString(),
    payload: {},
  }, { root })

  assert.equal(result.ok, false)
  assert.match(result.error ?? '', /permission preset service unavailable/)
  assert.equal(created, false)
})
