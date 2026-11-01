import { test } from 'node:test'
import assert from 'node:assert/strict'

import { sendJson } from '../../src/core/http.ts'

interface CapturedResponse {
  status?: number
  headers?: Record<string, unknown>
  body?: string
}

/** Minimal ServerResponse face: the helper only calls writeHead and end. */
function fakeResponse(captured: CapturedResponse): Parameters<typeof sendJson>[0] {
  return {
    writeHead(status: number, headers: Record<string, unknown>) {
      captured.status = status
      captured.headers = headers
      return this
    },
    end(body?: string) {
      captured.body = body
    },
  } as unknown as Parameters<typeof sendJson>[0]
}

test('http: sendJson writes the status, JSON body, and non-cacheable headers', () => {
  const captured: CapturedResponse = {}
  sendJson(fakeResponse(captured), 200, { ok: true, tasks: [{ id: 'task-a', enabled: false }] })

  assert.equal(captured.status, 200)
  assert.equal(captured.headers?.['content-type'], 'application/json; charset=utf-8')
  assert.equal(captured.headers?.['cache-control'], 'no-store')
  assert.deepEqual(JSON.parse(captured.body ?? ''), { ok: true, tasks: [{ id: 'task-a', enabled: false }] })
})

test('http: sendJson keeps error responses non-cacheable', () => {
  const captured: CapturedResponse = {}
  sendJson(fakeResponse(captured), 400, { ok: false, error: 'trigger toggle rejected' })

  assert.equal(captured.status, 400)
  assert.equal(captured.headers?.['cache-control'], 'no-store')
  assert.deepEqual(JSON.parse(captured.body ?? ''), { ok: false, error: 'trigger toggle rejected' })
})
