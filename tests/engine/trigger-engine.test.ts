import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync, appendFileSync, readFileSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'

import type { TaskTrigger, TriggerEvent } from '../../src/core/contract.ts'
import {
  TriggerEngine,
  type EngineScheduler,
  type EngineTask,
  type ExecResult,
} from '../../src/engine/trigger-engine.ts'
import { loadTriggerStateFile } from '../../src/engine/state.ts'

// ---------------------------------------------------------------------------
// Fakes and helpers
// ---------------------------------------------------------------------------

function tempRoot(): string {
  return mkdtempSync(join(tmpdir(), 'maintainall-engine-'))
}

interface DispatchCall {
  taskId: string
  event: TriggerEvent
}

function fakeDispatch(): { calls: DispatchCall[]; dispatch: (taskId: string, event: TriggerEvent) => Promise<void> } {
  const calls: DispatchCall[] = []
  return {
    calls,
    dispatch: async (taskId, event) => {
      calls.push({ taskId, event })
    },
  }
}

interface FakeScheduler extends EngineScheduler {
  intervals: Array<{ fn: () => void; ms: number }>
  cleared: Array<NodeJS.Timeout | number>
}

function fakeScheduler(): FakeScheduler {
  const intervals: FakeScheduler['intervals'] = []
  const cleared: FakeScheduler['cleared'] = []
  return {
    intervals,
    cleared,
    setInterval(fn, ms) {
      intervals.push({ fn, ms })
      return intervals.length
    },
    clearInterval(handle) {
      cleared.push(handle)
    },
  }
}

/** Mutable clock: `clock.now` is the current instant. */
function fakeClock(start: string): { now: Date; set: (iso: string) => void; fn: () => Date } {
  const clock = {
    now: new Date(start),
    set(iso: string) {
      clock.now = new Date(iso)
    },
    fn: () => clock.now,
  }
  return clock
}

function trigger(partial: Partial<TaskTrigger> & Pick<TaskTrigger, 'id' | 'source'>): TaskTrigger {
  return { enabled: true, ...partial }
}

function task(taskId: string, triggers: TaskTrigger[]): EngineTask {
  return { taskId, triggers }
}

function readState(root: string): {
  version: 2
  triggers: Record<string, { lastFiredAt?: string; fireTimestamps: string[] }>
  schedules: Record<string, { scheduledAt: string; ruleKey: string; done?: boolean }>
  filewatch: Record<string, Record<string, { offset: number; inode?: number }>>
  exec: Record<string, { stdout?: string; stderr?: string; exitCode?: number }>
} {
  return JSON.parse(readFileSync(join(root, 'storages', 'trigger-state.json'), 'utf8'))
}

test('state: a pre-schedules trigger-state file loads with an empty map', () => {
  const root = tempRoot()
  mkdirSync(join(root, 'storages'), { recursive: true })
  writeFileSync(join(root, 'storages', 'trigger-state.json'), JSON.stringify({
    version: 1,
    triggers: { old: { fireTimestamps: [] } },
    filewatch: { '/old/path.log': { offset: 5 } },
    journald: {},
    exec: {},
  }))
  const state = loadTriggerStateFile(root)
  assert.equal(state.version, 2)
  assert.deepEqual(state.schedules, {})
  assert.deepEqual(state.triggers.old?.fireTimestamps, [])
  assert.deepEqual(state.filewatch, {})
})

// ---------------------------------------------------------------------------
// Schedule
// ---------------------------------------------------------------------------

test('schedule: fires once when due and advances the next fire instant', async () => {
  const root = tempRoot()
  const clock = fakeClock('2026-08-23T11:59:00.000Z')
  const { calls, dispatch } = fakeDispatch()
  const scheduler = fakeScheduler()
  const engine = new TriggerEngine({
    root,
    tasks: () => [
      task('disk-check', [
        trigger({ id: 'sched-1', source: 'schedule', params: { cron: '0 12 * * *' } }),
      ]),
    ],
    dispatch,
    now: clock.fn,
    scheduler,
  })
  await engine.start()

  // start() arms the 1s schedule tick plus the filewatch/exec poll ticks.
  assert.deepEqual(
    scheduler.intervals.map((i) => i.ms).sort((a, b) => a - b),
    [1000, 5000, 5000],
  )

  // Not due yet.
  await engine.onScheduleTick(new Date('2026-08-23T11:59:30.000Z'))
  assert.equal(calls.length, 0)

  // Due at noon UTC: fires exactly once.
  await engine.onScheduleTick(new Date('2026-08-23T12:00:00.000Z'))
  assert.equal(calls.length, 1)
  assert.equal(calls[0]!.taskId, 'disk-check')
  assert.equal(calls[0]!.event.source, 'schedule')
  assert.equal(calls[0]!.event.occurredAt, '2026-08-23T12:00:00.000Z')
  assert.equal(calls[0]!.event.payload.cron, '0 12 * * *')

  // Ticking again at the same instant does not re-fire.
  await engine.onScheduleTick(new Date('2026-08-23T12:00:00.000Z'))
  await engine.onScheduleTick(new Date('2026-08-23T12:00:45.000Z'))
  assert.equal(calls.length, 1)

  // The next fire advanced to the following day.
  await engine.onScheduleTick(new Date('2026-08-24T12:00:00.000Z'))
  assert.equal(calls.length, 2)
  assert.equal(calls[1]!.event.occurredAt, '2026-08-24T12:00:00.000Z')

  await engine.stop()
  assert.equal(scheduler.cleared.length, 3)
  await engine.onScheduleTick(new Date('2026-08-25T12:00:00.000Z'))
  assert.equal(calls.length, 2)
})

test('schedule: persisted target catches up once after a restart', async () => {
  const root = tempRoot()
  const sched = trigger({
    id: 'sched-persist',
    source: 'schedule',
    params: { cron: { expression: '0 12 * * *', time_zone: 'UTC' } },
  })
  const first = new TriggerEngine({
    root,
    tasks: () => [task('disk-check', [sched])],
    dispatch: async () => {},
    now: () => new Date('2026-08-23T11:59:00.000Z'),
    scheduler: fakeScheduler(),
  })
  await first.start()
  assert.equal(readState(root).schedules['sched-persist']?.scheduledAt, '2026-08-23T12:00:00.000Z')
  await first.stop()

  // The Host was down through the noon occurrence; the next start fires it once.
  const { calls, dispatch } = fakeDispatch()
  const second = new TriggerEngine({
    root,
    tasks: () => [task('disk-check', [sched])],
    dispatch,
    now: () => new Date('2026-08-23T12:05:00.000Z'),
    scheduler: fakeScheduler(),
  })
  await second.start()
  await second.onScheduleTick(new Date('2026-08-23T12:05:00.000Z'))
  assert.equal(calls.length, 1)
  assert.equal(calls[0]!.event.occurredAt, '2026-08-23T12:00:00.000Z')
  // The next target moves past the missed occurrence, not to 12:00 again.
  assert.equal(readState(root).schedules['sched-persist']?.scheduledAt, '2026-08-24T12:00:00.000Z')
  await second.onScheduleTick(new Date('2026-08-23T12:06:00.000Z'))
  assert.equal(calls.length, 1)
  await second.stop()
})

test('schedule: daily rule follows the IANA zone', async () => {
  const root = tempRoot()
  const clock = fakeClock('2026-08-23T00:00:00.000Z')
  const { calls, dispatch } = fakeDispatch()
  const engine = new TriggerEngine({
    root,
    tasks: () => [
      task('daily', [
        trigger({
          id: 'sched-daily',
          source: 'schedule',
          params: { daily: { time: '09:00:00', time_zone: 'Asia/Shanghai' } },
        }),
      ]),
    ],
    dispatch,
    now: clock.fn,
    scheduler: fakeScheduler(),
  })
  await engine.start()
  await engine.onScheduleTick(new Date('2026-08-23T00:00:00.000Z'))
  assert.equal(calls.length, 0)
  await engine.onScheduleTick(new Date('2026-08-23T01:00:00.000Z'))
  assert.equal(calls.length, 1)
  assert.equal(calls[0]!.event.occurredAt, '2026-08-23T01:00:00.000Z')
  assert.deepEqual(calls[0]!.event.payload.daily, {
    time: '09:00:00',
    timeZone: 'Asia/Shanghai',
  })
  await engine.stop()
})

test('schedule: every fires repeatedly and after fires exactly once', async () => {
  const root = tempRoot()
  const clock = fakeClock('2026-08-23T00:00:00.000Z')
  const { calls, dispatch } = fakeDispatch()
  const engine = new TriggerEngine({
    root,
    tasks: () => [
      task('interval', [
        trigger({ id: 'sched-every', source: 'schedule', params: { everySeconds: 60 } }),
      ]),
      task('delayed', [
        trigger({ id: 'sched-after', source: 'schedule', params: { afterSeconds: 120 } }),
      ]),
    ],
    dispatch,
    now: clock.fn,
    scheduler: fakeScheduler(),
  })
  await engine.start()
  await engine.onScheduleTick(new Date('2026-08-23T00:01:00.000Z'))
  assert.equal(calls.filter((call) => call.taskId === 'interval').length, 1)
  assert.equal(calls.filter((call) => call.taskId === 'delayed').length, 0)
  await engine.onScheduleTick(new Date('2026-08-23T00:02:00.000Z'))
  assert.equal(calls.filter((call) => call.taskId === 'interval').length, 2)
  assert.equal(calls.filter((call) => call.taskId === 'delayed').length, 1)
  await engine.onScheduleTick(new Date('2026-08-23T00:03:00.000Z'))
  assert.equal(calls.filter((call) => call.taskId === 'delayed').length, 1)
  assert.equal(readState(root).schedules['sched-after']?.done, true)
  await engine.stop()
})

test('schedule: absolute one-shot fires once and stays done across restart', async () => {
  const root = tempRoot()
  const sched = trigger({
    id: 'sched-at',
    source: 'schedule',
    params: { at: '2026-08-23T12:00:00Z' },
  })
  const first = new TriggerEngine({
    root,
    tasks: () => [task('one-shot', [sched])],
    dispatch: async () => {},
    now: () => new Date('2026-08-23T11:59:00.000Z'),
    scheduler: fakeScheduler(),
  })
  await first.start()
  await first.stop()

  const { calls, dispatch } = fakeDispatch()
  const second = new TriggerEngine({
    root,
    tasks: () => [task('one-shot', [sched])],
    dispatch,
    now: () => new Date('2026-08-23T12:00:00.000Z'),
    scheduler: fakeScheduler(),
  })
  await second.start()
  await second.onScheduleTick(new Date('2026-08-23T12:00:00.000Z'))
  assert.equal(calls.length, 1)
  assert.equal(calls[0]!.event.occurredAt, '2026-08-23T12:00:00.000Z')
  await second.stop()

  const third = new TriggerEngine({
    root,
    tasks: () => [task('one-shot', [sched])],
    dispatch,
    now: () => new Date('2026-08-24T12:00:00.000Z'),
    scheduler: fakeScheduler(),
  })
  await third.start()
  await third.onScheduleTick(new Date('2026-08-24T12:00:00.000Z'))
  assert.equal(calls.length, 1)
  await third.stop()
})

test('schedule: an injected resolver supplies the committed target', async () => {
  const root = tempRoot()
  const fired: string[] = []
  const engine = new TriggerEngine({
    root,
    tasks: () => [
      task('injected', [
        trigger({
          id: 'sched-injected',
          source: 'schedule',
          params: { cron: { expression: '* * * * *', time_zone: 'UTC' } },
        }),
      ]),
    ],
    dispatch: async () => {
      fired.push('dispatch')
    },
    now: () => new Date('2026-08-23T00:00:00.000Z'),
    scheduler: fakeScheduler(),
    scheduleTime: {
      first: () => '2026-08-23T00:01:00.000Z',
      next: () => '2026-08-23T00:02:00.000Z',
    },
  })
  await engine.start()
  await engine.onScheduleTick(new Date('2026-08-23T00:01:00.000Z'))
  assert.equal(fired.length, 1)
  assert.equal(readState(root).schedules['sched-injected']?.scheduledAt, '2026-08-23T00:02:00.000Z')
  await engine.stop()
})

test('schedule: invalid params fail loud at start', async () => {
  const engine = new TriggerEngine({
    root: tempRoot(),
    tasks: () => [
      task('broken', [
        trigger({
          id: 'sched-broken',
          source: 'schedule',
          params: { cron: { expression: 'not a cron', time_zone: 'UTC' } },
        }),
      ]),
    ],
    dispatch: async () => {},
    scheduler: fakeScheduler(),
  })
  await assert.rejects(() => engine.start(), /schedule trigger sched-broken/)
})

test('schedule: a reload during dispatch aborts the stale tick', async () => {
  const root = tempRoot()
  const clock = fakeClock('2026-08-23T00:00:00.000Z')
  const second = trigger({ id: 'sched-stale', source: 'schedule', params: { afterSeconds: 60 } })
  const tasks: EngineTask[] = [
    task('first', [trigger({ id: 'sched-first', source: 'schedule', params: { afterSeconds: 60 } })]),
    task('second', [second]),
  ]
  const calls: string[] = []
  let release: (() => void) | undefined
  let started: (() => void) | undefined
  const gate = new Promise<void>((resolve) => { release = resolve })
  const firstStarted = new Promise<void>((resolve) => { started = resolve })
  const engine = new TriggerEngine({
    root,
    tasks: () => tasks,
    now: clock.fn,
    scheduler: fakeScheduler(),
    dispatch: async (taskId) => {
      calls.push(taskId)
      if (taskId === 'first') {
        started?.()
        await gate
      }
    },
  })
  await engine.start()
  const tick = engine.onScheduleTick(new Date('2026-08-23T00:01:00.000Z'))
  await firstStarted
  second.params = { afterSeconds: 3600 }
  engine.reload()
  release?.()
  await tick
  assert.deepEqual(calls, ['first'])
  assert.equal(readState(root).schedules['sched-stale']?.done, undefined)
  assert.equal(readState(root).schedules['sched-stale']?.scheduledAt, '2026-08-23T01:00:00.000Z')
  await engine.stop()
})

test('schedule: every keeps its committed cadence on a late tick', async () => {
  const root = tempRoot()
  const clock = fakeClock('2026-08-23T00:00:00.000Z')
  const { calls, dispatch } = fakeDispatch()
  const engine = new TriggerEngine({
    root,
    tasks: () => [
      task('interval', [
        trigger({ id: 'sched-cadence', source: 'schedule', params: { everySeconds: 60 } }),
      ]),
    ],
    dispatch,
    now: clock.fn,
    scheduler: fakeScheduler(),
  })
  await engine.start()
  await engine.onScheduleTick(new Date('2026-08-23T00:01:30.000Z'))
  assert.equal(calls.length, 1)
  assert.equal(readState(root).schedules['sched-cadence']?.scheduledAt, '2026-08-23T00:02:00.000Z')
  await engine.stop()
})

// ---------------------------------------------------------------------------
// Filewatch
// ---------------------------------------------------------------------------

test('filewatch: emits new matching lines and respects debounce via rate limit', async () => {
  const root = tempRoot()
  const logPath = join(root, 'app.log')
  writeFileSync(logPath, 'ERROR pre-existing history\nINFO boot\n')

  const clock = fakeClock('2026-08-23T00:00:00.000Z')
  const { calls, dispatch } = fakeDispatch()
  const engine = new TriggerEngine({
    root,
    tasks: () => [
      task('log-watch', [
        trigger({
          id: 'fw-1',
          source: 'filewatch',
          filter: { path: 'app.log', regex: 'ERROR' },
          rate: { minIntervalSeconds: 60, maxPerHour: 100 },
        }),
      ]),
    ],
    dispatch,
    now: clock.fn,
    scheduler: fakeScheduler(),
  })
  await engine.start()

  // First poll is the baseline: pre-existing lines never emit.
  await engine.onFilewatchTick()
  assert.equal(calls.length, 0)

  // New lines: two ERROR lines match, one INFO line is filtered out.
  clock.set('2026-08-23T00:00:10.000Z')
  appendFileSync(logPath, 'INFO quiet\nERROR boom one\nERROR boom two\n')
  await engine.onFilewatchTick()

  // First matching line dispatches; the second is inside the 60s debounce.
  assert.equal(calls.length, 1)
  assert.equal(calls[0]!.taskId, 'log-watch')
  assert.equal(calls[0]!.event.source, 'filewatch')
  assert.equal(calls[0]!.event.payload.path, logPath)
  assert.equal(calls[0]!.event.payload.line, 'ERROR boom one')

  // Offset advanced past everything; a later tick with no new data is quiet.
  clock.set('2026-08-23T00:01:30.000Z')
  await engine.onFilewatchTick()
  assert.equal(calls.length, 1)

  // After the debounce window a new matching line fires again.
  appendFileSync(logPath, 'ERROR boom three\n')
  await engine.onFilewatchTick()
  assert.equal(calls.length, 2)
  assert.equal(calls[1]!.event.payload.line, 'ERROR boom three')

  // The filewatch offset persisted to trigger-state.json.
  const state = readState(root)
  assert.ok((state.filewatch['fw-1']?.[logPath]?.offset ?? 0) > 0)
})

test('filewatch: forgetting a later trigger fences its in-flight batch', async () => {
  const root = tempRoot()
  const aPath = join(root, 'a.log')
  const bPath = join(root, 'b.log')
  writeFileSync(aPath, '')
  writeFileSync(bPath, '')

  let release: () => void = () => {}
  let entered: () => void = () => {}
  const gate = new Promise<void>((resolve) => { release = resolve })
  const started = new Promise<void>((resolve) => { entered = resolve })
  const calls: string[] = []
  const engine = new TriggerEngine({
    root,
    tasks: () => [
      task('a', [trigger({ id: 'fw-a', source: 'filewatch', filter: { path: aPath } })]),
      task('b', [trigger({ id: 'fw-b', source: 'filewatch', filter: { path: bPath } })]),
    ],
    dispatch: async (taskId, event) => {
      calls.push(`${taskId}:${String(event.payload.line)}`)
      if (taskId === 'a') {
        entered()
        await gate
      }
    },
    scheduler: fakeScheduler(),
  })
  await engine.start()
  await engine.onFilewatchTick()

  appendFileSync(aPath, 'a-new\n')
  appendFileSync(bPath, 'b-new\n')
  const tick = engine.onFilewatchTick()
  await started
  engine.forgetTriggers(['fw-b'])
  release()
  await tick

  assert.deepEqual(calls, ['a:a-new'])
  assert.equal(readState(root).filewatch['fw-b'], undefined)
  await engine.stop()
})

// ---------------------------------------------------------------------------
// Docker
// ---------------------------------------------------------------------------

const DIE_EVENT = JSON.stringify({
  type: 'container',
  action: 'die',
  status: 'die',
  actor: { Attributes: { name: 'web-1', exitCode: '137' } },
  time: 1787500000,
})

test('docker: source filter, CEL when, and dispatch', async () => {
  const root = tempRoot()
  const clock = fakeClock('2026-08-23T00:00:00.000Z')
  const { calls, dispatch } = fakeDispatch()
  const engine = new TriggerEngine({
    root,
    tasks: () => [
      task('restart-web', [
        trigger({
          id: 'dk-1',
          source: 'docker',
          filter: { events: ['die'], container: 'web-*' },
          when: 'payload.exitCode == 137',
        }),
      ]),
    ],
    dispatch,
    now: clock.fn,
    scheduler: fakeScheduler(),
  })
  await engine.start()

  // Malformed lines are ignored.
  await engine.onDockerEvent('not json')
  assert.equal(calls.length, 0)

  // Matching filter + when -> dispatch with the normalized event.
  await engine.onDockerEvent(DIE_EVENT)
  assert.equal(calls.length, 1)
  assert.equal(calls[0]!.taskId, 'restart-web')
  assert.equal(calls[0]!.event.source, 'docker')
  assert.equal(calls[0]!.event.occurredAt, new Date(1787500000 * 1000).toISOString())
  assert.equal(calls[0]!.event.payload.container, 'web-1')
  assert.equal(calls[0]!.event.payload.exitCode, 137)

  // CEL when rejects a clean exit.
  await engine.onDockerEvent(
    JSON.stringify({
      type: 'container',
      status: 'die',
      actor: { Attributes: { name: 'web-1', exitCode: '0' } },
    }),
  )
  assert.equal(calls.length, 1)

  // Source filter rejects a non-matching container name.
  await engine.onDockerEvent(
    JSON.stringify({
      type: 'container',
      status: 'die',
      actor: { Attributes: { name: 'db-1', exitCode: '137' } },
    }),
  )
  assert.equal(calls.length, 1)

  // Source filter rejects a non-matching event kind.
  await engine.onDockerEvent(
    JSON.stringify({
      type: 'container',
      status: 'start',
      actor: { Attributes: { name: 'web-1' } },
    }),
  )
  assert.equal(calls.length, 1)
})

// ---------------------------------------------------------------------------
// Journald
// ---------------------------------------------------------------------------

test('journald: unit/priority/regex filter selects entries', async () => {
  const root = tempRoot()
  const clock = fakeClock('2026-08-23T00:00:00.000Z')
  const { calls, dispatch } = fakeDispatch()
  const engine = new TriggerEngine({
    root,
    tasks: () => [
      task('nginx-alert', [
        trigger({
          id: 'jd-1',
          source: 'journald',
          filter: { unit: 'nginx.service', priority: 3, regex: 'error' },
        }),
      ]),
    ],
    dispatch,
    now: clock.fn,
    scheduler: fakeScheduler(),
  })
  await engine.start()

  await engine.onJournaldLine('not json')
  // Wrong unit.
  await engine.onJournaldLine(
    JSON.stringify({ _SYSTEMD_UNIT: 'ssh.service', PRIORITY: '3', MESSAGE: 'error happened' }),
  )
  // Too low severity (priority 6 > threshold 3).
  await engine.onJournaldLine(
    JSON.stringify({ _SYSTEMD_UNIT: 'nginx.service', PRIORITY: '6', MESSAGE: 'error happened' }),
  )
  // Message does not match the regex.
  await engine.onJournaldLine(
    JSON.stringify({ _SYSTEMD_UNIT: 'nginx.service', PRIORITY: '3', MESSAGE: 'all good' }),
  )
  assert.equal(calls.length, 0)

  // Full match, with __REALTIME_TIMESTAMP driving occurredAt.
  await engine.onJournaldLine(
    JSON.stringify({
      _SYSTEMD_UNIT: 'nginx.service',
      PRIORITY: '3',
      MESSAGE: 'upstream error connecting',
      __REALTIME_TIMESTAMP: '1787500000000000',
    }),
  )
  assert.equal(calls.length, 1)
  assert.equal(calls[0]!.taskId, 'nginx-alert')
  assert.equal(calls[0]!.event.source, 'journald')
  assert.equal(calls[0]!.event.occurredAt, new Date(1787500000000).toISOString())
  assert.equal(calls[0]!.event.payload.unit, 'nginx.service')
  assert.equal(calls[0]!.event.payload.priority, 3)
  assert.equal(calls[0]!.event.payload.message, 'upstream error connecting')
})

// ---------------------------------------------------------------------------
// Webhook
// ---------------------------------------------------------------------------

test('webhook: path and bearer token gate the dispatch', async () => {
  const root = tempRoot()
  const clock = fakeClock('2026-08-23T00:00:00.000Z')
  const { calls, dispatch } = fakeDispatch()
  const engine = new TriggerEngine({
    root,
    tasks: () => [
      task('deploy', [
        trigger({
          id: 'wh-1',
          source: 'webhook',
          filter: { path: '/hooks/deploy', token: 's3cret' },
        }),
      ]),
    ],
    dispatch,
    now: clock.fn,
    scheduler: fakeScheduler(),
  })
  await engine.start()

  const headers = { authorization: 'Bearer s3cret' }

  // Unknown trigger id.
  assert.equal(await engine.onWebhookRequest('nope', '/hooks/deploy', headers, '{}'), false)
  // Wrong path.
  assert.equal(await engine.onWebhookRequest('wh-1', '/hooks/other', headers, '{}'), false)
  // Missing and wrong tokens.
  assert.equal(await engine.onWebhookRequest('wh-1', '/hooks/deploy', {}, '{}'), false)
  assert.equal(
    await engine.onWebhookRequest('wh-1', '/hooks/deploy', { authorization: 'Bearer wrong' }, '{}'),
    false,
  )
  assert.equal(calls.length, 0)

  // Correct path + token dispatches and returns true.
  assert.equal(
    await engine.onWebhookRequest('wh-1', '/hooks/deploy', headers, '{"ref": "main"}'),
    true,
  )
  assert.equal(calls.length, 1)
  assert.equal(calls[0]!.taskId, 'deploy')
  assert.equal(calls[0]!.event.source, 'webhook')
  assert.equal(calls[0]!.event.payload.path, '/hooks/deploy')
  assert.deepEqual(calls[0]!.event.payload.body, { ref: 'main' })
})

// ---------------------------------------------------------------------------
// Exec
// ---------------------------------------------------------------------------

test('exec: fires on edges only (first observation, changed output/exit)', async () => {
  const root = tempRoot()
  const clock = fakeClock('2026-08-23T00:00:00.000Z')
  const { calls, dispatch } = fakeDispatch()
  const results: ExecResult[] = [
    { stdout: 'ok', stderr: '', exitCode: 0 },
    { stdout: 'ok', stderr: '', exitCode: 0 },
    { stdout: 'ok', stderr: 'warning noise', exitCode: 0 },
    { stdout: 'fail', stderr: '', exitCode: 1 },
  ]
  const commands: string[] = []
  const engine = new TriggerEngine({
    root,
    tasks: () => [
      task('probe', [trigger({ id: 'ex-1', source: 'exec', filter: { command: 'check-disk' } })]),
    ],
    dispatch,
    now: clock.fn,
    scheduler: fakeScheduler(),
    exec: async (command) => {
      commands.push(command)
      return results[Math.min(commands.length - 1, results.length - 1)]!
    },
  })
  await engine.start()

  // First observation is an edge.
  await engine.onExecTick()
  assert.equal(calls.length, 1)
  assert.deepEqual(commands, ['check-disk'])
  assert.equal(calls[0]!.event.source, 'exec')
  assert.equal(calls[0]!.event.payload.command, 'check-disk')
  assert.equal(calls[0]!.event.payload.stdout, 'ok')
  assert.equal(calls[0]!.event.payload.exitCode, 0)

  // Identical observation: no edge.
  await engine.onExecTick()
  assert.equal(calls.length, 1)

  // Stderr-only change: recorded but no edge.
  await engine.onExecTick()
  assert.equal(calls.length, 1)
  assert.equal(readState(root).exec['ex-1']!.stderr, 'warning noise')

  // Changed stdout + exit code: edge fires.
  await engine.onExecTick()
  assert.equal(calls.length, 2)
  assert.equal(calls[1]!.event.payload.stdout, 'fail')
  assert.equal(calls[1]!.event.payload.exitCode, 1)
})

// ---------------------------------------------------------------------------
// Rate limiting
// ---------------------------------------------------------------------------

test('rate limit: blocks a second firing inside the minimum interval', async () => {
  const root = tempRoot()
  const clock = fakeClock('2026-08-23T00:00:00.000Z')
  const { calls, dispatch } = fakeDispatch()
  const engine = new TriggerEngine({
    root,
    tasks: () => [
      task('restart-web', [
        trigger({
          id: 'dk-rate',
          source: 'docker',
          filter: { events: ['die'] },
          rate: { minIntervalSeconds: 300, maxPerHour: 10 },
        }),
      ]),
    ],
    dispatch,
    now: clock.fn,
    scheduler: fakeScheduler(),
  })
  await engine.start()

  await engine.onDockerEvent(DIE_EVENT)
  assert.equal(calls.length, 1)

  // One second later: blocked by the 300s minimum interval.
  clock.set('2026-08-23T00:00:01.000Z')
  await engine.onDockerEvent(DIE_EVENT)
  assert.equal(calls.length, 1)

  // Past the window: fires again.
  clock.set('2026-08-23T00:05:01.000Z')
  await engine.onDockerEvent(DIE_EVENT)
  assert.equal(calls.length, 2)

  // Hourly cap: maxPerHour 10 already holds 2 timestamps; burn the rest.
  const state = readState(root)
  assert.equal(state.triggers['dk-rate']!.fireTimestamps.length, 2)
})

test('rate limit: maxPerHour blocks when the rolling hour is full', async () => {
  const root = tempRoot()
  const clock = fakeClock('2026-08-23T00:00:00.000Z')
  const { calls, dispatch } = fakeDispatch()
  const engine = new TriggerEngine({
    root,
    tasks: () => [
      task('restart-web', [
        trigger({
          id: 'dk-cap',
          source: 'docker',
          filter: { events: ['die'] },
          rate: { minIntervalSeconds: 0, maxPerHour: 2 },
        }),
      ]),
    ],
    dispatch,
    now: clock.fn,
    scheduler: fakeScheduler(),
  })
  await engine.start()

  await engine.onDockerEvent(DIE_EVENT)
  clock.set('2026-08-23T00:00:01.000Z')
  await engine.onDockerEvent(DIE_EVENT)
  clock.set('2026-08-23T00:00:02.000Z')
  await engine.onDockerEvent(DIE_EVENT)
  assert.equal(calls.length, 2)

  // Rolling hour has elapsed: the cap frees up.
  clock.set('2026-08-23T01:00:03.000Z')
  await engine.onDockerEvent(DIE_EVENT)
  assert.equal(calls.length, 3)
})

// ---------------------------------------------------------------------------
// State persistence across restarts
// ---------------------------------------------------------------------------

test('state: rate limits and exec observations survive an engine restart', async () => {
  const root = tempRoot()
  const clock = fakeClock('2026-08-23T00:00:00.000Z')
  const tasks = () => [
    task('restart-web', [
      trigger({
        id: 'dk-persist',
        source: 'docker',
        filter: { events: ['die'] },
        rate: { minIntervalSeconds: 300, maxPerHour: 10 },
      }),
      trigger({ id: 'ex-persist', source: 'exec', filter: { command: 'check-disk' } }),
    ]),
  ]
  const execResult: ExecResult = { stdout: 'ok', stderr: '', exitCode: 0 }

  const first = fakeDispatch()
  const engine1 = new TriggerEngine({
    root,
    tasks,
    dispatch: first.dispatch,
    now: clock.fn,
    scheduler: fakeScheduler(),
    exec: async () => execResult,
  })
  await engine1.start()
  await engine1.onDockerEvent(DIE_EVENT)
  await engine1.onExecTick()
  assert.equal(first.calls.length, 2)
  await engine1.stop()

  assert.equal(existsSync(join(root, 'storages', 'trigger-state.json')), true)

  // A fresh engine over the same root restores rate + exec state.
  const second = fakeDispatch()
  const engine2 = new TriggerEngine({
    root,
    tasks,
    dispatch: second.dispatch,
    now: clock.fn,
    scheduler: fakeScheduler(),
    exec: async () => execResult,
  })
  await engine2.start()

  // Same docker event inside the debounce window: blocked.
  clock.set('2026-08-23T00:00:30.000Z')
  await engine2.onDockerEvent(DIE_EVENT)
  assert.equal(second.calls.length, 0)

  // Identical exec observation: no edge, no dispatch.
  await engine2.onExecTick()
  assert.equal(second.calls.length, 0)

  // Past the debounce window the docker trigger fires again.
  clock.set('2026-08-23T00:05:01.000Z')
  await engine2.onDockerEvent(DIE_EVENT)
  assert.equal(second.calls.length, 1)
})

// ---------------------------------------------------------------------------
// Reload
// ---------------------------------------------------------------------------

test('reload: picks up a newly enabled trigger', async () => {
  const root = tempRoot()
  const clock = fakeClock('2026-08-23T00:00:00.000Z')
  const { calls, dispatch } = fakeDispatch()

  const dockerTrigger = trigger({ id: 'dk-reload', source: 'docker', filter: { events: ['die'] } })
  dockerTrigger.enabled = false
  const tasks: EngineTask[] = [task('restart-web', [dockerTrigger])]

  const engine = new TriggerEngine({
    root,
    tasks: () => tasks,
    dispatch,
    now: clock.fn,
    scheduler: fakeScheduler(),
  })
  await engine.start()

  // Disabled trigger never fires.
  await engine.onDockerEvent(DIE_EVENT)
  assert.equal(calls.length, 0)

  // Enable it out of band; reload re-reads the task list.
  dockerTrigger.enabled = true
  engine.reload()
  await engine.onDockerEvent(DIE_EVENT)
  assert.equal(calls.length, 1)
  assert.equal(calls[0]!.taskId, 'restart-web')

  // Disabling + reload silences it again.
  dockerTrigger.enabled = false
  engine.reload()
  await engine.onDockerEvent(DIE_EVENT)
  assert.equal(calls.length, 1)
})

test('reload: recomputes schedule next-fire for changed cron expressions', async () => {
  const root = tempRoot()
  const clock = fakeClock('2026-08-23T11:59:00.000Z')
  const { calls, dispatch } = fakeDispatch()

  const sched = trigger({ id: 'sched-reload', source: 'schedule', params: { cron: '0 12 * * *' } })
  const tasks: EngineTask[] = [task('disk-check', [sched])]
  const engine = new TriggerEngine({
    root,
    tasks: () => tasks,
    dispatch,
    now: clock.fn,
    scheduler: fakeScheduler(),
  })
  await engine.start()

  sched.params = { cron: '30 13 * * *' }
  engine.reload()

  // Old fire time no longer applies.
  await engine.onScheduleTick(new Date('2026-08-23T12:00:00.000Z'))
  assert.equal(calls.length, 0)

  // New fire time does.
  await engine.onScheduleTick(new Date('2026-08-23T13:30:00.000Z'))
  assert.equal(calls.length, 1)
  assert.equal(calls[0]!.event.payload.cron, '30 13 * * *')
})
