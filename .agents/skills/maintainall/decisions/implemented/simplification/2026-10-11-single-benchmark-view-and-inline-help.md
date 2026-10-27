# Decision: One benchmark page and contextual terminology

Status: implemented — each public suite has one cumulative page, with contextual definitions and history shown when data supports it.

## Problem

A formal input report and its cumulative suite page show the same evaluation under different navigation labels. Empty commit-history charts add little information when tested revisions were not recorded. A separate interpretation chapter forces readers to leave the metric being explained.

## Decision

The [publisher](../../../../../../benchmarks/skill_bench/src/skill_bench/publication.py) validates every catalogued source bundle and merges each suite into one page. It publishes the suite page, landing page and shared assets, rather than additional source-report pages. Public manifests require one history page per suite. Source bundles remain separately verifiable and later submissions extend history.

The [viewer](../../../../../../benchmarks/skill_bench/src/skill_bench/report_view.py) has four numbered chapters for setup, execution/review coverage, comparisons and case evidence. A fifth evaluation-history chapter appears when multiple evaluations exist under the selected conditions. Commit charts additionally require multiple matching, recorded commit-bound runs; snapshot-only histories cannot supply missing Git SHAs. Existing history projection, condition separation and append-only input records remain intact.

The [help module](../../../../../../benchmarks/skill_bench/src/skill_bench/report_help.py) provides a compact glossary before chapter 1 with separate tables for core terms and report headings. Its explicit glossary allowlist also supplies tooltip definitions; only listed core terms and headings receive dotted underlines. Chapter, subsection and disclosure headings have fixed explanations. Actual case headings and submitted-experiment headings append matching glossary rows when rendered; filtering removes stale rows. Status badges, metric captions, chart legends and table column labels do not receive automatic decoration. The tooltip is constrained to the viewport and closes with Escape, outside clicks or page scrolling. Decoration is idempotent after filtering and applies to lazy case content while leaving original prompts, review reasons, anchors and source patches untouched. Technical records, JSON and limitations remain collapsed footer disclosures.

This refines the [formal-publication decision](2026-10-11-formal-publication-and-numbered-chapters.md); formal failures and insufficient evidence remain included. Model execution remains manual and local.

The [execution chart](../../../../../../benchmarks/skill_bench/src/skill_bench/report_charts.py) distinguishes Completed in green, Failed in red, Stopped in blue and Other/not started in slate gray. Labels and exact counts remain visible; presentation colors do not change status records or requirement judgments. The same generic renderer supports registered suites within the existing task/review contract. New scoring types or interactive media need explicit contract and renderer support rather than a separate page template for each skill.

## Alternatives considered

- Keep separate source and cumulative pages: redundant with one submission, and later requires readers to identify which page has the complete history. One suite page selects individual evaluations and also preserves cumulative data.
- Remove history collection entirely: discards the ability to track later skill revisions. Conditional sections keep that capability without empty charts.
- Infer tested commits from report submission commits: rejected because submission identity does not establish the generated skill bytes.
- Rely only on a glossary: definitions remain too distant from the metric. Contextual help shares fixed definitions without generating new text or ratings.
- Underline every recognizable metric or status: repeated small labels obscure the document. An explicit glossary allowlist and restricted heading/core-term locations keep explanations available without decorating every data display.
- Annotate every word in evidence: risks changing the interpretation of frozen task and review content. Help is restricted to presentation labels.

## Consequences

The current formal evaluation publishes one Art creation page with four chapters, 18 runs and 322 requirement ratings. Its frozen JSON and original assets do not change. Different suites remain separate and share only image storage and presentation. Renderer changes invalidate older HTML under the new validator, so refreshed source HTML and new derived site directories are required. See the [plan](../../../../../../docs/superpowers/plans/2026-10-11-inline-benchmark-help.md), [report documentation](../../../../../../benchmarks/skill_bench/README.md#reports-and-history) and [verification report](../../../../../../docs/research/skill-benchmark-refresh-2026-10-11/report.md).
