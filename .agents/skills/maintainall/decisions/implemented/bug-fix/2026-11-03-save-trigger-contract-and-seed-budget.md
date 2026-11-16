# Decision: Save trigger contract and replay-seed budget preflight

Status: implemented — the model-facing trigger contract is explicit, and every save path measures the replay seed before prompting or writing

## Problem

A field save from a long session exposed two failures in the save path.

First, `ops_save_task` documented `triggers` only as "each trigger must include `id`, `source`, and `enabled`". The tool schema left the trigger item at `additionalProperties: true` and neither the tool description nor the injected Save prompt mentioned `params` or `filter`. The model guessed that `source` was a cron expression and made seven failed tool calls (`unsupported source '*/30 * * * *'`, `'schedule:*/30 * * * *'`, `'every 30 minutes'`, …) before finding `source: "schedule"` + `params: { everySeconds }` by reading the plugin source. The error named the rejected string but not the accepted shape.

Second, the task was being saved from a session that had been resumed several times, so its durable trace was large. `safe-copy` at the requested boundary was an 18,522,566-byte seed against the 16 MiB cap. `ops_save_task` spent a full model turn building the runbook, then failed with the bare message `invalid seed: seed is too large`; the model could not tell the measured size, that `compact` at the same boundary fit in 5,862,016 bytes, or which earlier boundary would fit `safe-copy`. The session ended with the task unsaved.

## Decision

- One module, [`src/dispatch/tool-contract.ts`](../../../../../../src/dispatch/tool-contract.ts), owns the trigger contract the model sees: the `ops_save_task` trigger JSON schema, the tool-description guide with valid examples for all six sources and every schedule variant, and the Save-prompt bullets. `source` is documented as the trigger kind; schedule rules go in `params` (exactly one of `cron` / `daily` / `weekly` / `everySeconds` / `afterSeconds` / `at`, with ISO weekdays Monday=1 and the `at` shapes), and source selectors go in `filter`. The guide examples are rendered from one labeled array and revalidated by a test, and the accepted source names come from `TASK_TRIGGER_SOURCES`. The schema, prompt, and `validateTaskTriggers` must stay aligned.
- `validateTaskTriggers` reports an unsupported source by listing all six accepted kinds and pointing selectors/rules to `filter`/`params`, instead of only echoing the rejected value.
- [`src/core/seed.ts`](../../../../../../src/core/seed.ts) measures the exact serialized seed size for both `safe-copy` and `compact`, and computes the latest completed-turn boundary that fits each mode's byte and event-count budgets.
- The Save request path measures the seed before injecting the prompt. A concrete `safe-copy` or `compact` request that does not fit is rejected in the dialog with the measured bytes, the compact size, and the latest fitting `turn/end`; an `auto` request receives both measurements in the prompt and must choose a fitting mode or `fresh`.
- `ops_save_task` repeats the budget check before writing. An oversized capture fails before any temporary task directory or registry entry is committed, and the error carries the same measured alternatives.
- The 16 MiB / 100,000-event caps are unchanged. `safe-copy` remains byte-complete; overflowing it is a mode choice, not a reason to silently compact.
- The Save prompt now states that the replay seed is a frozen snapshot and that recurring runbooks must discover their scope at run time.

## Alternatives considered

- **Auto-downgrade `safe-copy` to `compact` when the seed does not fit.** Rejected: the mode is a user-visible creation-time property in the manifest; silently changing it makes the saved asset disagree with the dialog and the runbook audit.
- **Raise the seed cap.** Rejected for this bug: the cap bounds replay memory and parse cost, and the target case still fit comfortably (5.86 MB) in `compact`. A future need for larger full traces should be a separate decision with replay measurements.
- **Inject a smaller save prompt/metadata set to avoid the failure.** Rejected: prompts and runbooks are small; the seed dominated the budget. Hiding the mode limit would only move the failure.
- **Return the failure only from `ops_save_task` and let the model recover.** Rejected for concrete modes: the dialog already knows the mode and boundary, so the failure belongs before the model turn. The tool check stays as the second line of defense for direct calls.
- **Drop reasoning blocks in `safe-copy` too.** Rejected: that is exactly `compact`; making `safe-copy` lossy would erase the distinction between the two modes.

## Consequences

- A Save from a long, resumed session either succeeds with a mode that fits or fails immediately in the dialog with a measured compact/fitting-boundary option. A concrete capture mode no longer burns a model turn on an impossible save; an `auto` request still queues one turn, but its prompt now carries both byte and event-count measurements plus explicit per-mode eligibility, so it can choose `fresh` when neither capture mode fits.
- A task created before this change keeps its existing seed and mode; the preflight only guards new captures (and direct oversized `ops_save_task` calls).
- Direct `ops_save_task` callers get an actionable error instead of `invalid seed: seed is too large`.
- The model can now construct a schedule trigger from the tool schema/prompt without reading the plugin source; the trigger contract has a single rendering authority, so a future trigger field must be added there as well as in the validator.
- `findLatestFittingBoundary` is an extra linear scan of the session snapshot on the failure path only; successful saves are unchanged except for the byte measurement needed for the prompt.
- Replay behavior is unchanged: a run is still a new session seeded from the frozen durable prefix, not a continuation of the original session id.
