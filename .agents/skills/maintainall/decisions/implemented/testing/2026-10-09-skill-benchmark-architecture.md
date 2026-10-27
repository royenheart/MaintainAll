# Decision: Versioned skill benchmark architecture

Status: implemented — versioned task contracts, bounded Harbor trials, independent review and sanitized reports share an isolated benchmark package.

## Problem

Separate creative runners preserve useful local authentication, real attachments, exact-session continuation and usage evidence, but cannot establish a comparable skill effect from delivery checks or correlated atom counts. Historical rubric changes and session-derived references also need explicit provenance instead of silently becoming new held-out data.

## Decision

The [framework](../../../../../../benchmarks/skill_bench/README.md) owns experiment freezing, evidence, review and reporting. The [art task suite](../../../../../../benchmarks/art_creation/README.md) owns requirements, references, calibration and capability gates. A case binds each atom to an exact prompt quote and its active turns. Task, rubric, skill, model, effort, backend, generation runtime and verifier identities define comparison cohorts; changing an identity breaks the trend. Frozen framework and skill bytes, result seals and a hash-chained reservation ledger preserve the inputs and actual attempts.

Harbor 0.24.0 at the exact verified official source commit supplies native Job, Trial and multi-step lifecycle through public custom agent/environment interfaces. The environment reuses the verified local Codex Linux command sandbox, not Harbor's built-in Docker/Codex adapter. Local host authentication is not uploaded; actual image arguments and exact thread UUID continuation are retained. A separate local backend remains a compatibility lane. Missing native 3D, interaction or continuous playback capability is an execution gate, not permission to substitute static evidence.

Without-skill, previous and candidate interventions use a frozen counterbalanced schedule and bounded repeats. Mechanical delivery, ordinal visual judgments, preservation, narrow source-editability evidence and efficiency remain separate. Unknown is not zero, and no aggregate aesthetic score is produced. Completed, failed, interrupted and unattempted planned work retain their coverage denominators. A closed validated ledger is required to represent absent results. Invalid sealed solver previews are withheld with hash-linked status evidence; integrity failures still reject export.

One process holds a nonblocking experiment lock before preflight or result writes. A concurrent caller cannot seal an empty failure over the winning process's real turn evidence. Linked and special lock files are rejected, and process exit releases the lock without making an already started experiment retryable. Native lifecycle progress on stdout is a log; sealed records and derived state remain the machine-readable execution interface.

Independent artifact-only and notes-process packets use a run-private random HMAC key and bind the complete packet to its private mapping. Reviewers record class, disclosures, reasons and hash-linked evidence. Frozen rating versions cannot be overwritten. Regrading consumes immutable generation evidence and appends a verifier version without model calls. Source verification rebuilds a supported SVG and changes one existing fill; it does not certify a whole editable project. Initial agent judgments remain exploratory, with calibration limited to two geometric relations.

Actual user feedback is extracted into development regressions. Private original messages and images remain outside Git. Public cases use clearly labeled authored schematic replacements; they are different input conditions from the private original-reference variant. Historical pilots are imported into new private records without altering their original files, summing inherited token totals or adopting old self-scores as fresh review.

The [GitHub workflow](../../../../../../.github/workflows/skill-benchmark.yml) validates contracts, indexes, deterministic tests and user-submitted public report bundles without model credentials. Model execution is explicitly started locally with `run --execute`; no GitHub request is emitted or consumed through the public CLI. The [manual publication decision](2026-10-10-commit-tracking-and-readable-reports.md) defines the current boundary. Self-hosted runners are not registered to the public personal repository.

The package records its first-import checkout HEAD and complete framework/legacy-helper source hashes. Worker execution verifies that initial identity as well as current Git blobs and compiled definitions, covering stale module constants after a checkout update. Package reload preserves the original identity; a changed checkout requires a fresh process. Offline or wheel usage without a source checkout cannot satisfy this authenticated execution gate. Public trajectory provenance retains hashed source identifiers instead of raw session or thread IDs.

## Alternatives considered

- Expand the legacy runners indefinitely: preserves compatibility but duplicates protocol, repetition, review and history logic. Their audited sandbox helpers remain reused behind the backend instead.
- Adopt the entire SkillEvaluator pipeline: useful skill-control patterns, but its additional orchestration and verification tiers exceed this release's bounded task/evidence scope.
- Use Harbor's default Codex adapter: its inspected auth upload and last-session continuation do not retain the verified local boundary.
- Run authenticated self-hosted GitHub jobs: labels and conditions do not isolate that runner from changed fork workflows. Credential-free hosted jobs validate manually submitted public results; generation stays local and explicitly initiated.
- Publish a single aesthetic total or solver self-rating: obscures unknown evidence, subjective disagreement and the true independent sample size.
- Treat feedback-derived tasks as holdouts or reuse old rubric scores: contaminates generalization claims and pools different measurement conditions.

## Consequences

The framework supports a reproducible bounded comparison and an honest negative or inconclusive result. Eight core task definitions and three public feedback-derived tasks are not eleven completed model evaluations. The initial measured static tasks, repeats and narrow calibration cannot establish general artistic quality or human preference. Runtime, verifier or wrapper changes are retained as cohort changes. Raw trajectories, private keys, authentication and original user references remain outside the repository; only validated sanitized bundles are deliverable.

The [implementation report](../../../../../../docs/research/skill-benchmark-architecture-2026-10-09/report.md), [dataset report](../../../../../../docs/research/skill-benchmark-architecture-2026-10-09/dataset.md) and [backend report](../../../../../../docs/research/skill-benchmark-architecture-2026-10-09/compatibility.md) record the measured scope and limitations. The [implementation plan](../../../../../../docs/research/skill-benchmark-architecture-2026-10-09/implementation-plan.md) documents the approved release boundaries.
