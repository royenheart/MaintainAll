# Proposal: a neutral Session-activation extension point in dsh

Status: proposed — prepared for the dsh project, not sent upstream yet; MaintainAll keeps a compatibility bridge until a neutral extension point exists
Upstream reference: dsh `0.2.1-rc.3` (local checkout used while writing this proposal)

## Problem

MaintainAll's continuation mode needs to activate a persisted Session from a host plugin without owning the resulting Agent's lifecycle. Two requirements conflict under the current surface:

- The plugin cannot call `ctx.agents.resume()` itself. Cordis traces a service call to the caller's context, so the Agent lifecycle would bind to the plugin fiber; unloading or reloading MaintainAll could cancel the user's source Session. The dsh agent tests pin this behavior (`packages/core/agent/tests/agent.spec.ts`, "delegates through the calling context").
- The lifecycle owner must therefore be the embedding composition (the Web Session controller or the SDK server), not any single feature plugin.

The only activation provider path visible today is `schedule/resolve-agent`, declared by the Schedule plugin:

- Its documented semantics are reminder-specific: "Restore a reminder's Session through its embedding's owning controller."
- The generated event matrix (`docs/event-producer-consumer.md`) lists Schedule as the dispatcher and the SDK `server` as the only listener.
- The Schedule subsystem docs say the embedding owns activation and the composition waits for its activation provider (`docs/subsystems/schedule.md`).
- The Web composition supplies the fallback through `sessionController`, while the SDK server registers its own handler.

MaintainAll currently calls that waterfall as a compatibility bridge, falling back to `sessionController.resolveAgent`. That works in the shipped Web composition, but it is not a general contract: the event belongs to the reminder domain, its name and listener matrix do not describe third-party consumers, and a plugin has no typed dependency on the event declaration.

## Proposal

Add one neutral, general-purpose Session-activation extension point to dsh, owned by the session/host domain rather than by Schedule.

Preferred shape:

- Declare a waterfall (neutral name, for example `session/resolve-agent`) in a session/host package:
  `session/resolve-agent(sessionId: SessionId, next: () => Promise<Agent>): Promise<Agent>`.
- Keep ownership with the embedding: the Web composition provides the `sessionController.resolveAgent` fallback, and the SDK server registers its handler. Providers own the resumed Agent's lifecycle for the same reason the Schedule provider does today.
- Convert `schedule/resolve-agent` into a thin compatibility alias that forwards to the neutral event, or keep it for one deprecation window while Schedule migrates. Schedule becomes a consumer like any other plugin.
- Publish the listener contract in the event matrix and the Session subsystem docs so external plugins can depend on it with a typed declaration.

Secondary option if a new event is too broad:

- Expose a documented host service (for example `sessionActivation.resolve(sessionId)`) whose implementation delegates to the embedding provider and returns an Agent without transferring ownership. The service interface would have to state that the caller must not retain the handle as its own.

Minimum viable fix for external consumers if neither is accepted:

- Document `schedule/resolve-agent` as a public cross-plugin compatibility contract, ship its type declaration in a package external plugins can depend on, and list third-party consumers in the event matrix. This is the weakest option because the event name keeps advertising reminder semantics.

## Impact on MaintainAll

- The compatibility bridge stays for now: live Agent reuse, `schedule/resolve-agent` when present, `sessionController.resolveAgent` fallback, fail closed without a provider. Its current docs are marked as compatibility, not as a general mechanism.
- When a neutral extension point ships, MaintainAll switches the bridge to that event/service, drops the Schedule coupling, and adds a typed dependency. The task asset schema does not change: `bindings.continueSession` is independent of how the Agent is activated.
- The bridge's fail-closed reason (`source_session_unavailable`) remains useful either way.

## Questions for dsh maintainers

1. Is `schedule/resolve-agent` intended to be consumable by non-Schedule host plugins, or is it reminder-internal?
2. Which package should own a neutral activation event/service if one is added: session, host, or agent?
3. Should a neutral provider return only the Agent, or also an ownership-neutral handle / retention contract for callers that keep the Session live across deliveries?
4. Can the Web and SDK providers register the neutral event/service as well as the Schedule event during a migration window?
5. Does the event matrix generator need an explicit "external consumer" annotation before third-party plugins may rely on an event?

## Related evidence

- `docs/event-producer-consumer.md` — generated producer/consumer matrix; `schedule/resolve-agent` is scheduled-owned with the SDK server listener.
- `docs/subsystems/schedule.md` — "The embedding owns activation"; provider composition and delivery semantics.
- `packages/schedule/schedule/src/index.ts` — the reminder-specific waterfall declaration.
- `packages/api/session-controller/src/agent.ts` — Web `resolveAgent` ownership, preset composition, and subagent/archived checks.
- `packages/core/agent/src/index.ts` and `packages/core/agent/tests/agent.spec.ts` — caller-fiber ownership of create/resume.
- `.agents/notes/implemented/architecture/2026-08-18-session-history-and-event-transport.md` — other host namespaces reuse `sessionController` resolution rather than keeping a second resolver.

## Revisit trigger

Re-check this proposal when a dsh update adds a session-activation service/event, changes the `schedule/resolve-agent` contract, or documents third-party event-consumer support. Until then the compatibility bridge is the deployed behavior.
