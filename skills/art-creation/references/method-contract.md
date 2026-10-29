# Method Contract

This connects a construction method to the [iterative workflow](iterative-creation.md).

## Input to a method

- Medium, purpose, required content, and asset/output paths.
- The next design question and stage: broad exploration or focused refinement.
- Accepted choices, constraints, and the current baseline.
- Renderer, project version, and comparison conditions such as size, seed, and time.
- The established [feedback path](feedback-setup.md): launch/viewing route, tested conditions, and question/answer channel.

Resolve linked resources relative to their containing file. The [resource index](resource-index.md) locates detailed guidance; [Intent and evidence](intent-and-evidence.md) helps clarify aesthetic language.

## Output to the workflow

Return a small, concrete result containing:

| Field | Meaning |
|---|---|
| Hypothesis and method | What this representation tests, and why it fits |
| Candidate IDs and differences | Stable identifiers and intentional changes |
| Source and preview | Editable artifact plus displayed render or playback |
| Recipe | Current parameters, assets, dimensions, seed, timing, version, and replay method as relevant |
| Feedback path | How the user opens or experiences the result, responds to its version, and reuses the setup |
| Feedback | Selected, retained, and rejected features |
| Next question | One understandable choice or reaction that resolves the uncertainty |

A preview is the rendered artifact the reader can see; a path or source listing alone is not a preview.

Store current control values in a JSON recipe when replay helps. Capture selections through the comparison viewer's Choose button or conversation feedback. Independent construction, research, or review can use [optional delegation](delegation.md).
