# Decision: Bounded Art Skill Refinement Experiments

Status: implemented — both comparisons and independent reviews are sealed; the tested instruction candidate was rejected and the baseline retained.

## Problem

The historical public art comparison covers only two tasks. Three negative paired preferences are insufficient to locate a general instruction problem, especially when a blinded second review disagrees on two costume episodes. Most existing skill changes are optional resources, so an observed output difference does not establish that the changed guidance was encountered.

## Decision

Use the existing native Harbor adapter and sealed command sandbox rather than modifying execution contracts during the experiment. The [development selection](../../../../../../benchmarks/art_creation/refinement-suite.json) reuses six existing case files and their exact hashes. The [protocol](../../../../../../docs/research/art-skill-refinement-2026-10-13/protocol.json) bounds old/current screening to 36 CLI user-turn launches and a subsequent current/refined comparison to 24, with one shared 60-launch ledger and no automatic retries. Holdouts are excluded from tuning.

Keep the historical review immutable. An independent diagnostic review of the three negative units records agreement and disagreement, with negative-selection bias disclosed. New anonymous reviews use the existing prompt-linked ordinal anchors, complete applicable evidence and separate paired episode preferences. Their [instructions](../../../../../../docs/research/art-skill-refinement-2026-10-13/review-instructions.txt) require concrete differences and disclosure of whether later feedback resolves them; they introduce no numerical aesthetic total.

The [candidate](../../../../../../docs/research/art-skill-refinement-2026-10-13/refinement-candidate.json) tested one shared-rule replacement: preserve supporting relationships, identify revision scope and compare actual renders with accepted baselines under relevant formats, views or states. Its preregistered four-case retest produced one gain, one tie and two persistent brief-relevant losses. The conservative adoption rule rejected the candidate; only the changed entry file was restored from the sealed baseline. The repository and installed skill retain the same baseline hash, and the installed copy was never changed. This does not establish instruction-level causation or a general performance regression. No mandatory form, incident catalog or follow-up tuning was added. The installed global CLI is unchanged; a task-local official 0.160.0 installation satisfies the sealed runtime pin. Failures and missing evidence remain in formal experiment coverage.

## Alternatives considered

- Treat all original negative preferences as established regressions: rejected because the diagnostic reviewer disagrees on two selected units and the small sample cannot identify causation.
- Add detailed fixes for the exact poster and costume incidents: rejected because this overfits development examples and enlarges the skill without testing transfer.
- Run all development and holdout tasks immediately: rejected because the requested experiment is a bounded refinement cycle and holdouts must not become tuning inputs.
- Upgrade the benchmark CLI pin or weaken sandbox grants during execution: rejected because that changes the controlled runtime. The official native dependency is colocated under its JS package within the existing private readonly runtime root instead.
- Replace prior public data with the new result: rejected because manual experiment history must preserve both failed and successful observations.

## Consequences

The [Chinese research report](../../../../../../docs/research/art-skill-refinement-2026-10-13/report.md) distinguishes execution, applicable requirements and paired preference, and records actual generator and reviewer identities. Both phases launched 58 CLI user turns, of which 56 completed; failures were not retried. The six-case screen has one gain, three ties and two undetermined pairs; the [four-case retest](../../../../../../docs/research/art-skill-refinement-2026-10-13/retest-review.json) records the rejected candidate unchanged. Each case receives one independent artifact-only agent judgment, not a panel vote. A single-repeat development comparison is exploratory; neither a complete run nor a passing index validator establishes improved creative quality. Literal successful read commands provide routing evidence, not a complete file-access audit. Validated bundles are appended to the [public catalog](../../../../../../docs/research/skill-benchmark-architecture-2026-10-09/outputs/reports.json); historical data is preserved and framework preflight data stays private. Holdouts remain unused for tuning.
