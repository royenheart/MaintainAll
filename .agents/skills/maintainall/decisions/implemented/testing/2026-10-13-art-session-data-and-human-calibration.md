# Decision: Original-Session Data and Binary Human Calibration

Status: implemented — nine private task definitions and four actual human visible-subatom annotations are preserved; dynamic evidence capabilities and new model evaluation remain pending.

## Problem

The four-case refinement retest samples different mechanisms but repeatedly uses the same reference images. Existing public trajectory tasks use replacements and were absent from that run. A model can also reward visible clearance without checking whether the depicted support or connection still makes sense. A negative paired preference does not explain whether either result is acceptable to the user.

## Decision

Preserve all existing suite definitions and skill snapshots. The [new catalog](../../../../../../benchmarks/art_creation/session-expansion/catalog.json) indexes nine local-private cases derived from 27 user messages and 29 exact original attachments across two sessions. Task bodies and original image bytes stay outside Git, use the existing schema and retain source hashes, activation turns and declared benchmark additions. An isolated component study is not faithful replay of the original application. The current version-2 release gives large three-image annotations a bounded 64 MiB output workspace; the preceding [version-1 metadata](../../../../../../benchmarks/art_creation/session-expansion/catalog-v1.json) remains intact.

Gate six browser cases on independent action evidence and the audio case additionally on a known-signal probe. These capabilities are explicitly unimplemented. Contract validation does not waive the gate, launch a model or establish behavioral evidence.

Preserve the user's four actual binary answers in a [separate sidecar](../../../../../../docs/research/art-skill-diversity-2026-10-13/human-calibration.json). Both final costume sheets fail the displayed sleeve/torso spatial-clarity question and pass the narrower anatomical-side question. Optional comments distinguish a pasted-looking inset from a broken connection. Do not convert these answers into historical ordinal scores, infer a whole-case preference, or calculate judge accuracy from this selected sample.

## Alternatives considered

- Immediately rewrite the skill from the two negative judgments: rejected because evidence and judge calibration still need work, and two correlated results do not establish a general instruction failure.
- Reuse replacement sketches as if they were original references: rejected because this would hide the requested input diversity and change the evaluation condition.
- Treat a visible gap as sufficient construction quality: rejected because the actual user rejects both a stiff inset and a broken connection while accepting body-side consistency.
- Demand long human reviews or rewrite old ratings: rejected because short binary questions provide useful local evidence and historical records must remain immutable.
- Declare new browser tasks runnable after schema validation: rejected because solver claims and sparse screenshots do not establish actual actions, temporal behavior or audio causality.

## Consequences

The [Chinese report](../../../../../../docs/research/art-skill-diversity-2026-10-13/report.md) states actual definitions, annotations and zero new generator calls. The [evaluation plan](../../../../../../docs/research/art-skill-diversity-2026-10-13/evaluation-plan.md) prioritizes evidence acceptance and human calibration, retained-skill screening, selected repeats and only then a bounded paired skill revision. Task count is distinguished from input diversity and source-session independence. Private original-reference conditions are not pooled with public schematic conditions or exposed as new unseen holdouts.
