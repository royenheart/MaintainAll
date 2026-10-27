# AGENTS.md

MaintainAll is a DeepSeek Harness (dsh) plugin, `@royenheart/dsh-plugin-maintainall`: it turns a successful ops session into a reusable task asset and replays it into a new session when a deterministic trigger fires. This file covers the plugin implementation, task assets, and their tests.

Read [`.agents/skills/maintainall/SKILL.md`](.agents/skills/maintainall/SKILL.md) first, then [docs/architecture.md](docs/architecture.md) before changing `src/`.

## Repository layout

```
src/            host and client plugin entries; core/ is pure logic with no dsh imports
tests/          node --test unit tests (pure core and trigger engine)
preset/         ops agent preset bundle patch (ops.patch.yml)
docs/           architecture, testing, development
skills/         personal general skill library (not project API knowledge)
.agents/skills/ project development skills and decision records
deploy/daed/    daed deployment config + one-shot daed-init.py
```

## Commands

```sh
npm install       # node ^22.19 || >=24
npm run build     # tsdown host/client bundles plus tsc declarations
npm test          # node --test tests/core/*.test.ts tests/triggers/*.test.ts tests/client/*.test.ts tests/dispatch/*.test.ts tests/engine/*.test.ts
npm run typecheck # tsc --noEmit
npm run lint      # oxlint
```

## Conventions

- Language: all code, comments, prompts, user-facing messages, and documentation are written in English; only replies and reports to the user use the user's own language.
- Skill prose has no per-line word, character, or column limit. Keep paragraphs and list-item text on natural lines without manual wrapping to a fixed width; use newlines for Markdown structure and meaningful paragraph boundaries.
- Package is scoped `@royenheart/dsh-plugin-maintainall`; `@deepseek-ai/*` packages are peerDependencies only.
- ESM everywhere (`"type": "module"`). Host entry default-exports a Cordis service or `apply(ctx)`; client entry exports `inject` + `apply(ctx)` and renders with `React.createElement` (no JSX).
- `src/core/` imports no dsh packages and is unit-tested directly with `node --test`.
- Registrations return disposers and must be released on unload and failed init; client contributions use `ctx.effect`/`ctx.on`, while host route/tool disposers are tracked explicitly.
- Runtime updates go through dsh extension points (tools registry, client slots, RPC), never by patching dsh.
- Client text is i18n-only: register a locale namespace with symmetric `zh`/`en` dictionaries and bind it; hard-coded UI strings are not allowed.

## Storage

- Plugin data root: `$DSH_HOME/@royenheart/dsh-plugin-maintainall` with dsh-compatible home resolution (tilde expansion, blank as unset, absolute normalization).
- `ops/<task-id>/` holds task assets: `manifest.yml`, `AGENTS.md`, `.agents/skills/`, `scripts/`, `seed/session.jsonl`, `triggers.yml`, `runs/`.
- `storages/` holds plugin state as atomically written JSON files (`registry.json`, `trigger-state.json`, `run-map.json`), with `logs/` and `exports/` for generated files.
- Do not write under `$DSH_HOME/sessions/`, `$DSH_HOME/profiles/`, or the plugin package directory.

## Trigger engine (non-LLM)

Triggers are deterministic. The current source list, schedule selectors, filter contract, committed-target persistence, dispatch order, and teardown behavior are specified in [docs/architecture.md](docs/architecture.md). Standing orders: the LLM never participates in a trigger decision; CEL expressions may only read the event and whitelisted string/regex functions (`matches`, `startsWith`, `endsWith`, `contains`); validate every trigger shape, required source filter, and schedule first target, and keep trigger ids non-empty, non-reserved, and unique across tasks (webhook ids URL-safe), before any save/edit/tool write; all management routes except the token-authenticated webhook route apply `connection.requestRejection`; dispatch applies the manifest permission preset fail-closed and rolls back an unpublished Agent on post-create failure.

## Tests

- `tests/` is `node --test`, no harness runtime required for `src/core/` and trigger logic.
- Trigger source tests use fake emitters/streams; dispatch tests use fake `agents`/`sessions`; the full coverage policy and current gaps live in [docs/testing.md](docs/testing.md).
- A behavior change updates or adds targeted tests in the same change; run the files covering the touched module rather than the whole suite.

## Docs and Decisions

- Update `.agents/skills/maintainall/` when the repository map, commands, invariants, or demo recipe changes. Substantial decisions live under [`.agents/skills/maintainall/decisions/`](.agents/skills/maintainall/decisions/README.md); do not add routine release notes or a parallel decision tree.
- Root `AGENTS.md` carries standing orders only; architecture facts live in [docs/architecture.md](docs/architecture.md); testing policy in [docs/testing.md](docs/testing.md).
- Project development skills and decision records live under `.agents/skills/`; `skills/` is the personal general skill library, not the project API reference.
- Read `.agents/skills/maintainall/SKILL.md` before changing plugin behavior or re-recording the README demo.
- Document current state, not change history. Cross-reference with relative Markdown links, never bare prose.
