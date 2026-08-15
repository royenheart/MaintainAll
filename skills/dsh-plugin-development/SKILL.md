---
name: dsh-plugin-development
description: When to use — build, extend, or debug a DeepSeek Harness (dsh) plugin — the host/client entry split, cordis services, client slots/settings/locale, the apiproxy RPC, profiles and presets, packaging, loading, the develop→load→reload loop, or proposing a change to dsh itself.
---

# DSH plugin development

General reference for writing dsh plugins. It records durable conventions and gotchas — the *what / why*, not the *where* — so re-locate the current files by grepping the harness rather than relying on memorized paths.

## Locating the harness

1. If the user or the current session has named a local `deepseek-harness` checkout, first check that its `master` branch is aligned with upstream; if not, fetch and pull the latest `master` before relying on that checkout. Then read it.
2. Otherwise, analyze the **published package** — the `@deepseek-ai/dsh-*` packages under `node_modules` (what `npx @deepseek-ai/dsh …` runs) — rather than assuming a local source tree exists.

## Profile

dsh's user config lives under `$DSH_HOME` (default `~/.dsh`). A **profile** is a named configuration, each under `profiles/<name>/`, holding:

- `cordis.yml` — the profile's base plugin composition.
- `cordis.patch.yml` — a patch layer applied over it (id-targeted overrides, disables, and `insert` lists).
- `node_modules/` — plugins installed for this profile.

`$DSH_HOME/cordis.patch.yml` is a **home-level** patch applied over every profile. Pick a profile with `--profile <name>` (the GUI `web` profile is the common one). A profile is unrelated to a workspace/cwd.

## Preset

A **preset** is an agent-plane composition — the tools, prompt sections, and services that build one session's agent. It is orthogonal to a **profile**: a profile is process/host-plane (registries, sandbox, approval, persistence, model route), while a preset decides what each agent can do.

- Each preset is one agent-plane roster (named presets include `standard`, `code`, `minimal`, `cordis`, `online`), mounted once per process under a standing scope; every session naming it joins by scope parentage.
- A preset mounts its own per-agent copies (shell/filesystem tools, skills discovery + catalog loader, goals, plan mode, compaction, delegation/workflows); the host composition keeps the shared registries.
- Per-agent service rows sit inside a group carrying an `isolate` realm (entry-local = one private instance per mounted session).
- Use it by creating a session against a preset — `session.create({ agentPreset })`; the id is stored on the session header and resume rebuilds the same agent. The default is the user's stored choice, else the deployment default (`standard`).
- Manage presets through the `agentPreset.*` RPCs (list / select / read / copy / remove / openDocument).

## Package shape

- One plugin = one npm package. `package.json` carries `main`/`exports` (`.`, `./client`), a `dsh` block (host/client `inject`, `platform`), and `peerDependencies` against `@deepseek-ai/*`.
- Layout: `src/index.ts` (host entry), `src/client.ts` (client entry), `src/core/` (pure logic with no dsh imports → unit-testable with `node --test`), `src/locales/` (i18n dictionaries), `tests/`.
- Host entry: default-export a Cordis Service — `static inject = [...]`, `super(ctx, 'name')`, init in `async *[Service.init]()` — or a plain `apply(ctx)`.
- Client entry: `exports["./client"]` → `src/client.ts`, exporting `inject` (service names) + `apply(ctx)`; render with `React.createElement` (no JSX).

## Develop → load → reload loop

1. Edit host/client sources under `src/`.
2. Build + typecheck + test: `npm run build` (emits the host ESM and the CJS client bundle), `npx tsc --noEmit`, `npm test`.
3. Install into the active profile: `dsh plugin add link:<path>` (symlinks the package into the profile's `node_modules`).
4. Enable it: reference the plugin by its **bare package name** in a manifest file placed in the profile dir (same dir as `cordis.yml`), then add a `cordis:include` entry in `cordis.patch.yml` (profile- or home-level) pointing at that manifest.
5. Reload: restart dsh. (While `dev:web` runs from the same checkout, client bundles hot-reload without a page refresh.)

The client bundle is CJS wrapped in `window.__ModuleLoader__.load({ id, factory })`; `react` and `@deepseek-ai/*` imports are external (resolved from the loader's module table), relative imports are bundled.

## Client surfaces

- **Slots** — `ctx.slots.register({ name, id, order, label, inject }, Component)`. Kinds: `single` / `list` / `keyed` / `chain`; scope: `root` / `session-maybe` / `session`. Registering into an undeclared slot throws.
- **Locale** — `ctx.locale.register(ns, { zh, en })` then `ctx.locale.bind(ns)`; merge the key union into `LocaleNamespaceMap`.
- **Settings** — `ctx.settingsScope.bind({ namespace, decode })`; persist via the `settings.mutate` RPC. A third-party namespace must be in `exposedNamespaces()` or its writes are silently rejected.
- **RPC** — reach host domains through `ctx.get('connection').api.<domain>.<method>` (the apiproxy client face), not a custom transport.

## Host surfaces

- Provide a service with `super(ctx, 'name')` + `static inject`; read optional deps with `ctx.get('...')`.
- Register settings with a schema via `ctx.settings.register(ns, schema, { applies })`.

## Type & lint gotchas

- `exactOptionalPropertyTypes: true`: optional props need an explicit `| undefined`.
- CSS modules type as `Record<string, string>`; with `noUncheckedIndexedAccess`, `css.x` is `string | undefined` — pass it with `?? ''`, never `!` (`no-non-null-assertion` is a lint error in `src/**`).
- Render components with `React.createElement(Component, props)`, never `Component(props)` — calling the function misattributes hooks (React error #310).
- The pre-commit hook lints with `typeAware: false`, so a type-aware rule's `// oxlint-disable-next-line` shows as an "unused directive" warning there; it's harmless and still required for the type-aware CI gate.

## Proposing a change to dsh itself

A plugin should avoid forking the harness, but some needs (a slot, a wire field, a registry semantic) require a change to dsh. **The change must be general-purpose — reusable beyond the one plugin that needs it, never a bespoke seam for it — and must fit the dsh / cordis design philosophy (plugin-first composition, explicit typed boundaries, minimal API surface).** First **search the existing discussions** — dsh's GitHub Discussions and its Agent Notes tree — to check whether a similar proposal already exists; if so, build on it instead of duplicating.

For a new proposal, write a short discussion draft with this structure (sections only — mirror the existing drafts, don't hardcode them):

1. **Title** — `# [Feature request] <short summary>`.
2. **English summary** — a 1–2 sentence blockquote of the change and why.
3. **Background (the actual need I hit)** — what plugin you're building, its scopes, and the concrete problem.
4. **Current state** — quote the current code/comment/docs that explain the present behavior and why it's deliberate.
5. **Proposal** — the minimal change, and why it's safe.
6. **Appendix: patch** — the diff that implements it.
7. **Questions to confirm** — the open questions for maintainers.
8. **Related** — links to the docs and to related discussions/notes.
