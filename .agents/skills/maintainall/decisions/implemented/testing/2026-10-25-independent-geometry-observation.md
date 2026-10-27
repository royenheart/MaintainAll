# Decision: Independent geometry observation

Status: implemented — optional geometry traces and versioned task contracts expose observation gaps without replacing historical scores.

## Problem

The [supplementary review](../../../../../../docs/research/art-skill-supplement-2026-10-25/report.md) cannot verify audio pause from button text, full interruption behavior from sparse screenshots, or repeated player feedback from one link click. The inherited oblique-label requirement also remains ambiguous in the final staged prompt. One generation turn records repeated browser captures before its deadline, including a final screenshot timeout.

## Decision

The [browser evidence contract](../../../../../../benchmarks/skill_bench/README.md) adds optional independently timed, bounded DOM geometry traces. They share the actual input ordering barrier but do not wait for screenshot encoding. Requested and actual sampling times remain visible, worker threads finish before profile navigation, and failed capture cleanup cancels both clocks. Cancellation wakes action-barrier waiters; capture refuses to seal evidence while a worker remains alive. Existing default contracts retain their scope versions. The verifier preserves each trace with its scenario identity and keeps quality unassessed.

The [version-4 task catalog](../../../../../../benchmarks/art_creation/session-expansion/catalog.json) changes three private tasks. It adds real media controls for pause/resume, repeated clicks, explicit trace targets, and explicit continuation of inherited label travel. Targeted authoring checks are distinguished from evaluator replay. Each change creates a new task condition; old suites, scores and assets remain unchanged. This is a mitigation for excessive capture work, not proof that the generation timeout has a single repaired cause.

## Alternatives considered

- Increasing the generation timeout leaves unnecessary rendering and missing observation contracts unresolved.
- More screenshots on the same serial loop do not provide a reliable geometry sampling clock while screenshot capture is slow.
- Main-world application counters and button labels cannot independently establish actual media playback or visible geometry.
- Retrofitting observations or clarifications into the old suite would obscure what earlier outputs were asked to satisfy.

## Consequences

Regression coverage includes delayed screenshots, trace bounds and scenario provenance, actual tone pause/resume with continuing background motion, and existing cleanup and profile-order checks. Geometry traces do not establish uninterrupted pixel appearance; media capture remains conditional on actual browser support. The new manual experiment uses a separate bounded generation budget and cannot establish a skill improvement because it changes observation/task conditions while retaining the skill snapshot.

The [completed experiment](../../../../../../docs/research/art-skill-observation-2026-10-25/report.md) records nine completed turns and 33 independent atom-turn judgments: 31 met, one partial and one unverifiable. The latter retains the distinction between sampled DOM geometry and continuous Canvas pixels. Recorded media-resource aborts remain visible separately from observed pause behavior. The post-generation cleanup fix has its own verifier identity; generation snapshots and historical ratings remain unchanged. Actual inherited reviewer effort remains unconfirmed under a documented pre-review amendment.

One-version private reports resolve their primary selector from the actual recorded arm, including previous-only and no-skill screens. Exact commit or snapshot identities remain distinct from run identity; repeated runs of the same version stay selectable. A view adapter preserves the public paired-comparison logic. Regression tests cover all three arm types, duplicate version runs, and rejection of unrecorded choices. Re-rendering changes HTML only, with the report data hash preserved.
