---
name: dsh-plugin-development
description: When to use — build, extend, or debug a DeepSeek Harness (dsh) plugin — plugin naming/scope rules, the host/client entry split, cordis services, client slots/settings/locale, the apiproxy RPC, profiles and presets, self-contained bundle packaging/loading, the develop→load→reload loop, or proposing a change to dsh itself.
---

# DSH plugin development

General reference for writing dsh plugins. It records durable conventions and gotchas — the *what / why*, not the *where* — so re-locate the current files by grepping the harness rather than relying on memorized paths.

## Locating the harness

1. If the user or the current session has named a local `deepseek-harness` checkout, first check that its `master` branch is aligned with upstream; if not, fetch and pull the latest `master` before relying on that checkout. Then read it.
2. Otherwise, analyze the **published package** — the `@deepseek-ai/dsh-*` packages under `node_modules` (what `npx @deepseek-ai/dsh …` runs) — rather than assuming a local source tree exists.

## Profile

dsh's user config lives under `$DSH_HOME` (default `~/.dsh`). A **profile** is a named composition under `profiles/<name>/`, holding:

- `package.json` — out-of-tree plugin `dependencies` plus the `dsh.profile` manifest with its ordered `bundles` list. `dsh plugin` maintains it; never write it by hand.
- `cordis.patch.yml` — the user's own patch layer (id-targeted whole-`config` overrides, disables, and `insert` lists). It is an override layer, not the mechanism a plugin loads through.
- `node_modules/` — plugins pnpm installed for this profile.

Layers apply over an empty entry list in order: each bundle patch in `dsh.profile.bundles` order, then the profile's `cordis.patch.yml`, then the home-level `$DSH_HOME/cordis.patch.yml`, then each `--patch` overlay. Pick a profile with `--profile <name>` (the GUI `web` profile is the common one). A profile is unrelated to a workspace/cwd.

## Preset

A **preset** is an agent-plane composition — the tools, prompt sections, and services that build one session's agent. It is orthogonal to a **profile**: a profile is process/host-plane (registries, sandbox, approval, persistence, model route), while a preset decides what each agent can do.

- Each preset is one agent-plane roster (named presets include `standard`, `code`, `minimal`, `cordis`, `online`), mounted once per process under a standing scope; every session naming it joins by scope parentage.
- A preset mounts its own per-agent copies (shell/filesystem tools, skills discovery + catalog loader, goals, plan mode, compaction, delegation/workflows); the host composition keeps the shared registries.
- Per-agent service rows sit inside a group carrying an `isolate` realm (entry-local = one private instance per mounted session).
- Use it by creating a session against a preset — `session.create({ agentPreset })`; the id is stored on the session header and resume rebuilds the same agent. The default is the user's stored choice, else the deployment default (`standard`).
- Manage presets through the `agentPreset.*` RPCs (list / select / read / copy / remove / openDocument).

## Package shape

- One plugin = one npm package, named under a user scope: when no scope is explicitly specified, default to the current user's git config `user.name` — `@<git-user.name>/dsh-plugin-<name>`. **Never use the `@deepseek-ai/*` scope for a third-party plugin** — it is reserved for the harness's own packages. Depending on `@deepseek-ai/*` via `peerDependencies` is expected; the reserved-scope rule is about the plugin's own package name.
- `package.json` carries `main`/`exports` (`.`, `./client`), a `dsh` block — `dsh.bundle.patch` pointing at the package's own `cordis.patch.yml`, plus optional `dsh.client` (`platform`, `inject`, `immediately`) — a `files` list that ships every built entry and `cordis.patch.yml`, and `peerDependencies` against `@deepseek-ai/*`.
- The package's `cordis.patch.yml` inserts its own host row by package name (never a relative source path), so Node resolution finds the installed code.
- Layout: `src/index.ts` (host entry), `src/client.ts` (client entry), `src/core/` (pure logic with no dsh imports → unit-testable with `node --test`), `src/locales/` (i18n dictionaries), `tests/`.
- Host entry: default-export a Cordis Service — `static inject = [...]`, `super(ctx, 'name')`, init in `async *[Service.init]()` — or a plain `apply(ctx)`.
- Client entry: `exports["./client"]` → `src/client.ts`, exporting `inject` (service names) + `apply(ctx)`; render with `React.createElement` (no JSX).

## Constraints

- **Naming.** Third-party plugin packages are scoped: when no scope is explicitly specified, default to the current user's git config `user.name` — `@<git-user.name>/dsh-plugin-<name>`. `@deepseek-ai/*` is reserved for the harness and must never be a plugin's own scope.
- **Self-contained loading.** A plugin must declare `dsh.bundle.patch` pointing at its own `cordis.patch.yml`, whose `insert` lists the package's host row by package name. `dsh plugin add <spec>` automatically appends any installed dependency that declares `dsh.bundle` to the profile's `dsh.profile.bundles` — never hand-edit the profile's `cordis.patch.yml`, `cordis.yml`, or a `cordis:include` manifest just to load a plugin. Profile/home patches remain user override layers.
- **Bundle-less packages are libraries.** A package without `dsh.bundle` still installs but activates no layer (dsh warns); reserve that shape for libraries plugins import, not for plugins.
- **Ship runnable artifacts.** `files` must include the built host/client entries and `cordis.patch.yml`. Git installs fetch sources, not build output: ship a self-contained `prepare` script that builds the published entries without dev-only assumptions, or distribute built artifacts (npm / tarball). A user allowlisting a git `prepare` is permitting install-time code, so they should pin a commit.
- **Whole-row patches.** A later patch replaces a row's entire `config` by id — when overriding, restate every retained key. Users can override your rows in their profile patch without touching your package, so prefer configuration defaults they will keep.
- **Client manifest matches the built bundle.** `dsh.client.platform` must be `'web'`; `exports["./client"]` must point at the built client bundle; `dsh.client.inject` edges are informational (preflight display / HMR diffing), not activation order — activation waits on service injection only.
- **Pure core.** `src/core/` imports no dsh package, so `node --test` exercises the logic directly.
- **No harness forks for one plugin.** When a need crosses the plugin surface, follow the general-purpose proposal path below instead of patching or forking dsh ad hoc.

## Develop → load → reload loop

1. Edit host/client sources under `src/`.
2. Build + typecheck + test: `npm run build` (emits the host ESM and the CJS client bundle), `npx tsc --noEmit`, `npm test`.
3. Install and load: `dsh plugin --profile <name> add link:<path>` (symlinks the package into the profile's `node_modules`). Because the package declares `dsh.bundle`, dsh appends it to the profile's `dsh.profile.bundles` and its own `cordis.patch.yml` inserts the host row — the plugin is self-contained, with no manual profile patch or manifest edit. Remove it with `dsh plugin --profile <name> remove <package>` (dependency and layer together).
4. Reload: restart dsh. (While `dev:web` runs from the same checkout, client bundles hot-reload without a page refresh.)

`link:` is the dev-loop install; deployment uses `file:` (copies into the profile), so the source checkout is not a runtime dependency.

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
