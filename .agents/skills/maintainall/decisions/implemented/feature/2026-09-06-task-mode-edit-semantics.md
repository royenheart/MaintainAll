# Decision: taskMode edit semantics

Status: implemented — taskMode and replay seed are immutable after creation; edits update metadata only.

## Problem

The Save dialog is reused for editing an existing task. The mode carousel offered `safe-copy` / `compact` / `fresh` / `auto` during edit, which implied the replay seed could be re-cut from the current session. But the Ops-drawer edit flow has no source session, and a natural-language edit opens a fresh session whose trajectory is about editing the task, not performing it. The semantics of "edit a fresh task into safe-copy/compact" were undefined.

Separately, creation mode was ambiguous: do `safe-copy` and `compact` store both the original and the compacted trajectory, or only one?

## Decision

- `taskMode` describes how the seed was captured **once at creation time**. It is recorded in `manifest.yml` and is not editable from the task edit dialog; the dialog shows the current mode as fixed text.
- `safe-copy` stores only the full durable seed under `seed/session.jsonl`. `compact` stores only the compacted seed (reasoning blocks stripped) under the same path. The original trajectory remains in the source dsh session, not inside the task asset.
- Manual edit (`POST /tasks/<id>/edit` with `materialize: true`) rewrites only `manifest.yml`, `AGENTS.md`, and `triggers.yml` via `writeTaskMeta`. `seed/`, `.agents/skills/`, `scripts/`, and `runs/` are untouched.
- Natural-language edit (`POST /tasks/<id>/edit` with `auto: true`) opens a fresh session with the current task directory as cwd. The prompt instructs the model to keep `taskMode` and to call `ops_save_task`; `ops_save_task` hard-enforces preservation: when a task with the same id already exists, it keeps the existing `taskMode`, `version`, `importedAt`, `fingerprint`, and seed instead of re-cutting the edit session's trajectory.
- To change a task's mode or recapture its seed, delete the task and re-create it from a real ops session with the desired mode.

## Alternatives considered

- **Allow mode changes in manual edit.** Rejected: there is no source session in the Ops-drawer edit flow, so `safe-copy`/`compact` could not produce a seed; it would leave a manifest mode with no matching seed.
- **Natural-language edit re-cuts the seed from the edit session.** Rejected: the edit session's trajectory is about editing the task, not performing the ops task, so it would silently replace a proven replay seed.
- **Store both original and compacted seeds for `compact`.** Rejected: doubles storage and complicates dispatch selection for no user-visible benefit; `compact` is an explicit size optimization over `safe-copy`.

## Consequences

- Task mode is a creation-time property. The edit dialog cannot change it; users must re-create from a session to recapture.
- `ops_save_task` is no longer a pure "create" tool: re-saving an existing id is an edit and preserves the seed. Delete + save is the recapture path.
- `writeTaskMeta` is the metadata-only writer; `writeTaskAsset` remains the full writer used at creation/import/recreation.
