# Agent Note: Local skill evaluation and public report delivery

Status: implemented — versioned local evaluation feeds credential-free CI and optional Pages publication.

## Problem

Creative skill comparisons need reproducible inputs, independent review, and inspectable history. Local authentication, source sessions, and machine configuration belong outside the public repository.

## Decision

The [benchmark framework](../../../../benchmarks/skill_bench/README.md) records frozen tasks and skill versions, executes manually through local Codex or Harbor, and exports independently reviewed public bundles. The [task collection](../../../../benchmarks/art_creation/README.md) contains public reference material and derived development tasks. Original-session catalogs retain hashes and task metadata; original attachments and research archives remain local.

The [CI workflow](../../../../.github/workflows/skill-benchmark.yml) downloads the small Git LFS input dataset, runs deterministic checks, restores the versioned Release packages in the [result catalog](../../../../benchmarks/results/catalog.json), and builds the report site. It uses no model credentials or generation calls. Optional Pages deployment requires the repository variable `BENCHMARK_PAGES_ENABLED=true` and the GitHub Actions Pages source; only the deployment job receives Pages/OIDC write permissions.

Browser integration tests select a local runtime through `SKILL_BENCH_TEST_CHROMIUM`. Privacy regression fixtures use synthetic paths and session identifiers. Deterministic ZIP packages contain only frozen public JSON and hash-addressed raster media. The committed catalog pins public HTTPS locations, sizes, SHA-256 hashes, report fingerprints and small summaries. Restoration checks archive members and expanded limits, verifies each report and image, and generates current HTML into a new local collection before atomic publication. Report rendering changes need no archive update. Ordinary tests use local synthetic packages. Historical automatic request, queue and worker execution modules are removed; tested-commit provenance and manual execution remain. Public PNG derivatives remove text, EXIF and timestamp metadata without re-encoding image or color-profile bytes. Each derivative records its original hash, original size and transformation; review evidence retains original hashes alongside public derivative paths. Bundle and shared-site validation reject these PNG metadata chunks. Original execution files and review packets stay local and unchanged.

## Alternatives considered

- GitHub-hosted model evaluation would require a separate authentication arrangement and differs from the requested manual local workflow.
- Committing historical reports adds hundreds of generated files and large LFS output images to source review. Versioned Release packages keep evidence reproducible while Git retains readable identities and counts. Actions artifacts alone expire and cannot serve as durable inputs.
- Compressing executable test modules hides source diffs without reducing maintenance work. Tests remain normal discoverable source files; tests for removed queue behavior are removed with that behavior.
- Publishing local research directories would include unrelated experiments and machine-specific records. Publication uses an explicit catalog and per-bundle file validation.
- Installing browser runtimes through hard-coded home paths would make tests depend on one workstation. An explicit environment variable supports local integration checks while offline CI stays portable.

## Consequences

The source PR contains the framework, public task definitions and references, skill bundle, tests, and compact result catalog. Future evaluations upload a new verified Release package and append its metadata to the catalog. Generated sites and restored collections stay outside Git; maintainers keep local package backups. CI needs public Release download access, but no generation credentials. Missing or altered packages fail publication rather than removing historical observations. Report pages group results by skill suite and preserve tested version identities. Repository administrators can enable Pages through the documented settings; downloadable report artifacts work independently of Pages.
