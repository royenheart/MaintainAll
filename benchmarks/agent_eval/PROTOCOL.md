# Skill iteration with an evolving evaluation dataset

The old loop froze the cases at the start. That makes saturation and reward hacking
likely: both arms pass, the remaining signal is report wording, and the skill is tuned
to the same visible examples. This protocol inserts an **evaluation audit and data
refresh** step between scoring and validation.

## Loop

1. **2.1 Directions.** Subagents + GPT propose skill directions from current results.
2. **2.2 Implement and score.** Produce 2-3 variants; adversarial review; run the
   frozen development set; keep raw traces and per-case scores.
3. **2.2.5 Audit the evaluator and refresh data.** Required, before validation:
   - compute per-case saturation, floor, with/without gap, repeats and variance;
   - flag cases where every arm is at max, where a grader accepts keyword-only
     reports, where fixtures/reports contain the answer, or where the prompt names the
     expected finding;
   - check fixture mutation and grader independence;
   - spawn 2-3 subagents + GPT with the results and manifest to propose new cases,
     harder variants, distractors and a holdout;
   - add at least one **new challenge case** and one **frozen holdout**; do not tune on
     the holdout; version the dataset and record why each case exists;
   - recalibrate known-good/broken before any model run.
4. **2.3 Validation.** Run the updated development set and the untouched holdout;
   report per-case, not just aggregate.
5. **2.4 Feed back.** Saturation or no spread means the case is a control or too easy;
   retire it from the discriminating set and add a harder one.

## Dataset rules

- The dataset must contain **more than 30 cases** (31+), across at least five categories, plus at
  least one frozen holdout. Generated/templated cases count only after known-good and
  broken calibration. A refresh that drops to 30 or below is a failed 2.2.5.
- Every case has a split: `control`, `development`, or `holdout`.
- At least one holdout stays unseen by the skill author until final validation.
- A case enters the discriminating set only after known-good/broken calibration and
  at least two paired trials per arm.
- Keep case SHA, prompt, fixture tree, grader SHA, and a short "what would make this
  fail" note in `datasets/validation-<n>.json`.
- Replace, do not silently edit, a case that has saturated. Old cases stay as controls.
- Do not let a grader accept only keywords; require evidence, IDs, fixed versions,
  file paths, or a diff/trace.
- Hidden tests may hide inputs, never requirements.

## Reward-hack checks

- Fixture mutation (report files excluded) invalidates the trial.
- The prompt must not name the expected advisory ID, CVE, issue number or fix.
- The grader must not be inside the case directory; hash it separately.
- A "clean" result must list what was not verified.
- A model that always says vulnerable must fail distractor packages.
- A model that always says clean must fail a case with a real finding.


## Problem-scale targets

Do not grow the dataset only with 2-6 file fixtures. Use three explicit tiers:

| Tier | Files | Dependency nodes | Surfaces | Findings | Distractors |
|---|---:|---:|---:|---:|---:|
| small | 8-15 | 10-30 | 2-3 | 0-2 | 3-6 |
| medium | 40-100 | 100-300 | 4-6 | 3-6 | 12-25 |
| large | 300-800 | 1k-3k | 8-12 | 8-15 | 40-100 |

The current `scale-large-*`/`scale-medium-client` cases are the first steps; generated
2-6 file cases are smoke/regression controls, not discrimination evidence. A case is
promoted only after known-good/broken calibration and paired trials. Large cases must
add interacting behavior, not filler.

GPT review of the generated cases found: keyword-only reports can score full marks,
circular calibration from expected strings, contradictory clean case, missing
entrypoints, and too-small scale. The generator now requires a file:line evidence
string, coherent clean/uninstalled fixtures, and explicit scale metadata; the remaining
generated cases stay marked as smoke until paired evidence exists.
