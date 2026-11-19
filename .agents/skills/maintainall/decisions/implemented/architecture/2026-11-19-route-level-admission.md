# Decision: route-level admission instead of a plugin-side connection fence

Status: implemented

## Problem

dsh 0.2.2-rc.3 removed `connection.requestRejection` from the connection service and moved request admission into the web server: a route declares an `auth` policy (`'required'` / `'anonymous'` / `'deny'`), and the `webserver/authorize` waterfall lets dsh's connection provider apply the Host/Origin fence and verify the browser Peer before the handler runs. MaintainAll still wrapped every management route in a fence that called `connection.requestRejection(req)`. That method no longer exists, so each `/plugins/@royenheart/dsh-plugin-maintainall/...` management request threw a `TypeError` inside the handler before reaching task logic; the Ops panel's `GET /tasks` received a non-OK response and rendered its generic `ops.error` alert ("任务操作失败。"). The plugin still loaded (its `ops_save_task` tool registered), which made the failure look like an install-time problem rather than an API break.

## Decision

- Route admission is declared, not implemented: `src/host/routes.ts` owns the whole table and marks every management route `auth: 'required'`.
- The webhook stays `auth: 'anonymous'` and keeps its own per-task bearer-token check; it is the only route whose callers do not present a browser session.
- Handlers no longer consult the `connection` service, and the host service drops `connection` from its injection list.
- `tests/host/route-table.test.ts` pins the policy split, paths, and match kinds without a live host.

## Alternatives considered

- Keep a plugin-side fence and feature-detect `requestRejection`: rejected because it duplicates dsh's admission logic, and a missing method would still fail after reading the request instead of before.
- Register the routes through `connection.fetch`: rejected because these are browser management routes with long-held responses and no RPC channel, and the web server's route table is the extension point dsh documents for that shape.
- Make the panel tolerate a failed load silently: rejected because it hides a broken deployment; the alert is the only signal a user gets.

## Consequences

- The admission contract follows dsh's extension point, so a future admission change lands in dsh's `webserver/authorize` and does not require a plugin edit.
- A missing or denied Peer now produces dsh's own 401/403/503 before the handler runs; the Ops panel shows `ops.error` only when the response is not a successful task list.
- The route table is the single place to add a route; adding one without an explicit `auth` policy fails the type check.
- `docs/architecture.md`, `.agents/skills/maintainall/SKILL.md`, and the root standing order describe the declared policy rather than the removed fence.
