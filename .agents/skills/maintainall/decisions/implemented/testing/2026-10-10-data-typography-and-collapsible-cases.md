# Decision: Data typography and collapsible case evidence

Status: implemented — reports use standard data typography and whole-case disclosure with recorded-data summaries.

## Problem

Artistic serif typography makes numerical comparisons difficult to scan. All case evidence opens immediately, producing long reports as the number of cases increases. Collapsing only prompts and technical proofs does not address the full-case reading burden.

## Decision

The [report renderer](../../../../../../benchmarks/skill_bench/src/skill_bench/report_view.py) and [suite landing page](../../../../../../benchmarks/skill_bench/src/skill_bench/publication.py) use system sans-serif fonts. Numbers, hashes, source text and chart values use a local monospace stack with tabular digits. Explicitly numeric table columns align right, while descriptions remain left aligned. No fonts are downloaded. Existing semantic outcome colors and full version identities remain in use.

Each case is a native keyboard-accessible `details` element, initially closed. Its summary shows filtered runs and repeats, execution statuses, recorded/planned turns, review coverage and separate candidate-direction comparison counts. These values come from the same frozen records and active filters as the report, grouped by case fingerprint. Review coverage counts runs with recorded ratings, including unknown ratings; it does not assert quality or independence. Missing evidence remains a distinct category. Summaries cover all filtered runs, while expanded evidence selects an individual repeat and turn.

Case bodies are populated on first expansion, so closed cases do not create image requests or rating panels. Expand/collapse-all controls affect visible cases. Expansion state is retained separately for each evaluation and case fingerprint, while repeat and turn choices survive case re-rendering. Comparison-table navigation explicitly opens the chosen case and selects the exact repeat, retaining the chosen turn. Removed nodes cannot overwrite current disclosure state through delayed toggle events. Several cases can remain open for comparison.

This is presentation-only. Frozen source JSON, execution records, review reasons, image bytes, dataset identities and model-call counts remain unchanged. Source HTML is rebuilt by the trusted renderer, previous HTML is archived locally, and the pooled site is independently validated. Rendering and checks make zero new model calls.

## Alternatives considered

- Monospace every label and paragraph: adds density without improving the reading of prose; monospace is reserved for data and source text.
- Keep all cases open and add internal disclosures: still creates a long evidence wall and loads unnecessary content.
- An exclusive accordion: prevents simultaneous comparison of multiple cases; independent native disclosures are more useful here.
- Show an average quality score in the closed summary: obscures ordinal judgments, dependencies and unknown evidence; retain separate recorded counts.
- Hide bodies only with CSS: creates all figures and ratings despite being collapsed; build the body when requested.
- Share expansion state solely by case ID: leaks state across experiments and task versions; use evaluation plus case fingerprint.

## Consequences

Closed cases stay compact, but summaries still grow with the number of cases. Opening a case introduces its image requests; originals remain shared relative assets and are not embedded in each report. Numeric tables retain horizontal scrolling when needed at narrow widths. Disclosure state lasts for the current page session and is not stored across reloads.

The [projection tests](../../../../../../benchmarks/skill_bench/tests/test_report_view.py) cover recorded counts, separate fingerprints, version filtering and absent case selections. Actual Chromium checks cover initial disclosure, lazy bodies, summary values, single and bulk toggles, repeat/turn retention, evaluation-scoped state, comparison jumps, numeric alignment, five overview widths, four expanded-case widths, both diff layouts and original images. Synthetic commit-chart fixtures remain in browser memory only. See the [validation summary](../../../../../../docs/research/skill-benchmark-refresh-2026-10-10/data-cases-summary.json) and [implementation report](../../../../../../docs/research/skill-benchmark-refresh-2026-10-10/report.md).
