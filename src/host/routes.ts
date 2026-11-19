/**
 * Route table for the browser-facing management surface.
 *
 * dsh admits a plugin HTTP request at the route boundary: a route declares
 * `auth: 'required'`, and dsh's connection provider applies its Host/Origin
 * fence and verifies the browser Peer before the handler runs. Handlers
 * therefore never re-check admission themselves. The webhook is the one
 * anonymous route because its callers present a per-task bearer token rather
 * than a browser session, and its handler owns that check.
 */

import type { IncomingMessage, ServerResponse } from 'node:http'

/** Exact match or longest-prefix match under the web server's route tables. */
export type RouteKind = 'exact' | 'prefix'

/** Admission policy dsh enforces before a handler runs. */
export type RouteAuth = 'required' | 'anonymous'

/** One route handler; it owns the whole response lifecycle. */
export type RouteHandler = (req: IncomingMessage, res: ServerResponse) => void | Promise<void>

/** One registered route as dsh's web server consumes it. */
export interface RouteSpec {
  kind: RouteKind
  path: string
  auth: RouteAuth
  handler: RouteHandler
}

/** Handlers the management surface contributes, keyed by route purpose. */
export interface RouteHandlers {
  logs: RouteHandler
  tasks: RouteHandler
  save: RouteHandler
  import: RouteHandler
  export: RouteHandler
  webhook: RouteHandler
  triggers: RouteHandler
}

/**
 * Build the management route table for one route base.
 *
 * Every management route requires an admitted Peer; only the token-checked
 * webhook is anonymous. Keeping the policy in this table — rather than in a
 * handler wrapper — is what lets dsh reject an unauthenticated or cross-origin
 * request before a handler reads a body or mutates state.
 *
 * @param base - absolute route base without a trailing slash.
 * @param handlers - handlers owning each prefix.
 * @returns routes in registration order.
 */
export function buildRouteTable(base: string, handlers: RouteHandlers): RouteSpec[] {
  return [
    { kind: 'exact', path: `${base}/logs`, auth: 'required', handler: handlers.logs },
    { kind: 'prefix', path: `${base}/tasks`, auth: 'required', handler: handlers.tasks },
    { kind: 'exact', path: `${base}/save`, auth: 'required', handler: handlers.save },
    { kind: 'exact', path: `${base}/import`, auth: 'required', handler: handlers.import },
    { kind: 'prefix', path: `${base}/export`, auth: 'required', handler: handlers.export },
    { kind: 'prefix', path: `${base}/webhook`, auth: 'anonymous', handler: handlers.webhook },
    { kind: 'prefix', path: `${base}/triggers`, auth: 'required', handler: handlers.triggers },
  ]
}
