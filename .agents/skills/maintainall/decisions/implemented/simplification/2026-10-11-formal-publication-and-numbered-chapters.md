# Decision: Formal publication and numbered report chapters

Status: implemented — the public catalog contains formal evaluations and the trusted viewer presents numbered document chapters.

## Problem

Framework development and compatibility pilots appear beside formal skill evaluations and enter cumulative history. They measure the benchmark's implementation process, which makes the public report harder to interpret. Unnumbered report panels and a comparison summary above the filters obscure the reading order.

## Decision

The [public catalog](../../../../../../docs/research/skill-benchmark-architecture-2026-10-09/outputs/reports.json) lists a standalone formal export from the existing sealed run, frozen review and mechanical regrade. It excludes the development and compatibility experiments, including their records inside the previous merged report. Local archives retain those implementation checks. Public formal failures and insufficient evidence remain intact; exclusion is based on evaluation purpose, not observed performance.

The [trusted viewer](../../../../../../benchmarks/skill_bench/src/skill_bench/report_view.py) uses numbered chapters for evaluation setup, execution/review coverage, candidate versus baseline and case evidence. Its conditional history and contextual definitions are specified by the [viewer simplification](2026-10-11-single-benchmark-view-and-inline-help.md). An ordered contents list links to semantic level-two headings. Filters and the skill diff belong to setup, and the comparison summary belongs to version comparison. Level-three headings and case-summary headings receive chapter-relative numbers after rendering and filtering; their original labels are retained to prevent duplicate prefixes.

The [publication module](../../../../../../benchmarks/skill_bench/src/skill_bench/publication.py) continues to include only explicitly catalogued bundles and to assemble their suite histories. The framework remains generic; experiment names are not a publication blacklist. New formal runs can be appended without adding development records or changing the manual-local execution policy.

## Alternatives considered

- Hide pilot navigation while retaining its rows: rejected because coverage, selectors and cumulative history would still include implementation checks.
- Remove failed formal runs: rejected because execution failures are part of the measured evaluation.
- Hard-code a development-name filter in the publisher: rejected because publication eligibility is an explicit catalog decision and suite naming is generic.
- Convert reports into static Markdown: loses interactive filters, charts, diffs and evidence disclosures. The HTML viewer instead follows Markdown heading hierarchy and numbering.

## Consequences

The formal source supplies the public Art creation page: 18 runs, 54 planned turns, 46 recorded turns and 322 requirement ratings. Future submitted evaluations extend history without overwriting previous results. Renderer changes require a new verified export; archived bundles are not silently accepted by the current validator. No new generation, review or remote deployment occurs. See the [implementation plan](../../../../../../docs/superpowers/plans/2026-10-11-public-benchmark-chapters.md) and [report documentation](../../../../../../benchmarks/skill_bench/README.md#reports-and-history).
