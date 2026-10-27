# Decision: Task asset writer and opskit exchange format

Status: implemented — `src/core/task-writer.ts` + `src/core/opskit.ts` shipped with `node --test` coverage

## Problem

The save/export/import flows need a concrete on-disk task asset format under
`ops/<task-id>/` and a portable exchange archive (`<task-id>.opskit.zip`) that
other machines can import and verify, built only on the contracts in
[`contract.ts`](../../../../../../src/core/contract.ts) and the manifest helpers in
[`manifest.ts`](../../../../../../src/core/manifest.ts) — without adding dependencies
and without dsh imports, per [docs/testing.md](../../../../../../docs/testing.md).

## Decision

Two modules under `src/core/`:

- [`task-writer.ts`](../../../../../../src/core/task-writer.ts):
  `writeTaskAsset`/`readTaskAsset`/`listTaskAssets` plus the shared
  serializers `serializeSeed`/`parseSeed` and
  `serializeTriggers`/`parseTriggers` and the atomic primitive
  `writeFileAtomic`. `writeTaskAsset` validates the manifest, then writes
  every file via tmp file + fsync + rename (same pattern as
  [`storage.ts`](../../../../../../src/core/storage.ts)); `.agents/skills/`,
  `scripts/`, `seed/`, and `runs/` are created even when empty.
  - `seed/session.jsonl`: first line is `{"type":"session","cwd":...}`, then
    one JSON `SeedEvent` per line, trailing newline.
  - `triggers.yml`: a YAML mapping `{ triggers: [...] }` so the file can grow
    sibling keys later without breaking readers; each entry must carry a
    non-empty `id`, a `source`, and a boolean `enabled`.
  - Skill/script map keys are task-relative posix paths; anything resolving
    outside the task directory is rejected.
- [`opskit.ts`](../../../../../../src/core/opskit.ts): `exportTask`/`importTask` plus a
  self-contained stored-ZIP codec (`createZip`/`readZip`, table-driven CRC32,
  ~120 lines). Only method 0 (stored) entries are written and accepted; names
  are flagged UTF-8 and a fixed DOS timestamp keeps archives deterministic.
  - Export: entry order is `manifest.yml`, `AGENTS.md`, skills (sorted),
    scripts (sorted), `seed/session.jsonl`, `triggers.yml`. The in-zip
    manifest carries `checksums` (sha256 hex of every other file's UTF-8
    bytes) and never carries machine-local `bindings`.
  - Import: checksums are verified before anything is written; a missing
    `manifest.yml`, schema violation, missing covered file, or checksum
    mismatch fails loud. Bindings are rewritten via
    `rewriteManifestForImport`; every trigger gets `enabled` forced to the
    caller's `opts.enabled` (default `false`) so imported tasks never start
    firing on their own. The task is staged with `writeTaskDir` under
    `incoming/` and renamed into `ops/<task-id>/`; the registry update is the
    caller's job, keeping the module pure.

Tests live in `tests/core/task-writer.test.ts` and
`tests/core/opskit.test.ts` (12 tests), all using `fs.mkdtemp` under
`os.tmpdir()`.

## Alternatives considered

- **A ZIP dependency (`adm-zip`, `fflate`, `yauzl`)**: rejected — the plugin
  ships as a self-contained bundle and core must stay dependency-light; the
  stored-only subset of ZIP is small, and import deliberately refuses
  deflated entries rather than growing a decompressor.
- **`zlib.deflateRaw` for smaller archives**: rejected for now — skill files
  and seeds are small, stored entries keep the reader trivially auditable,
  and the method check gives a clean rejection path. A `dsh-opskit/2`
  manifest format could admit deflated entries later.
- **Top-level YAML sequence for `triggers.yml`**: rejected — a bare sequence
  can never gain a `version` or defaults key without a breaking change; the
  `{ triggers: [...] }` wrapper costs one indent level.
- **Registry update inside `importTask`**: rejected — it would drag
  `storages/registry.json` and fingerprinting into what is otherwise a pure
  file-format module; the host service owns registry writes.

## Consequences

- The host service's save/export/import RPC surface can be implemented as
  thin orchestration over these two modules plus `dedupe.ts`.
- Exported archives are byte-deterministic for identical task content (fixed
  timestamps, sorted entry order), which keeps checksums and tests stable.
- Any change to the on-disk layout, seed line format, triggers.yml wrapper,
  or zip entry set must update the matching `tests/core/` suite in the same
  change.
