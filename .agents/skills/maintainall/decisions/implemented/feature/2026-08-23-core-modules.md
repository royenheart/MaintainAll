# Decision: Dependency-free core modules (manifest, seed, storage, dedupe)

Status: implemented — core logic shipped under `src/core/` with `node --test` coverage

## Problem

The plugin needs its pure logic — manifest parsing/validation, replay-seed
extraction and rewriting, atomic state persistence, and task dedupe — to exist
before the host service ([`src/index.ts`](../../../../../../src/index.ts)) and trigger
engine can be built, and that logic must stay testable with `node --test`
without a harness runtime, per [docs/testing.md](../../../../../../docs/testing.md).

## Decision

Four modules under `src/core/`, importing only node built-ins, the `yaml`
package ([`manifest.ts`](../../../../../../src/core/manifest.ts)), and the shared
contracts in [`contract.ts`](../../../../../../src/core/contract.ts). Relative imports
use the `.ts` extension so Node 24 runs them directly in strip-only mode
(no parameter properties or other non-erasable syntax).

- [`manifest.ts`](../../../../../../src/core/manifest.ts): `parseManifest` (via `yaml`),
  `validateManifest` (strict `format`/`id`/`name`/`version`; id matches
  `^[a-z0-9][a-z0-9-]*$`, version is semver), `computeChecksums` (sha256 hex
  per file), `rewriteManifestForImport` (bindings replaced with machine-local
  presets, `requires.secrets` carried over unchanged, input never mutated).
- [`seed.ts`](../../../../../../src/core/seed.ts): `extractSeedEvents` keeps the eight
  durable event types up to a seq boundary and rejects non-contiguous seq;
  `rewriteSeedCwd` deep-replaces cwd strings in event data; `filterSeedTools`
  drops unavailable `tool/call` events, their `tool/result`s, and the
  matching blocks inside assistant messages.
- [`storage.ts`](../../../../../../src/core/storage.ts): `pluginDataRoot` resolves
  `$DSH_HOME/@royenheart/dsh-plugin-maintainall` with a `~/.dsh` fallback;
  `AtomicJsonFile` writes via tmp file + fsync + rename (dirs 0o700, files
  0o600); loaders for `registry.json`, `trigger-state.json`, `run-map.json`
  return versioned defaults when absent and throw a clear error on corrupted
  JSON.
- `dedupe.ts` (now removed from the core surface; see `src/core/`): `taskFingerprint` is sha256 over
  id + normalized name + version + order-normalized requires tools/MCP
  servers (secrets and bindings excluded); `similarity` is Jaccard over name/
  description word tokens plus an exact-id bonus, clamped to `[0, 1]`.

Tests live in `tests/core/` and run with `node --test tests/core/*.test.ts`.
The `yaml` dependency is declared in `package.json` but installed at the
integration step; until then the manifest suite cannot load and the other
three suites (20 tests) pass.

## Alternatives considered

- **Hand-rolled YAML subset parser**: keeps `src/core/` fully
  dependency-free, but YAML edge cases (quoting, anchors, nesting) make a
  partial parser a correctness hazard for a user-authored file format. The
  `yaml` package is already a declared dependency.
- **Zod/schemastery schemas in core**: rejected because `src/core/` must
  stay dsh-free and dependency-light; hand-written validators produce the
  descriptive error messages import flows need without a schema runtime.
- **Reading corrupted state as `undefined` instead of throwing**: rejected
  for state files; silently resetting plugin state could re-enable triggers
  or lose run mappings. Missing files get defaults; corrupted files fail loud.

## Consequences

- Host/client entries and the trigger engine can build on stable, tested
  contracts without touching dsh APIs.
- `npm run typecheck`/`lint` cover these modules; the manifest test suite
  activates once `npm install` runs (declared `yaml` dependency).
- Any change to manifest schema, seed event retention, or state file shape
  must update the matching `tests/core/` suite in the same change.
