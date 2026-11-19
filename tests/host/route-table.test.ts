import test from 'node:test'
import assert from 'node:assert/strict'

import { buildRouteTable, type RouteHandlers, type RouteSpec } from '../../src/host/routes.ts'

const BASE = '/plugins/@royenheart/dsh-plugin-maintainall'

const noop: RouteHandlers['logs'] = () => {}

function handlers(): RouteHandlers {
  return { logs: noop, tasks: noop, save: noop, import: noop, export: noop, webhook: noop, triggers: noop }
}

function byPath(routes: RouteSpec[], suffix: string): RouteSpec | undefined {
  return routes.find((route) => route.path === `${BASE}/${suffix}`)
}

test('route table: every management route requires an admitted Peer', () => {
  const routes = buildRouteTable(BASE, handlers())
  const management = ['logs', 'tasks', 'save', 'import', 'export', 'triggers']
  for (const suffix of management) {
    const route = byPath(routes, suffix)
    assert.ok(route !== undefined, `missing route ${suffix}`)
    assert.equal(route.auth, 'required', `${suffix} must not be reachable without admission`)
  }
})

test('route table: the bearer-token webhook is the only anonymous route', () => {
  const routes = buildRouteTable(BASE, handlers())
  const anonymous = routes.filter((route) => route.auth === 'anonymous')
  assert.deepEqual(anonymous.map((route) => route.path), [`${BASE}/webhook`])
})

test('route table: paths and match kinds stay stable', () => {
  const routes = buildRouteTable(BASE, handlers())
  assert.deepEqual(
    routes.map((route) => `${route.kind} ${route.path.slice(BASE.length)}`),
    [
      'exact /logs',
      'prefix /tasks',
      'exact /save',
      'exact /import',
      'prefix /export',
      'prefix /webhook',
      'prefix /triggers',
    ],
  )
})

test('route table: handlers are registered as supplied', () => {
  const own = handlers()
  const routes = buildRouteTable(BASE, own)
  assert.equal(byPath(routes, 'logs')?.handler, own.logs)
  assert.equal(byPath(routes, 'webhook')?.handler, own.webhook)
})
