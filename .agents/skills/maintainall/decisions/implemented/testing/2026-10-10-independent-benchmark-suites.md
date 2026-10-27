# Decision: Independent benchmark suites

Status: implemented — one general framework publishes independent benchmark sections and commit histories.

## Problem

The framework accepts versioned tasks and arbitrary requirement dimensions, but the report title names art creation and publication merges every catalogued experiment into one history. Additional skills need independent sections and histories, including when their local experiment identifiers overlap.

## Decision

The [publication catalog](../../../../../../docs/research/skill-benchmark-architecture-2026-10-09/outputs/reports.json) version 2 declares logical suites with safe IDs and readable titles. Every submitted bundle has one `suite_id`. The [publisher](../../../../../../benchmarks/skill_bench/src/skill_bench/publication.py) validates assignments and reserved history paths, assembles each suite separately and generates a top navigation bar in every report. A logical section can retain several frozen dataset versions while condition fingerprints continue to isolate changed tasks, rubrics and runtimes. Catalog version 1 maps to a single generic default section.

The first suite retains the existing timeline URL. Other suite histories use stable `suite-<id>` paths, so registry order should remain stable. All original source bundles remain independently checked; projected report JSON records suite navigation and a new fingerprint. The shared-site validator checks navigation against the version 2 site manifest, renderer output, pooled image hashes and inventory. Images deduplicate across suites; execution records and ratings do not. Multi-suite portable exports require an explicit `--suite-id`.

The [renderer](../../../../../../benchmarks/skill_bench/src/skill_bench/report_view.py) uses a generic standalone title and the registered title for site pages. Git-based CLI planning requires an explicit skill directory. The [CI workflow](../../../../../../.github/workflows/skill-benchmark.yml) discovers frozen suite.json files for offline validation and packages only manually submitted reports; adding a suite does not enable automatic model calls.

The [case contract](../../../../../../benchmarks/skill_bench/schemas/case.schema.json) retains its current three-turn and format limits. Trusted source reopening remains a bounded static SVG check. The current measured data remains art-creation; a second code-review suite exists only in deterministic regression fixtures. General reporting does not establish support for arbitrary toolchains or new domain-specific verifiers.

## Alternatives considered

- Filter one globally merged report: risks experiment-ID collisions and mixes task counts before filtering; independent assembly keeps suite boundaries explicit.
- Fork the execution framework for each skill: duplicates storage, review, budgets and provenance checks; suites supply task data and scoring criteria instead.
- Separate full sites with duplicated reference images: wastes shared image storage and removes consistent navigation.
- Fabricate another measured suite to demonstrate tabs: would misrepresent evaluation coverage; regression fixtures demonstrate multiple sections without appearing in public results.
- Rewrite every frozen report to add logical suite identity: unnecessarily changes existing evidence fingerprints; the checked catalog supplies publication metadata.

## Consequences

The [manual workflow](../../../../../../benchmarks/skill_bench/README.md#multiple-benchmark-suites) records how to register a suite, freeze its own tasks, select the skill directory and submit results. New artifact formats and application capabilities require separate sandbox and verifier work. Existing report JSON, reviews, image bytes and model-call counts remain unchanged when regenerating HTML and publishing the new navigation.

The [suite regression tests](../../../../../../benchmarks/skill_bench/tests/test_suite_publication.py) cover overlapping experiment IDs across sections, shared image deduplication, valid navigation, incorrect assignments, reserved names, explicit skill selection and portable suite selection. All 181 framework tests pass in the pinned native environment; the offline/base environment passes 179 and skips two native-Harbor installation tests. Chromium validates the actual suite landing and report navigation at five viewport widths with 267 successful image loads, no runtime exceptions and zero new model calls. Existing source report JSON and image hashes match across 253 checked source files.
