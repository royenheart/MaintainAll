import { test } from 'node:test'
import assert from 'node:assert/strict'

import { getJson, postJson, ROUTE_BASE } from '../../src/client/api.ts'

interface FetchCall {
  path: string
  init: RequestInit | undefined
}

/** Install a fetch stub for one test and always restore the global afterwards. */
async function withFetch(
  reply: (call: FetchCall) => Response,
  run: (calls: FetchCall[]) => Promise<void>,
): Promise<void> {
  const original = globalThis.fetch
  const calls: FetchCall[] = []
  globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    const call = { path: String(input), init }
    calls.push(call)
    return reply(call)
  }) as typeof fetch
  try {
    await run(calls)
  } finally {
    globalThis.fetch = original
  }
}

test('api: getJson bypasses the browser HTTP cache', async () => {
  await withFetch(
    () => new Response(JSON.stringify({ ok: true, tasks: [] }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }),
    async (calls) => {
      const response = await getJson(`${ROUTE_BASE}/tasks`)
      assert.deepEqual(await response.json(), { ok: true, tasks: [] })
      assert.equal(calls.length, 1)
      assert.equal(calls[0]?.path, `${ROUTE_BASE}/tasks`)
      assert.deepEqual(calls[0]?.init, { cache: 'no-store' })
    },
  )
})

test('api: every getJson request is issued with the cache bypass', async () => {
  await withFetch(
    () => new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }),
    async (calls) => {
      await getJson(`${ROUTE_BASE}/tasks`)
      await getJson(`${ROUTE_BASE}/logs?limit=200&offset=0`)
      assert.equal(calls.length, 2)
      for (const call of calls) assert.equal(call.init?.cache, 'no-store')
    },
  )
})

test('api: postJson keeps its POST contract', async () => {
  await withFetch(
    () => new Response('{"ok":true}', { status: 200 }),
    async (calls) => {
      assert.equal(await postJson(`${ROUTE_BASE}/triggers/task-a/disable`, {}), true)
      assert.equal(calls.length, 1)
      assert.equal(calls[0]?.init?.method, 'POST')
      assert.equal(calls[0]?.init?.body, '{}')
      assert.deepEqual(calls[0]?.init?.headers, { 'content-type': 'application/json' })
    },
  )
})

test('api: postJson reports a failed response without throwing', async () => {
  await withFetch(
    () => new Response('{"ok":false}', { status: 400 }),
    async () => {
      assert.equal(await postJson(`${ROUTE_BASE}/triggers/task-a/enable`, {}), false)
    },
  )
})
