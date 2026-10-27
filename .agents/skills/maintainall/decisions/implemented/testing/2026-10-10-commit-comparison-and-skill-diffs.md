# Decision: Tested commit selection and frozen skill diffs

Status: implemented — reports select recorded commit pairs and show verified frozen skill changes without model calls.

## Problem

Experiment titles and a generic previous-skill selector obscure the tested source versions. The existing commit chart does not reveal which instructions, references or scripts changed. Rebuilding reports must remain deterministic and must not infer generation provenance from the later upload checkout.

## Decision

The [viewer](../../../../../../benchmarks/skill_bench/src/skill_bench/report_view.py) leads with candidate commit, baseline commit, evaluation run and case. The [selection logic](../../../../../../benchmarks/skill_bench/src/skill_bench/report_changes.py) offers only pairs present in recorded experiments. Repeated runs stay separate. Full generation-time commit or snapshot hashes appear in selectors, comparison cards, evidence headings and diff panels. Compact chart ticks have accompanying full-hash tables and tooltips. Older directory inputs retain frozen snapshot identities and an explicit missing-commit label; no upload SHA is substituted. No-skill comparisons have no previous source. See the [identity and presentation decision](2026-10-10-full-version-identities-and-semantic-colors.md) for filter synchronization and visual distinctions.

The [diff builder](../../../../../../benchmarks/skill_bench/src/skill_bench/changes.py) verifies the complete sealed snapshot inventories, skill identities and file bytes before generating sorted unified patches. Each supplemental experiment record binds its changed-file inventory and patch hash to the evaluated arm hashes. The [CLI](../../../../../../benchmarks/skill_bench/src/skill_bench/cli.py) derives it automatically during report export. Private content, binary files and bounded-size exclusions have explicit omission reasons. Text files are limited to 256 KiB and 6,000 lines; patches are limited to 2 MiB. File content is displayed as escaped text and never executed. Public bundle and shared-site validation independently check the new contract, while generation-time skill verification remains local to the sealed run.

The viewer uses [diff2html](https://github.com/rtfpessoa/diff2html) 3.4.56, pinned and verified from the official npm package. [Source metadata](../../../../../../benchmarks/skill_bench/src/skill_bench/vendor/diff2html/source.json) records the tarball integrity, component version, asset hashes and MIT license. Trusted HTML includes the component's script, style and complete license notice under the existing hash-authorized Content Security Policy. Framework freezing includes these assets and wheels package them. Expanding the panel renders lazily; split/unified layouts, changed-file selection, long-line wrapping with aligned split rows and patch download work offline. Image pooling is unaffected.

Rendering uses saved public data and fixed Python/HTML/JavaScript templates. Review reasons remain the frozen reviewer's supplied text; report generation does not invent summaries or request an LLM. Source differences are not quality judgments. Solver calls and new independent reviews remain separate explicit operations under the [manual workflow](../../../../../../benchmarks/skill_bench/README.md#manual-local-evaluation-and-result-submission).

The current public paired results have verified sealed snapshots but no recorded generation SHA. Their historical exports gain only supplemental frozen diffs and corresponding derived fingerprints/HTML; the original private exports are archived. Execution rows, ratings, pair judgments, cohorts, task context and original raster evidence remain intact. Both paired experiments show the same six changed files. The candidate-only compatibility experiment has no previous source.

## Alternatives considered

- Keep experiment titles as the main comparison identity: hides the source versions and prevents precise pair selection.
- Select arbitrary commits and combine unmatched evaluations: creates comparisons without recorded pairing or stable measurement conditions; only recorded pairs are offered.
- Diff the current checkout or the result-upload commit: does not establish what the solver saw; the exact sealed input snapshots are used.
- [Phistory's Monaco implementation](https://github.com/WEIFENG2333/phistory/blob/main/phistory/site.py): provides a full read-only editor with from/to selectors and wrapping. Its additional editor assets and loading machinery are unnecessary for this bounded static report. The public source was inspected because the hosted agent URL rejected direct access.
- [Pierre Diffs](https://github.com/pierrecomputer/pierre): offers a richer viewer with Shiki and component integration; unnecessary runtime/build integration for the existing Python offline template.
- A custom diff renderer: duplicates mature parsing, escaping, file navigation and split-view behavior; diff2html provides these with a small vendored distribution.
- LLM-authored report prose on every refresh: adds cost and nondeterminism without new evidence; fixed explanatory templates and frozen reviewer text are sufficient.

## Consequences

Each HTML page gains approximately 95 KiB of trusted component assets; original images still have one physical copy per site hash. Reports with source diffs additionally carry a bounded text patch. Legacy exports without verified snapshots show an unavailable state rather than fabricate changes. Commit-axis tracking requires Git-based planning before generation, as documented in the [README](../../../../../../benchmarks/skill_bench/README.md#reports-and-history).

The [regression tests](../../../../../../benchmarks/skill_bench/tests/test_skill_changes.py) cover exact frozen source despite later checkout edits, deterministic output, snapshot and patch tampering, omitted content, recorded pair selection, repeated runs and missing-commit honesty. Chromium checks the actual historical diff, split/unified wrapping and row alignment at four widths, five overview widths, no-skill switching, file selection, case/turn controls and shared image loading. Commit-control fixtures live only in browser memory and never alter public evaluation records. This change makes zero model generation calls.
