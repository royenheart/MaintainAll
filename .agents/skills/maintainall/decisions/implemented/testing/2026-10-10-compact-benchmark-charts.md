# Decision: Compact benchmark charts

Status: implemented — compact spacing and data-derived charts make execution, comparisons and evidence coverage easier to scan.

## Problem

Large section gaps, tall comparison cards and expanded experiment metadata make the report unnecessarily long. Text counts alone obscure differences between versions and cases. Additional charts must preserve the separation between execution, dependent requirement observations, missing evidence and actual changes in tested commits.

## Decision

The [report viewer](../../../../../../benchmarks/skill_bench/src/skill_bench/report_view.py) uses denser page, section, card, table and disclosure spacing while retaining standard UI fonts, aligned monospace data, exact version identities and collapsible cases. Old experiment metadata is available in a closed disclosure. Commit chart data tables also expand on demand. Desktop charts use two columns and narrow screens use one.

A separate [chart module](../../../../../../benchmarks/skill_bench/src/skill_bench/report_charts.py) contains deterministic record projections and offline SVG rendering:

- Runs by tested version: horizontal stacked bars show completed, failed, stopped and other/not-started counts. This is execution coverage, not task quality.
- Comparison by case: horizontal stacked bars show the candidate-direction Better/Similar/Worse/Not enough evidence counts from the same frozen pair records as the detailed table.
- Requirement rating distributions: an expandable chart keeps each recorded cohort separate, including case, tested version and full condition identity. Adjacent case/version rows improve scanning without combining their rating records or implying an average score.
- Known token subtotals: an expandable bar chart retains the observation count for each field. Missing usage receives an explicit not-recorded label; commands stay in the table because they have a different unit. Cached/uncached input are components of total input and are not added to it.
- Commit history: users choose stacked rating-count columns or a line for the proportion of recorded ratings assigned a 0/1/2 level. The line measures evidence availability, not design quality; unknown ratings remain in its denominator. Unreviewed runs have no value and interrupt connections. Existing commit grouping continues to separate changed task, model, runtime, rubric, judge, execution policy and protocol conditions. Missing tested commits receive no fabricated point.

Horizontal charts start at zero and use one shared absolute scale per panel. Count axes have integer ticks and a rounded upper bound; large tick labels use K/M abbreviations with full values in tooltips. Full counts remain in row labels, bar metadata and accessible text. Bar geometry uses the actual SVG viewport, so its origin and scale align with the external ticks at every width. Text keeps its unscaled monospace font. All categories retain labels and colors, including unknown evidence.

No chart library, external request, model call or image embedding is introduced. Framework snapshots and wheels include the chart module through the existing Python-package inventory. Source report JSON, frozen task context, ratings, reasons, images and model-call counts remain unchanged. Trusted HTML is rebuilt and pooled-site validation is retained; previous local HTML remains archived.

## Alternatives considered

- Add more numerical cards: remains difficult to compare relationships and consumes vertical space; use compact counts together with bars.
- Use pie charts: comparing several cases or versions is clearer on aligned bars with a common scale.
- Treat categorical rating counts as a continuous histogram or average: implies unsupported distances and quality aggregation; preserve discrete categories and exact cohorts.
- Draw a quality line across all experiments: changed conditions and missing commit identities invalidate it; commit graphs require recorded provenance and matching conditions.
- Plot missing reviews as zero: confuses unavailable evidence with a measured zero; absent values break coverage lines.
- Use logarithmic token bars or mix command counts with tokens: makes the present small data harder to interpret; retain linear token counts and explicit separate units.
- Introduce a large client chart dependency: these simple deterministic charts need only native SVG; offline assets and the strict trusted renderer remain sufficient.

## Consequences

The default report is shorter even with two visible overview charts. Distribution and usage details remain available through disclosures; several cases can still be expanded together. Full hashes wrap rather than being replaced with role names. Commit labels on chart axes remain abbreviated with full provenance in tooltips and the associated data table. Older evaluations without generation-time Git SHAs continue as snapshot experiments.

The [projection regressions](../../../../../../benchmarks/skill_bench/tests/test_report_view.py) cover selected counts, independent conditions, unknown usage, version filtering, coverage gaps and integer count scales. Actual Chromium checks compare chart counts against source projections, verify bar origins, exercise filters and commit metrics, inspect five widths for each chart family and measure the default page against the preceding renderer under the same viewport and disclosure state. Temporary commit and scale fixtures remain in browser memory only. See the [validation summary](../../../../../../docs/research/skill-benchmark-refresh-2026-10-10/compact-charts-summary.json) and [implementation report](../../../../../../docs/research/skill-benchmark-refresh-2026-10-10/report.md).
