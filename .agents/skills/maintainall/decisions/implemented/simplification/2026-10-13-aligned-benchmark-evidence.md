# Decision: Align benchmark images and requirement judgments

Status: implemented — shared rows replace independent evidence stacks without changing frozen results.

## Problem

The [benchmark viewer](../../../../../../benchmarks/skill_bench/src/skill_bench/report_view.py) stacks images and requirement cards separately for each tested version. Extra intermediate images shift corresponding judgments vertically, while repeated criteria and large cards make the same atoms difficult to compare.

## Decision

The [evidence projection and renderer](../../../../../../benchmarks/skill_bench/src/skill_bench/report_evidence.py) align applicable atoms by ID in one compact table for the selected case, repeat and turn. Criteria, original requirement quotes and ordinal anchors expand once per row. Each version retains its own complete reason, evidence and reviewer identity. Multiple reviews remain separate entries instead of overwriting or averaging them; no review, no run and insufficient evidence remain distinct.

Declared raster outputs align by exact artifact path. Missing images keep their own cells. Additional images and source-check images load in separate collapsed disclosures. Older records use available output names and atom identities without inferring missing task definitions. The presentation derives entirely from frozen records, supports a single-version filter and uses a horizontally scrollable table on narrow screens.

## Alternatives considered

- Smaller independent cards reduce spacing but leave corresponding atoms misaligned whenever image or review counts differ.
- Pairing images by array position can associate unrelated outputs and hide missing deliverables; exact declared artifact names provide a stable correspondence.
- Collapsing multiple judgments into one score removes reviewer disagreement. Separate records retain the evidence and review conditions.

## Consequences

The [viewer documentation](../../../../../../benchmarks/skill_bench/README.md) describes the layout. [Projection tests](../../../../../../benchmarks/skill_bench/tests/test_report_evidence.py) cover missing images, extras, distinct captures, applicable atoms, missing reviews, reviewer filters, legacy context and private cases. Browser inspection checks actual alignment, folding, original-size images and mobile overflow. Trusted HTML must be regenerated after this renderer change; report JSON, image bytes and judgments remain unchanged. Rendering and verification do not invoke a model.
