import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, readFile, readdir, stat } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { readFileSync, existsSync } from 'node:fs'
import type { TaskManifest } from '../../src/core/contract.ts'
import { loadRegistryState } from '../../src/core/storage.ts'
import { readTaskAsset, writeTaskAsset } from '../../src/core/task-writer.ts'
import {
  assertReplayModeUnchanged,
  buildTaskSeed,
  manifestFromMeta,
  materializeTaskEdit,
  materializeTaskFromSave,
  replayModeOfManifest,
  seedFromSession,
  summarizeSessionSeed,
  validateContinuationCreation,
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

test('validateTaskTriggers: unsupported source explains the accepted trigger kinds', () => {
  assert.throws(
    () => validateTaskTriggers([{ id: 'bad', source: '*/30 * * * *' as never, enabled: true }]),
    (error: unknown) => {
      const message = (error as Error).message
      assert.match(message, /unsupported source/)
      for (const source of ['schedule', 'filewatch', 'docker', 'journald', 'webhook', 'exec']) {
        assert.ok(message.includes(source), `missing ${source}`)
      }
      assert.match(message, /params|filter/)
      return true
    },
  )
})

function oversizedSession(): {
  id: string
  header: { cwd: string }
  snapshotEvents(): Array<{ type: string; seq: number; data?: unknown }>
} {
  const reasoning = 'x'.repeat(17 * 1024 * 1024)
  return {
    id: 'session-big',
    header: { cwd: '/home/user/ops/original' },
    snapshotEvents: () => [
      { type: 'turn/start', seq: 1, data: { turn: 1 } },
      { type: 'assistant/message', seq: 2, data: { message: { content: [{ type: 'reasoning', text: reasoning }] } } },
      { type: 'turn/end', seq: 3, data: { turn: 1 } },
    ],
  }
}

test('buildTaskSeed: safe-copy overflow reports measured size, cap, and compact alternative', () => {
  const session = oversizedSession()
  const sizes = summarizeSessionSeed(session, 3)
  assert.equal(sizes.eventCount, 3)
  assert.ok(sizes.safeCopyBytes > 16 * 1024 * 1024)
  assert.ok(sizes.compactBytes < sizes.safeCopyBytes)
  assert.throws(
    () => buildTaskSeed(session, 3, 'safe-copy'),
    (error: unknown) => {
      const message = (error as Error).message
      assert.match(message, /seed is too large/)
      assert.ok(message.includes(String(sizes.safeCopyBytes)), 'reports the measured size')
      assert.ok(message.includes('16777216'), 'reports the cap')
      assert.match(message, /compact/)
      assert.match(message, /boundarySeq 3/)
      return true
    },
  )
  const compact = buildTaskSeed(session, 3, 'compact')
  assert.deepEqual(compact?.events.map((item) => item.type), ['turn/start', 'turn/end'])
  assert.equal(buildTaskSeed(session, 3, 'fresh'), undefined)
})

test('materializeTaskFromSave: an oversized safe-copy seed fails before the asset is written', async () => {
  const root = await mkdtemp(join(tmpdir(), 'maintainall-save-oversized-'))
  const sessions = { get: () => oversizedSession() }
  await assert.rejects(
    materializeTaskFromSave(root, sessions, {
      sessionId: 'session-big',
      boundarySeq: 3,
      meta: {
        id: 'oversized-watch',
        name: 'Oversized watch',
        description: 'Too large for safe-copy',
        taskMode: 'safe-copy',
        triggers: [{ id: 't1', source: 'schedule', params: { everySeconds: 1800 }, enabled: true }],
      },
    }),
    /seed is too large/,
  )
  assert.equal(existsSync(join(root, 'ops', 'oversized-watch')), false)
  // The preflight must run before writeTaskAsset creates its `ops/` staging
  // directory; a late rejection would leave that directory behind.
  assert.equal(existsSync(join(root, 'ops')), false)
  assert.deepEqual(loadRegistryState(root).tasks, {})
})

function paddedSession(textLength: number): {
  id: string
  header: { cwd: string }
  snapshotEvents(): Array<{ type: string; seq: number; data?: unknown }>
} {
  return {
    id: 'session-padded',
    header: { cwd: '/home/user/ops/original' },
    snapshotEvents: () => [
      { type: 'turn/start', seq: 1, data: { turn: 1 } },
      { type: 'user/message', seq: 2, data: { text: 'x'.repeat(textLength) } },
      { type: 'turn/end', seq: 3, data: { turn: 1 } },
    ],
  }
}

test('buildTaskSeed: accepts exactly the byte cap and rejects cap + 1', () => {
  const base = summarizeSessionSeed(paddedSession(0), 3)
  const padding = 16 * 1024 * 1024 - base.safeCopyBytes
  assert.ok(padding > 0)
  const exact = paddedSession(padding)
  assert.equal(summarizeSessionSeed(exact, 3).safeCopyBytes, 16 * 1024 * 1024)
  assert.equal(buildTaskSeed(exact, 3, 'safe-copy')?.events.length, 3)
  assert.throws(
    () => buildTaskSeed(paddedSession(padding + 1), 3, 'safe-copy'),
    /seed is too large/,
  )
})

test('buildTaskSeed: rejects an event-count overflow even when bytes fit', () => {
  const events: Array<{ type: string; seq: number; data?: unknown }> = [
    { type: 'turn/start', seq: 0, data: { turn: 1 } },
  ]
  for (let seq = 1; seq <= 100_000; seq += 1) {
    events.push({ type: 'step/start', seq, data: { turn: 1, step: seq } })
  }
  events.push({ type: 'turn/end', seq: 100_001, data: { turn: 1 } })
  const session = {
    id: 'session-many-events',
    header: { cwd: '/home/user/ops/original' },
    snapshotEvents: () => events,
  }
  assert.throws(
    () => buildTaskSeed(session, 100_001, 'safe-copy'),
    (error: unknown) => {
      const message = (error as Error).message
      assert.match(message, /too many events/)
      assert.match(message, /100002/)
      assert.match(message, /100000/)
      return true
    },
  )
})

test('buildTaskSeed: compact fits where safe-copy overflows and reports the compact size', () => {
  const session = oversizedSession()
  const summary = summarizeSessionSeed(session, 3)
  assert.ok(summary.compactBytes <= 16 * 1024 * 1024)
  const compact = buildTaskSeed(session, 3, 'compact')
  assert.ok(compact !== undefined)
  assert.equal(compact.cwd, '/home/user/ops/original')
  assert.throws(
    () => buildTaskSeed(session, 3, 'safe-copy'),
    (error: unknown) => {
      assert.ok((error as Error).message.includes(String(summary.compactBytes)))
      return true
    },
  )
})

test('materializeTaskFromSave: continuation stores the source session and writes no seed', async () => {
  const root = await mkdtemp(join(tmpdir(), 'maintainall-save-continuation-'))
  const sessions = {
    get: () => session([
      { type: 'turn/start', seq: 0, data: { turn: 1 } },
      { type: 'turn/end', seq: 1, data: { turn: 1 } },
    ]),
  }
  const taskDir = await materializeTaskFromSave(root, sessions, {
    sessionId: 'session-1',
    boundarySeq: 0,
    meta: {
      id: 'continue-watch',
      name: 'Continue watch',
      description: 'Watch in the source session',
      taskMode: 'fresh',
      continueSession: true,
      triggers: [{ id: 't1', source: 'schedule', params: { everySeconds: 1800 }, enabled: true }],
    },
  })
  const asset = await readTaskAsset(root, 'continue-watch')
  assert.equal(asset.manifest.taskMode, 'fresh')
  assert.deepEqual(asset.manifest.bindings, { continueSession: { sessionId: 'session-1' } })
  assert.equal(asset.seed, undefined)
  assert.equal(existsSync(join(taskDir, 'seed', 'session.jsonl')), false)
})

test('materializeTaskFromSave: continuation requires fresh mode and no preset bindings', async () => {
  const root = await mkdtemp(join(tmpdir(), 'maintainall-save-continuation-invalid-'))
  const sessions = { get: () => session([{ type: 'turn/start', seq: 0 }, { type: 'turn/end', seq: 1 }]) }
  const base = {
    id: 'continue-invalid',
    name: 'Continue invalid',
    description: 'Invalid continuation',
    continueSession: true,
    triggers: [{ id: 't1' as const, source: 'schedule' as const, params: { everySeconds: 60 }, enabled: true }],
  }
  await assert.rejects(
    materializeTaskFromSave(root, sessions, {
      sessionId: 'session-1',
      boundarySeq: 0,
      meta: { ...base, taskMode: 'safe-copy' },
    }),
    /taskMode 'fresh'/,
  )
  await assert.rejects(
    materializeTaskFromSave(root, sessions, {
      sessionId: 'session-1',
      boundarySeq: 0,
      meta: { ...base, taskMode: 'fresh', permissionPresetHint: 'readonly' },
    }),
    /cannot bind/,
  )
  assert.equal(existsSync(join(root, 'ops', 'continue-invalid')), false)
})

test('manifestFromMeta: continuation needs an explicit source session id', () => {
  assert.throws(
    () => manifestFromMeta({
      id: 'continue-meta',
      name: 'Continue meta',
      description: 'x',
      taskMode: 'fresh',
      continueSession: true,
      triggers: [],
    }),
    /source Session id/,
  )
  const manifest = manifestFromMeta({
    id: 'continue-meta',
    name: 'Continue meta',
    description: 'x',
    taskMode: 'fresh',
    continueSession: true,
    sourceSessionId: 'session-9',
    triggers: [],
  })
  assert.deepEqual(manifest.bindings, { continueSession: { sessionId: 'session-9' } })
})

test('validateContinuationCreation: fresh-only mode and no preset bindings', () => {
  assert.doesNotThrow(() => validateContinuationCreation({}))
  assert.doesNotThrow(() => validateContinuationCreation({ continueSession: false, taskMode: 'safe-copy' }))
  assert.doesNotThrow(() => validateContinuationCreation({ continueSession: true, taskMode: 'fresh' }))
  assert.throws(
    () => validateContinuationCreation({ continueSession: true, taskMode: 'safe-copy' }),
    /taskMode 'fresh'/,
  )
  assert.throws(
    () => validateContinuationCreation({ continueSession: true, taskMode: 'fresh', agentPresetHint: 'ops' }),
    /cannot bind/,
  )
  assert.throws(
    () => validateContinuationCreation({ continueSession: true, taskMode: 'fresh', permissionPresetHint: 'readonly' }),
    /cannot bind/,
  )
})

test('replay target helpers: detect and protect the creation-time target', () => {
  const fresh: TaskManifest = {
    format: 'dsh-opskit/1',
    id: 'fresh-task',
    name: 'Fresh',
    description: 'x',
    version: '0.1.0',
    taskMode: 'fresh',
  }
  const continued: TaskManifest = {
    ...fresh,
    id: 'continued-task',
    bindings: { continueSession: { sessionId: 'session-1' } },
  }
  assert.equal(replayModeOfManifest(fresh), 'new-session')
  assert.equal(replayModeOfManifest(continued), 'continue-session')
  assert.doesNotThrow(() => assertReplayModeUnchanged(fresh, undefined))
  assert.doesNotThrow(() => assertReplayModeUnchanged(fresh, 'new-session'))
  assert.throws(() => assertReplayModeUnchanged(fresh, 'continue-session'), /fixed at task creation/)
  assert.throws(() => assertReplayModeUnchanged(continued, 'new-session'), /fixed at task creation/)
})

test('materializeTaskFromSave: a continuation default runbook describes the source session, not a seed', async () => {
  const root = await mkdtemp(join(tmpdir(), 'maintainall-save-continuation-runbook-'))
  const sessions = { get: () => session([{ type: 'turn/start', seq: 0 }, { type: 'turn/end', seq: 1 }]) }
  await materializeTaskFromSave(root, sessions, {
    sessionId: 'session-1',
    boundarySeq: 0,
    meta: {
      id: 'continue-runbook',
      name: 'Continue runbook',
      description: 'Continue in the source session',
      taskMode: 'fresh',
      continueSession: true,
      triggers: [{ id: 't1', source: 'schedule', params: { everySeconds: 1800 }, enabled: true }],
    },
  })
  const asset = await readTaskAsset(root, 'continue-runbook')
  assert.match(asset.agensMd, /continues the source session/)
  assert.doesNotMatch(asset.agensMd, /replay seed context/)
})
