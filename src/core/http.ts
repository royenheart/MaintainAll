/**
 * JSON response helper shared by the host route handlers.
 *
 * Every management response (task list, toggle result, run page, log page) is
 * live state. It must never be stored by a browser or an intermediary cache: a
 * cached task list keeps the Ops panel showing a stale enabled/disabled state
 * after a toggle. The risk is concrete on a deployment proxy, which may
 * classify `/plugins/<package>/*` as immutable static assets even though a
 * plugin's HTTP API can live under the same prefix. The client half also
 * bypasses the browser cache for its GETs; this header covers every other
 * consumer.
 */

import type { ServerResponse } from 'node:http'

/** Write one non-cacheable JSON response. */
export function sendJson(res: ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
  })
  res.end(JSON.stringify(body))
}
