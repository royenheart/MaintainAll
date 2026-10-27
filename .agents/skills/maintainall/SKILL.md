---
name: maintainall
description: Develop, test, debug, and produce the README demo for the MaintainAll DSH plugin. Use when changing plugin code, task assets, trigger behavior, the Ops panel, or the product demo, so the agent can start from the repository map and known invariants instead of re-reading the whole tree.
---

# MaintainAll project skill

Project-specific development knowledge for `@royenheart/dsh-plugin-maintainall`. General visual methods and the personal skill library live under `skills/`; this file is for working on this repository.

## Read first

- [Architecture](../../../docs/architecture.md) for runtime and persisted state.
- [Testing](../../../docs/testing.md) for the test policy and gaps.
- [Development](../../../docs/development.md) for build and profile setup.
- [README demo](../../../README.md#demo) for the current artifact.
- [Decision records](decisions/README.md) for historical choices; read only the relevant category, not the whole tree.

## Fast map

- `src/index.ts` — host Cordis service, HTTP routes, tools, save/edit/dispatch seams.
- `src/host/` — `TaskStateStore`, `ReplayRuntime`, and `TriggerRuntime`; runtime wiring, not the public route table.
- `src/client/` — Ops panel, save dialog, run history, and the client RPC helper.
- `src/core/` — pure contract, manifest, seed, storage, opskit, task writer, and trigger implementation; no dsh imports.
- `src/core/triggers/` — trigger events, filters, normalization, rate/debounce, and source implementations.
- `src/engine/` — trigger engine, listeners, schedule time, and state.
- `src/dispatch/` — run workspace, seed extraction, replay dispatch, save materialization, and lifecycle.
- `src/locales/` — symmetric `zh`/`en` dictionaries and keys.
- `tests/` — `node --test`; pure core and trigger tests do not need a harness.
- `preset/ops.patch.yml` — Ops agent preset.
- `.agents/skills/maintainall/decisions/` — historical decision records; read only the relevant category.
- `.agents/skills/` — project development skills such as this one.
- `skills/` — the personal general skill library, not the project plugin's catalog.

## Commands

Run from the repository root:

```sh
npm install
npm run build
npm test
npm run typecheck
npm run lint
```

Run the targeted test files for the module you touched rather than the full suite by default. Add or update a test when behavior changes.

## Invariants

- Trigger decisions are deterministic. The model never participates in a trigger decision.
- All trigger shapes, filters, schedule targets, ids, and uniqueness constraints validate before any save or edit.
- Storage writes are atomic. Do not write under `$DSH_HOME/sessions/`, `$DSH_HOME/profiles/`, or the plugin package directory.
- Client text is i18n-only with symmetric `zh`/`en` dictionaries.
- Registrations return disposers and release on unload and failed init.
- `src/core/` stays free of dsh imports.
- Use dsh extension points, never patch dsh internals.

## Demo production

The README demo is a **live evidence capture**, not a rebuilt motion film. It uses a scratch DSH home, the English light theme, a five-stage chapter rail, real model checks, a real saved task, and a real replay session. Read [the demo case](references/demo.md) before re-recording.

Key rules:

- Stage the rail before the capture and size it from the longest label; do not wrap labels.
- No decorative cursor, spinning dot, or free-floating focus frame.
- Type task fields at a readable pace; do not fill-and-submit in one frame.
- After Run once, enter the replay session immediately and stay there through the result.
- Record task id, run id, model, commit, and whether the artifact is live or rebuilt.
- No banner or launch film for the README; the GIF is the deliverable.

## Documentation

Update `docs/` for behavior and architecture. Update this skill when the repository map, commands, invariants, or demo recipe changes. Do not put project development instructions only in a personal skill.
