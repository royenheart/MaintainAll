# Decision: Bounded supplementary skill evaluation

Status: implemented — supplementary runs and independent reviews are complete under a separate manual launch budget, preserving earlier evidence.

## Problem

The [previous decision](../../../../../../docs/research/art-skill-diversity-2026-10-13/refinement-decision.json) defers adoption because the static paired baseline lacks a complete episode. Four original-session dynamic cases also lack complete episodes. Reusing a diagnostic baseline, replacing failed results or silently spending an old reservation would obscure what was actually compared.

## Decision

The [supplementary protocol](../../../../../../docs/research/art-skill-supplement-2026-10-25/plan.md) fixes one new static pair and four retained-skill dynamic episodes under a new 18-launch ceiling. Cases, skill snapshots, generation settings and review semantics remain fixed. New runtime identities are recorded before generation. Actual source reopening and anonymous review remain separate from execution completion. Prior records and the eight human binary answers remain immutable.

## Alternatives considered

- Substituting an earlier complete diagnostic baseline would compare independently selected episodes outside the frozen pair.
- Automatically retrying until completion or a preferred rating would hide execution variability and weaken the predeclared stopping rule.
- Changing the candidate while filling coverage gaps would confound the instruction experiment.
- Running all development and holdout tasks would spend more calls than needed to address the identified evidence gaps and expose reserved holdouts prematurely.

## Consequences

The incomplete original static comparison stays visible even if the new pair completes. Dynamic one-arm results cannot establish candidate improvement. A changed renderer identity and evaluation date form a distinct runtime condition. Adoption follows the existing gate, not the number of completed turns or a sum of ordinal scores.

The [installation observation](../../../../../../docs/research/art-skill-supplement-2026-10-25/installed-skill-observation.json) records a different current installed bundle. Generation uses the intended private frozen snapshots, while the current installation stays untouched. An experimental effect on those snapshots does not establish compatibility or benefit for the different installed bundle.

The [execution record](../../../../../../docs/research/art-skill-supplement-2026-10-25/execution-results.json) seals 17 launches: 16 completed turns, one timed-out turn and one unstarted planned turn. Original-session task coverage reaches eight of nine complete episodes. The [review record](../../../../../../docs/research/art-skill-supplement-2026-10-25/review-results.json) adds 81 related atom-turn observations. The new static pair is similar; together with the earlier native preference, it meets the limited predeclared evidence gate without demonstrating a general gain. The [decision](../../../../../../docs/research/art-skill-supplement-2026-10-25/refinement-decision.json) does not replace repository or installed skill files.

The [Chinese report](../../../../../../docs/research/art-skill-supplement-2026-10-25/report.md) distinguishes partial audio responsiveness from completed delivery, missing pause-state measurements from observed failure, and ambiguous inherited label requirements from proven supersession. Future dataset revisions must clarify those conditions without rewriting frozen ratings. Three new private reports and the data-derived landing pass desktop/mobile browser checks; [verification metadata](../../../../../../docs/research/art-skill-supplement-2026-10-25/final-verification.json) records their evidence and preserves earlier report identities.
