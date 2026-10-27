import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, readFile, readdir, stat } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { readFileSync, existsSync } from 'node:fs'
import { loadRegistryState } from '../../src/core/storage.ts'
import { readTaskAsset, writeTaskAsset } from '../../src/core/task-writer.ts'
import {
  manifestFromMeta,
  materializeTaskEdit,
  materializeTaskFromSave,
  seedFromSession,
  validateTaskTriggers,
} from '../../src/dispatch/save.ts'

function session(events: Array<{ type: string; seq: number; data?: unknown }>): {
  id: string
  header: { cwd: string }
  snapshotEvents(): Array<{ type: string; seq: number; data?: unknown }>
} {
  return { id: 'session-1', header: { cwd: '/home/user/ops/original' }, snapshotEvents: () => events }
}

test('manifestFromMeta builds a valid manifest', () => {
  const manifest = manifestFromMeta({
    id: 'check-disk',
    name: 'Check disk',
    description: 'Check disk usage',
    triggers: [],
    agentPresetHint: 'standard',
  })
  assert.equal(manifest.format, 'dsh-opskit/1')
  assert.equal(manifest.bindings?.agentPreset?.hint, 'standard')
})

test('manifestFromMeta rejects invalid id', () => {
  assert.throws(() => manifestFromMeta({ id: 'Bad Id', name: 'x', description: '', triggers: [] }), /invalid task id/)
})

test('seedFromSession cuts at boundary and filters non-durable events', () => {
  const result = seedFromSession(
    session([
      { type: 'session', seq: 0, data: {} },
      { type: 'turn/start', seq: 1, data: { turn: 1 } },
      { type: 'user/message', seq: 2, data: {} },
      { type: 'assistant/chunk', seq: 3, data: {} },
      { type: 'tool/call', seq: 4, data: { name: 'bash' } },
      { type: 'turn/end', seq: 5, data: {} },
      { type: 'user/message', seq: 6, data: {} },
    ]),
    5,
  )
  assert.equal(result.cwd, '/home/user/ops/original')
  assert.deepEqual(result.events.map((event) => event.type), ['turn/start', 'user/message', 'tool/call', 'turn/end'])
})

test('validateTaskTriggers rejects unsafe ids and malformed docker filters', () => {
  assert.throws(() => validateTaskTriggers([{ id: '__proto__', source: 'docker', enabled: true }]), /trigger id/)
  assert.throws(() => validateTaskTriggers([{ id: 'd1', source: 'docker', enabled: true, filter: { events: 'start' } }]), /docker filter.events/)
  assert.throws(() => validateTaskTriggers([{ id: 'd1', source: 'docker', enabled: true, filter: { container: 5 } }]), /docker filter.container/)
  assert.throws(() => validateTaskTriggers([{ id: 'w1', source: 'webhook', enabled: true, filter: {} }]), /webhook filter.token/)
})

test('materializeTaskEdit updates metadata but preserves the captured seed and taskMode', async () => {
  const root = await mkdtemp(join(tmpdir(), 'maintainall-edit-'))
  await writeTaskAsset(root, {
    manifest: {
      format: 'dsh-opskit/1',
      id: 'check-disk',
      name: 'Check disk',
      description: 'Old description',
      version: '0.1.0',
      taskMode: 'compact',
      icon: '📁',
      color: '#4f8cff',
    },
    agensMd: '# Old runbook',
    skills: new Map([['.agents/skills/check/SKILL.md', 'skill body']]),
    scripts: new Map([['scripts/check.sh', 'df -h']]),
    seed: { cwd: '/work/ops', events: [{ type: 'turn/start', seq: 0, data: { turn: 1 } }] },
    triggers: [{ id: 't1', source: 'schedule', params: { cron: '0 * * * *' }, enabled: true }],
  })

  const taskDir = await materializeTaskEdit(root, 'check-disk', {
    name: 'Check disk v2',
    description: 'New description',
    instructions: '# New runbook',
    icon: '⚡',
    color: '#34c77b',
    naturalPrompt: 'check disk every hour',
    triggers: [{ id: 't1', source: 'schedule', params: { cron: '5 * * * *' }, enabled: false }],
  })

  const asset = await readTaskAsset(root, 'check-disk')
  assert.equal(asset.manifest.name, 'Check disk v2')
  assert.equal(asset.manifest.taskMode, 'compact')
  assert.equal(asset.manifest.icon, '⚡')
  assert.equal(asset.manifest.color, '#34c77b')
  assert.equal(asset.manifest.naturalPrompt, 'check disk every hour')
  assert.equal(asset.agensMd, '# New runbook')
  assert.deepEqual(asset.seed, { cwd: '/work/ops', events: [{ type: 'turn/start', seq: 0, data: { turn: 1 } }] })
  assert.deepEqual(asset.skills, new Map([['.agents/skills/check/SKILL.md', 'skill body']]))
  assert.deepEqual(asset.scripts, new Map([['scripts/check.sh', 'df -h']]))
  assert.ok(existsSync(join(taskDir, 'seed', 'session.jsonl')))

  const registry = loadRegistryState(root)
  const record = registry.tasks['check-disk']
  assert.equal(record?.name, 'Check disk v2')
  assert.equal(record?.icon, '⚡')
  assert.equal(record?.color, '#34c77b')
  assert.equal(record?.enabled, false)
  assert.ok(readFileSync(join(taskDir, 'triggers.yml'), 'utf8').includes('5 * * * *'))

  await materializeTaskEdit(root, 'check-disk', {
    name: 'Check disk v3',
    description: 'Third description',
  })
  const preserved = await readTaskAsset(root, 'check-disk')
  assert.equal(preserved.manifest.icon, '⚡')
  assert.equal(preserved.manifest.color, '#34c77b')
  assert.equal(preserved.manifest.naturalPrompt, 'check disk every hour')
  assert.equal(preserved.manifest.taskMode, 'compact')
  assert.deepEqual(preserved.triggers, [{ id: 't1', source: 'schedule', params: { cron: '5 * * * *' }, enabled: false }])
})

test('materializeTaskFromSave writes the task asset and updates registry', async () => {
  const root = await mkdtemp(join(tmpdir(), 'maintainall-save-'))
  const sessions = {
    get: () => session([
      { type: 'turn/start', seq: 0, data: { turn: 1 } },
      { type: 'user/message', seq: 1, data: { content: 'check disk' } },
      { type: 'turn/end', seq: 2, data: {} },
    ]),
  }
  const taskDir = await materializeTaskFromSave(root, sessions, {
    sessionId: 'session-1',
    boundarySeq: 2,
    meta: {
      id: 'check-disk',
      name: 'Check disk',
      description: 'Check disk usage',
      triggers: [{ id: 't1', source: 'schedule', params: { cron: '0 * * * *' }, enabled: true }],
      instructions: 'Run df -h and report.',
    },
  })
  const statTask = await stat(taskDir)
  assert.equal(statTask.isDirectory(), true)
  const agens = await readFile(join(taskDir, 'AGENTS.md'), 'utf8')
  assert.match(agens, /Run df -h and report\./)
  const seedText = await readFile(join(taskDir, 'seed', 'session.jsonl'), 'utf8')
  assert.match(seedText, /"type":"session"/)
  assert.match(seedText, /"type":"turn\/start"/)
  assert.equal((await readdir(join(root, 'ops'))).length, 1)
})

test('materializeTaskFromSave rejects an invalid schedule trigger before writing', async () => {
  const root = await mkdtemp(join(tmpdir(), 'maintainall-save-invalid-'))
  const sessions = {
    get: () => session([
      { type: 'turn/start', seq: 0, data: { turn: 1 } },
      { type: 'turn/end', seq: 1, data: {} },
    ]),
  }
  await assert.rejects(
    () => materializeTaskFromSave(root, sessions, {
      sessionId: 'session-1',
      boundarySeq: 1,
      meta: {
        id: 'bad-schedule',
        name: 'Bad schedule',
        description: 'Bad schedule',
        triggers: [{
          id: 't1',
          source: 'schedule',
          params: { daily: { time: '25:00:00', time_zone: 'UTC' } },
          enabled: true,
        }],
      },
    }),
    /trigger t1: invalid local time/,
  )
  assert.equal(existsSync(join(root, 'ops', 'bad-schedule')), false)
  assert.deepEqual(loadRegistryState(root).tasks, {})
})

test('validateTaskTriggers rejects rules with no representable first target', () => {
  assert.throws(
    () => validateTaskTriggers([{
      id: 'never',
      source: 'schedule',
      params: { cron: { expression: '0 0 31 2 *', time_zone: 'UTC' } },
      enabled: true,
    }]),
    /no future fire time/,
  )
  assert.throws(
    () => validateTaskTriggers([{
      id: 'huge',
      source: 'schedule',
      params: { afterSeconds: Number.MAX_SAFE_INTEGER },
      enabled: true,
    }]),
    /Invalid time value/,
  )
})

test('materializeTaskFromSave accepts the new schedule selectors', async () => {
  const root = await mkdtemp(join(tmpdir(), 'maintainall-save-selectors-'))
  const sessions = {
    get: () => session([{ type: 'turn/start', seq: 0, data: { turn: 1 } }]),
  }
  const taskDir = await materializeTaskFromSave(root, sessions, {
    sessionId: 'session-1',
    boundarySeq: 0,
    meta: {
      id: 'daily-check',
      name: 'Daily check',
      description: 'Daily check',
      triggers: [{
        id: 't1',
        source: 'schedule',
        params: { daily: { time: '09:00:00', time_zone: 'Asia/Shanghai' } },
        enabled: true,
      }],
    },
  })
  assert.equal(existsSync(join(taskDir, 'triggers.yml')), true)
  const asset = await readTaskAsset(root, 'daily-check')
  assert.deepEqual(asset.triggers[0]?.params, {
    daily: { time: '09:00:00', time_zone: 'Asia/Shanghai' },
  })
})

test('materializeTaskFromSave refuses to overwrite an existing task id', async () => {
  const root = await mkdtemp(join(tmpdir(), 'maintainall-save-existing-'))
  const sessions = {
    get: () => session([{ type: 'turn/start', seq: 0, data: { turn: 1 } }]),
  }
  const request = {
    sessionId: 'session-1',
    boundarySeq: 0,
    meta: {
      id: 'existing-task',
      name: 'Existing',
      description: 'Keep me',
      triggers: [{ id: 't1', source: 'schedule' as const, params: { afterSeconds: 60 }, enabled: true }],
      instructions: 'do not replace',
    },
  }
  await materializeTaskFromSave(root, sessions, request)
  await assert.rejects(
    materializeTaskFromSave(root, sessions, { ...request, meta: { ...request.meta, name: 'Replacement' } }),
    /already exists/,
  )
  assert.match(await readFile(join(root, 'ops', 'existing-task', 'AGENTS.md'), 'utf8'), /do not replace/)
})

test('validateTaskTriggers rejects duplicate ids and missing required filters', () => {
  assert.throws(
    () => validateTaskTriggers([
      { id: 'dup', source: 'schedule', params: { afterSeconds: 60 }, enabled: true },
      { id: 'dup', source: 'schedule', params: { afterSeconds: 60 }, enabled: true },
    ]),
    /duplicate trigger id/,
  )
  assert.throws(
    () => validateTaskTriggers([{ id: 't1', source: 'filewatch', filter: {}, enabled: true }]),
    /filter\.path/,
  )
  assert.throws(
    () => validateTaskTriggers([{ id: 't1', source: 'exec', filter: {}, enabled: true }]),
    /filter\.command/,
  )
  assert.throws(
    () => validateTaskTriggers([{ id: 't1', source: 'webhook', filter: { token: 123456 }, enabled: true }]),
    /filter\.token/,
  )
})
