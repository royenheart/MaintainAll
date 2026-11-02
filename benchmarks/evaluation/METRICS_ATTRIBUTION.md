# Attribution metrics

Two metrics are reported separately. They answer different questions and must not be merged.

## Semantic accuracy

An independent blind judge (fresh agent, no arm or truth labels) reads the anonymized report and cited tool outputs and labels the layer. Semantic accuracy = judge label equals the case truth's `expected_blocker`.

## Evidence completeness

The frozen grader checks that the report cites a real tool call, the quote is a verbatim substring of that result, the quote supports the expected layer, completion matches, and the blocker label matches. Evidence completeness = grader `passed`.

## Results

| case | truth | arm | valid n | semantic | evidence |
|---|---|---|---|---:|---:|
| sandbox-natural-11 | both | A0 | 2 | 2/2 (100%) | 0/2 (0%) |
| sandbox-natural-11 | both | B | 3 | 3/3 (100%) | 3/3 (100%) |
| sandbox-natural-09 | dsh | A0 | 3 | 3/3 (100%) | 0/3 (0%) |
| sandbox-natural-09 | dsh | B | 3 | 3/3 (100%) | 3/3 (100%) |
| sandbox-natural-08 | app | A0 | 1 | not judged | 1/1 |
| sandbox-natural-08 | app | B | 1 | not judged | 1/1 |

- case11 semantic labels: two independent blind judges each returned 5/5 `both` for the 5 valid samples (2 A0, 3 B).
- case09 semantic labels: the blind judge returned `dsh` for all 6 valid samples (3 A0, 3 B).
- A0 was excluded from case11 n=3 when its run hit `tool-call budget exceeded`; that run is not counted.

## Interpretation

A0 already names the correct layer semantically in these valid samples; its failures are evidence-format failures. The measured skill increment is therefore evidence completeness, not basic layer recognition. B is the only arm that combines correct labels with verified citations.

## Limits

- Small n (2-3 per cell), one model, one fixture family, one host.
- Blind judges were same-provider subagents, not a different model family.
- case11 replaced case01/case02 as the only active `both` case; case01 is retired and case02 is a `missing-input` control.
