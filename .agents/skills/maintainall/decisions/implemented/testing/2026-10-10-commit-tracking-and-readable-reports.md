# Decision: Manual evaluations and readable public reports

Status: implemented — explicit local generation, user-submitted public results and credential-free CI keep subscription authentication on the local machine.

## Problem

Automatic generation on every skill commit consumes the user's subscription without a per-run decision. Raw hashes and JSON counts obscure comparison meaning. A public repository must not transport local account authentication or publish private evaluation evidence.

## Decision

Model generation uses the existing local `plan` and explicit `run --execute` commands. The [workflow](../../../../../../.github/workflows/skill-benchmark.yml) contains only offline checks and public-result validation/packaging. It sends no model requests. Supported worker/track CLI commands and scheduler examples are removed; historical request validation helpers remain only as internal offline regression coverage.

Users export sanitized reports, add them to the [catalog](../../../../../../docs/research/skill-benchmark-architecture-2026-10-09/outputs/reports.json), inspect their contents and submit them manually. The [publication module](../../../../../../benchmarks/skill_bench/src/skill_bench/publication.py) checks each listed bundle's exact trusted renderer, public fields, hashes, ordinary paths and file inventory before staging only those files into a new site. Unlisted side files are never copied, altered bundles fail, and existing output directories are not overwritten. The CI commit is not inferred as the generation commit.

The English viewer follows overview, comparison, case evidence, experiment history and technical details. Plain names explain completed runs, recorded/planned turns and Better/Similar/Worse/Not enough evidence. Original task text, reasons, score anchors and image bytes remain intact. Original review A/B order is stated even when evidence columns use baseline/candidate order. The layout follows Kami paper design rules and [official reporting research](../../../../../../docs/research/skill-benchmark-refresh-2026-10-10/industry-display.md).

Manual Git planning accepts `--repo`, `--previous-ref`, `--candidate-ref` and an explicit `--skill-path`, reads safe regular blobs and seals exact SHAs, dates and parent identity with the input snapshots. It does not infer a commit from a dirty directory or from the report-upload checkout. The [manual input reader](../../../../../../benchmarks/skill_bench/src/skill_bench/manual.py) does not execute skill files or fetch code. Snapshot-only historical results stay outside the commit chart.

Publication unions catalogued experiment records independently within each registered benchmark suite, with top navigation and separate commit histories as described in the [suite decision](2026-10-10-independent-benchmark-suites.md). Already merged reports do not duplicate trials or reviews. Conflicting identities within a suite fail instead of silently overwriting results. Commit charts use separate ordinal-count bars for manual runs and omit only skill-byte identity from their comparison conditions; task, rubric, model, runtime, judge, budget, order seed and protocol still separate series. Repeated evaluations at the same commit remain visible.

Publication stores original images once per content hash in a site-level `assets/` directory. All projected report pages and the cumulative timeline use `../assets/<hash>.<extension>`; common references are shared across experiments. Source bundles retain their independent validation contract. Derived public JSON records the shared layout and source fingerprint, while execution and rating records stay intact. `check-site` separately verifies pooled media, exact trusted HTML, public fields, fingerprints and the complete file allowlist.

Application previews can isolate one HTML file and lose adjacent resources. The default solution is opening the complete site or serving its root locally so relative paths resolve. CI creates the pooled site without embedded images. An explicit `portable` command can still embed checked originals for a single-file handoff, with a 96 MiB ceiling; it is not called by publication or CI. The pooled site stays bounded at 256 MiB. Local serving is scoped to the public site and does not initiate model evaluation.

## Alternatives considered

- Automatic per-commit local consumption: rejected because the user chooses when subscription-backed evaluations run.
- An authenticated GitHub self-hosted runner: adds remote execution and credential exposure unnecessary for manual local evaluation.
- API-backed hosted generation: requires a different authentication and billing setup from the user's existing subscription.
- Upload an entire run or collection root: could include private logs, credentials or unrelated files; explicit catalogued allowlists are used.
- Automatically embed images in each report: increases payloads and duplicates common references; shared paths are the default and standalone handoffs are opt-in.
- Embed generated look-alike images or relax exact HTML validation: rejected because original checked evidence and trusted presentation must remain verifiable.
- Flatten all quality records into one trend: confounds dependent ratings, unknown observations and changed evaluation conditions.

## Consequences

A submitted code change may have no new model result. CI packages only the evaluations actually submitted and never fills missing quality. Local per-experiment invocation ceilings are not subscription or monetary limits. Results and independent reviews remain immutable; HTML can be refreshed from unchanged public JSON when the trusted viewer changes. [README](../../../../../../benchmarks/skill_bench/README.md#manual-local-evaluation-and-result-submission) records commands and artifact use. Pages deployment, automatic push and runner/timer activation are absent.
