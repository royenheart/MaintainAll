# Iterative Creation

Help a non-expert discover a creative result through comparison and feedback. The goal is a progressively clearer expression of the user's intent, supported by visible prototypes and an executable brief. Do not make knowledge of design terminology a prerequisite, or equate a longer prompt with a better result.

This workflow adapts the mechanisms discussed in [Practice review](practice-review.md). It is a practical interaction policy, not a claim that language-only reasoning matches all perception or world modeling, or establishes general intelligence.

## Detailed description and construction methods

Choose the representation that tests the next uncertainty, then load only its linked skill. Every method reads the shared [method contract](method-contract.md) and returns its result to this workflow; it does not independently choose what the user prefers. Its references and executable starters load only when needed.

| Next question / representation | Detailed skill | Concrete support |
|---|---|---|
| Rules, particles, flow, repetition, seeded textures | [Algorithmic art](../methods/algorithmic-art/SKILL.md) | Rule construction, p5.js viewer, seed and parameter export |
| Static composition, palette, lettering, poster or illustration layout | [Canvas design](../methods/canvas-design/SKILL.md) | Layout/type diagnosis, SVG starter, rendering guidance |
| Movement, state changes, temporal feel, playable UI/graphic studies | [Motion studies](../methods/animate/SKILL.md) | Motion recipes, native browser playback and scrubbing |
| Compare directions, adjust a few properties, preserve a choice | [Visual variants](../methods/visual-variants/SKILL.md) | Portable comparison viewer, explicit selection and live recipe capture |
| Object form, silhouette, proportions, spatial arrangement | [Procedural 3D](../methods/scene-3d/SKILL.md) | Mesh construction, OBJ and SVG generation from the same geometry |
| Camera, material, interactive 3D in a webpage | [Web 3D](../methods/web-3d/SKILL.md) | Actual Three.js scene, controls, resizing and resource guidance |
| Shots, sound, frame-accurate animation, video export | [Remotion video](../methods/remotion-video/SKILL.md) | Imported topic references, frame-derived composition starter |

Use SVG/block studies when they can settle layout without a larger runtime. Use 3D geometry when form or viewpoint is the question; use browser 3D when interaction or material inspection is needed. Distinguish wall-clock preview motion from frame-based video construction. A missing runtime changes what can be verified, not the user's desired medium. Use the disclosed fallback in that method, or report the specific missing dependency.

The adopted methods preserve source attribution and explain their adaptations in [Upstream sources](upstream-sources.md). This index is part of the full skill bundle; distributing only the root SKILL.md omits executable guidance.

## 1. Start from the smallest useful description

Accept rough words, sketches, reference images, a webpage, or an example clip. Extract the requested medium, use, essential content, stated likes/dislikes, and constraints already present. Ask a plain-language question only if an unresolved detail changes the next useful experiment. Otherwise label a reasonable assumption and begin; do not demand expert names, palettes, or typography specifications.

Build a small working brief with:

- User statements and hard constraints.
- Observed reference features, separately from their interpretation.
- Preference hypotheses and unresolved questions.
- The next visible experiment and what its comparison will teach.

For a reference, use the analysis dimensions in [Style analysis](style-analysis.md). Give the full two-chapter report when requested; during exploration, use only the findings needed for the current decision. Do not treat an attractive reference as proof the user wants all its features.

## 2. Analyze and construct with language and programs first

Inspect available text, editable source, SVG paths, DOM/styles, image dimensions and pixel statistics, scene geometry, or clip timing. Choose methods from [Programmatic visual methods](visual-methods.md) that can answer the actual question. Translate results into understandable observations rather than asking the user to read code, histograms, or coordinates.

Begin with the simplest representation that can test the desired quality: arrangement blocks, a silhouette, a few colors, a camera setup, or keyframes. Increase detail only when it helps settle the next uncertainty. A draft must still be complete enough to compare; explicitly label what it demonstrates and what it does not model. Keep the final medium fixed unless the user changes it.

Use multimodal or world-model assistance only for a named gap that language and programmatic evidence cannot adequately resolve, such as ambiguous depicted subject, material semantics, occluded action, or motion interpretation beyond available tracking. Name what was inspected or what representation is unavailable, explain why it is insufficient, and limit assistance to that gap. Do not manufacture a failed attempt, use lack of vocabulary as the reason, or make irrelevant tool experiments merely to satisfy this preference. A palette histogram does not establish narrative meaning; a movement vector does not establish intention.

If a final raster subject needs generative rendering that the programmatic approach cannot practically express, explain that concrete limitation and use available specialist tools within the task's authorization. Keep the brief, composition, and other confirmed decisions inspectable. No automatic external skill installation or provider setup is part of the creative workflow.

Dispatch to the selected detailed method with the working brief, accepted constraints, comparison stage, intended output, and available runtime. Record which representation is used and what it cannot demonstrate. Receive its actual preview and recipe before entering the feedback step below.

## 3. Explore visibly different directions

For an open idea, normally show three contrasting directions; adapt the count to the user's request and available resources. Keep content, medium, and hard constraints comparable. Choose meaningful axes supported by the request, such as composition, visual rhythm, material, contrast, silhouette, or motion character. At this early stage, directions may vary several related dimensions together. Do not reduce the alternatives to tiny hue or corner-radius changes.

For an established design whose identity the user wants to retain, explore different expressions within that identity. Broader stylistic departure fits an open brief or a request for a new direction, not an unrequested redesign.

Give each direction a stable ID and one short explanation of its visual mechanism and intended effect. Render it at the same scale and comparable fidelity. Show the previews side by side or as a clearly labeled sequence. Use an animation or timeline playback when the difference is temporal; stills alone cannot demonstrate easing, rhythm, or continuity. Follow [Programmatic visual methods](visual-methods.md) when the host needs screenshots or raster exports to display a code-built preview.

Keep chance controlled: record seeds for stochastic work, keep assets and rendering conditions fixed where relevant, and record the intentional differences. The goal is an interpretable comparison, not unrelated random outputs.

## 4. Ask for reactions rather than vocabulary

After displaying the alternatives, ask one compact question that resolves the main uncertainty. Accept a choice, an everyday description, a combination of parts, or rejection of all candidates. Useful feedback includes:

- Which direction is closest, and which part should stay?
- Which part feels wrong, and should it be quieter, heavier, warmer, or simpler?
- Does the user prefer one option's arrangement but another's surface treatment?

Use the host's text-input mechanism when available. Do not require a specialized UI or multiple-choice selection. Describe only differences the user can actually see. Teach the useful term after explaining the visible feature in ordinary words.

Wait for the user's reaction before choosing among preference-dependent branches. Silence is not a choice. A round can end with visible candidates and a pending question; do not declare aesthetic convergence or invent feedback. If the user explicitly delegates selection, choose a direction with a stated rationale and keep its status distinct from user-confirmed preference.

## 5. Refine without losing accepted choices

Translate feedback into a concrete update to the working brief. Keep accepted features and rejected directions explicit. Convert vague reactions into tentative, observable changes: for example, calmer might mean less contrast, fewer competing shapes, wider spacing, or slower motion. Test the likely interpretation; do not silently treat one mapping as universal.

Once a direction is chosen, change only one or two unresolved dimensions per comparison where practical. Keep an unchanged accepted preview available, label the new version, and explain what changed and what the comparison tests. Offer two small variations or an adjustable preview when that makes the decision easier. Favor a few meaningful controls, named in everyday language, over a dense settings panel. Every control must visibly work and affect the intended property.

Move from coarse structure to finer color, typography, contour, texture, lighting, or movement according to the current uncertainty. This is not a mandatory order for every medium. If all directions miss the target, revisit the premise or show a new contrasting branch rather than polishing the least disliked one indefinitely.

Maintain a concise decision record:

| Version | Preview and method | Intent tested / variables changed | Keep | Reject | Still uncertain |
|---|---|---|---|---|---|

Keep the record in conversation unless a saved project artifact is useful and within the requested scope. If saving, use a task-local location, preserve prior iterations, and record source assets, parameters, seeds, dimensions, and timing needed to reproduce the comparison. Do not overwrite the supplied reference.

## 6. Converge and hand off

Stop at the user's chosen level of completion: an agreed direction, a reusable prompt, an editable prototype, or a finished asset. Check the latest visible result against the accepted decisions and objective constraints. Do not imply that geometry checks establish aesthetic satisfaction, or call a composition sketch a finished painting.

When handing off, provide:

- The accepted result or latest candidate, with its actual confirmation status.
- A concise brief covering purpose, medium, subject/content, layout, palette roles, typography when relevant, contour/material, imagery, and temporal behavior if needed.
- Features inherited from references, changes for the intended use, and new suggestions.
- One complete implementation prompt and observable acceptance criteria.
- Editable source or parameters and reproducibility details when artifacts were created.
- Open uncertainties that materially affect implementation.

Do not add unrequested polishing rounds after the agreed result passes its checks.

## Reusable starting prompt

The following English instruction is maintained in the repository; execute it in Chinese unless the user chooses another language. Fill it from the conversation instead of making the user complete a long form.

```text
Act as a creative partner who helps a non-expert discover and express their intent.
Start from my rough description, sketch, reference, or clip. Keep my requested
medium and essential content. Separate what I stated, what the reference shows,
and what you hypothesize about my preferences. Assume only what is needed to begin.

Prefer natural-language reasoning and inspectable programs. Use source, geometry,
pixel statistics, timelines, SVG, canvas, procedural models, or frame-based rendering
when they can answer the question or build a useful preview. Explain a concrete
remaining gap before using multimodal or world-model assistance; use it only for
that gap. Measurements cannot establish my preferences without feedback.

Begin with a simple prototype that tests the main structure or effect. Show several
clearly different, labeled, comparable visual directions, normally three. Actually
render and display them when possible; explain a specific limitation otherwise.
For motion, show temporal behavior rather than relying only on still frames.
Explain differences in ordinary language, then ask one small feedback question.
Do not choose for me or infer approval from silence unless I delegated selection.

After my feedback, record what to keep, reject, and explore. Preserve accepted
choices, then compare small variations of one or two uncertain dimensions. Keep
versions and random seeds comparable. If none fit, revisit the assumptions.
Teach useful vocabulary through the visible examples instead of testing my knowledge.

When the result reaches the completion level I requested, provide the confirmed
brief, the visible result, one complete implementation prompt, observable acceptance
criteria, and any editable source or parameters. Distinguish inherited features,
use-specific adjustments, new suggestions, and unresolved hypotheses.
```
