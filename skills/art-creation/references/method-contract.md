# Method Contract

This connects a detailed construction method to [Iterative creation](iterative-creation.md). Read it once per task, including when a method is invoked directly. Shared principles remain those of [Art Creation](../SKILL.md); do not recursively reload already-read instructions or unrelated methods.

## Input to a method

- The user's actual medium, purpose, required content, and task-local asset/output paths.
- The next hypothesis to test and stage: broad exploration or limited refinement.
- Confirmed choices and hard constraints, separated from uncertain interpretations.
- Available renderer, project/version, preview/display capabilities, and dependencies.
- Accepted baseline when present; comparable size, seed/time conditions, and fidelity.

Infer routine construction details when safe and label assumptions. Ask for a preference only when it determines a branch; a method does not run an independent expert questionnaire or replace the parent's decision record.

## Output to the parent

Return a small, concrete result containing:

| Field | Meaning |
|---|---|
| Hypothesis and method | What this representation tests, and why it fits |
| Candidate IDs and differences | Stable identifiers and intentional changes |
| Source and actual preview | Editable artifact plus displayed render or playback |
| Recipe | Current parameters, assets, dimensions, seed, timing, version, and replay method as relevant |
| Evidence and limits | What ran, what was inspected, runtime/render/display limitations |
| Decision status | Pending, explicitly user-selected, or selected under delegated authority |
| Next question | One understandable choice or reaction that resolves the uncertainty |

When useful, store this information as a task-local JSON recipe. Recipe exports must reflect current controls, not defaults. A default visible candidate is not accepted. The comparison viewer's Choose button records an actual selection; conversation feedback can do the same without a browser helper.

## Execution rules

1. Construct from the brief, preserving confirmed decisions. Begin with the simplest representation that can test the question.
2. Render and display actual results. An imported skill or a saved HTML file is not evidence that its external scripts, fonts, graphics context, or export run.
3. Use comparable conditions and inspect the intended difference. Keep reference annotations based on actual input, separate from candidate construction.
4. Return candidates for feedback. Do not self-certify a preferred aesthetic, invent acceptance, or continue a preference-dependent branch without a reply.
5. Refine the cause of the observed issue with limited changes, preserving the accepted baseline and recipe. Keep prior iterations available.

The method skills include instructions and selected executable resources, not all rendering applications. Preserve the requested medium when a dependency is missing; mark a simpler study as partial. Runtime setup is within scope when the user requested a project that needs it; it is not performed merely by loading a skill.
