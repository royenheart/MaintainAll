import test from 'node:test'
import assert from 'node:assert/strict'

import { ReplayRuntime } from '../../src/host/replay-runtime.ts'
import type { ReplayAgentFace } from '../../src/dispatch/replay.ts'

type Waterfall = (name: string, ...args: unknown[]) => Promise<unknown>

interface FakeServices {
  services?: Record<string, unknown>
  waterfall?: Waterfall
}

function fakeCtx(input: FakeServices): never {
  return {
    get: (name: string) => input.services?.[name],
    ...(input.waterfall === undefined ? {} : { waterfall: input.waterfall }),
  } as never
}

function agent(
  id: string,
  header: { cwd?: string; agentPreset?: string; origin?: string; delegationDepth?: number } = {},
): ReplayAgentFace & { session: { header: Record<string, unknown> } } {
  return {
    session: { header: { id, cwd: '/home/user/project', ...header } },
    followup: () => {},
  }
}

/** A waterfall that calls no listener and only runs the supplied fallback. */
const noListeners: Waterfall = async (_name, ...args) => {
  const fallback = args.at(-1) as () => Promise<unknown>
  return fallback()
}

test('resolveSourceSession: reuses a live agent', async () => {
  const live = agent('session-live')
  const runtime = new ReplayRuntime(fakeCtx({
    services: { agents: { get: () => live } },
    waterfall: noListeners,
  }), { warn: () => {} })
  assert.equal((await runtime.resolveSourceSession('session-live')).agent, live)
})

test('resolveSourceSession: fails closed for an archived source session', async () => {
  const runtime = new ReplayRuntime(fakeCtx({
    services: {
      agents: { get: () => agent('session-archived') },
      workspaceRegistry: { archivedSessionIds: ['session-archived'] },
    },
    waterfall: noListeners,
  }), { warn: () => {} })
  await assert.rejects(runtime.resolveSourceSession('session-archived'), /archived/)
})

test('resolveSourceSession: refuses a live subagent-owned source session', async () => {
  const subagent = agent('session-child', { origin: 'subagent' })
  const runtime = new ReplayRuntime(fakeCtx({
    services: { agents: { get: () => subagent } },
    waterfall: noListeners,
  }), { warn: () => {} })
  await assert.rejects(runtime.resolveSourceSession('session-child'), /subagent routing/)
})

test('resolveSourceSession: activates a cold session through the waterfall handler', async () => {
  const activated = agent('session-cold')
  let receivedName = ''
  let receivedId = ''
  const runtime = new ReplayRuntime(fakeCtx({
    services: { agents: { get: () => undefined } },
    waterfall: async (name, ...args) => {
      receivedName = name
      receivedId = args[0] as string
      return activated
    },
  }), { warn: () => {} })
  const result = await runtime.resolveSourceSession('session-cold')
  assert.equal(receivedName, 'schedule/resolve-agent')
  assert.equal(receivedId, 'session-cold')
  assert.equal(result.agent, activated)
  assert.equal(result.handle, undefined)
})

test('resolveSourceSession: falls back to the Web controller when no waterfall handler exists', async () => {
  const resolved = agent('session-web')
  let received = ''
  const runtime = new ReplayRuntime(fakeCtx({
    services: {
      agents: { get: () => undefined },
      sessionController: {
        resolveAgent: async (sessionId: string) => {
          received = sessionId
          return { agent: resolved }
        },
      },
    },
    waterfall: noListeners,
  }), { warn: () => {} })
  const result = await runtime.resolveSourceSession('session-web')
  assert.equal(received, 'session-web')
  assert.equal(result.agent, resolved)
})

test('resolveSourceSession: fails closed when no activation provider exists', async () => {
  const runtime = new ReplayRuntime(fakeCtx({
    services: { agents: { get: () => undefined } },
    waterfall: noListeners,
  }), { warn: () => {} })
  await assert.rejects(
    runtime.resolveSourceSession('session-orphan'),
    /no Session activation provider/,
  )
})

test('resolveSourceSession: wraps a waterfall activation failure', async () => {
  const runtime = new ReplayRuntime(fakeCtx({
    services: { agents: { get: () => undefined } },
    waterfall: async () => { throw new Error('session persistence unavailable') },
  }), { warn: () => {} })
  await assert.rejects(
    runtime.resolveSourceSession('session-broken'),
    /cannot activate source session .*session persistence unavailable/,
  )
})

test('resolveSourceSession: reports a Web controller error', async () => {
  const runtime = new ReplayRuntime(fakeCtx({
    services: {
      agents: { get: () => undefined },
      sessionController: { resolveAgent: async () => ({ error: { message: 'session not found' } }) },
    },
    waterfall: noListeners,
  }), { warn: () => {} })
  await assert.rejects(runtime.resolveSourceSession('session-missing'), /session not found/)
})

test('resolveSourceSession: refuses a subagent Agent returned by an activation provider', async () => {
  const runtime = new ReplayRuntime(fakeCtx({
    services: { agents: { get: () => undefined } },
    waterfall: async () => agent('session-activated-child', { origin: 'subagent' }),
  }), { warn: () => {} })
  await assert.rejects(runtime.resolveSourceSession('session-activated-child'), /subagent routing/)
})

test('resolveSourceSession: fails closed without a waterfall-capable context', async () => {
  const runtime = new ReplayRuntime(fakeCtx({
    services: { agents: { get: () => undefined } },
  }), { warn: () => {} })
  await assert.rejects(runtime.resolveSourceSession('session-no-waterfall'), /no agent activation waterfall/)
})

test('resolveSourceSession: never creates or resumes an Agent through the plugin context', async () => {
  const activated = agent('session-provider-owned')
  let pluginOwnedCall = false
  const runtime = new ReplayRuntime(fakeCtx({
    services: {
      agents: {
        get: () => undefined,
        resume: () => { pluginOwnedCall = true; throw new Error('plugin-owned resume must not run') },
        create: () => { pluginOwnedCall = true; throw new Error('plugin-owned create must not run') },
      },
    },
    waterfall: async () => activated,
  }), { warn: () => {} })
  const result = await runtime.resolveSourceSession('session-provider-owned')
  assert.equal(result.agent, activated)
  assert.equal(result.handle, undefined)
  assert.equal(pluginOwnedCall, false)
})
