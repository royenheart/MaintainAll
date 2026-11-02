# Routes and authentication

A route that answers on loopback is still reachable by every process on the machine and
by a browser through a local proxy/SSH forward. Loopback is not authentication.

Check:

- how the route is registered (`ctx.webServer.register`, `registerUpgrade`,
  `createServer`, `router.*`, `listen`);
- whether it passes through the host's connection/session/token/cookie gate;
- whether it checks `Origin`/`Host` for browser callers;
- whether it reads or mutates session, files, or credentials;
- whether a raw route can be reached without a token, including after a redirect or
  error path;
- whether the protocol (HTTP/WS/RPC) is preserved when adding auth.

A scanner can only point at a candidate. Trace the actual handler and its middleware;
state when reachability is unverified.


## Multi-entrypoint matrix

For a host with several routes, upgrades, or client surfaces, produce one row per
entrypoint instead of a file-level finding:

| Route | Surface | Host auth | Chain to sink | Severity |
|---|---|---|---|---|

- `Host auth: yes` only when the route/handler passes through the host's
  `connection.requestRejection` (or an equivalent wrapper such as `gate`, `withGate`, `withHostGate`, or another explicit connection/session/token gate).
  `isLoopback`, `sameOriginOnly`, and an allowlist of dispatch keys are **not** host
  authentication.
- Follow a registry/dispatch map to the actual handler. `Chain` must list every hop:
  registration -> dispatch/registry -> handler -> dangerous sink, with file:line.
- `high` requires a dangerous sink with no visible host gate. A guarded route, an
  unimported dead module, or a local-only helper is at most `review` until reachability
  is shown.
- Run `node scripts/route-matrix.mjs <repo>` to enumerate candidate entrypoints, then
  verify each row by reading the handler. The script's "nearby guard" is not proof.

## Chain extraction (required for high)

A high route finding needs an explicit chain, not a file-level regex hit:

1. Find the registration call and the handler expression.
2. If the handler is a dispatch lookup (`registry.get(key)`, object map, router table),
   resolve the key to the actual handler in the same repo.
3. Follow wrappers (`gate`, `withGate`, `withHostGate`) and record whether they call
   `connection.requestRejection` on the request path before the handler.
4. Continue into the handler until a dangerous sink (`spawnSync`/`exec`, filesystem,
   credentials, network) or a guard.
5. Write each hop as `file:line` in order, for example:

```text
src/api/apply.ts:7 -> src/api/routes.ts:6 -> src/api/registry.ts:8 -> src/handlers/run.ts:4
```

If any hop cannot be shown from repo code, severity is `review`, not `high`, and the
missing hop goes in `notVerified`. An unguarded registration alone is not a high
finding. A nearby guard on another route is not a guard for this route.
