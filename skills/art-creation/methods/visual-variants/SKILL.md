---
name: visual-variants
description: Use within art-creation when alternative visual expressions need visible comparison, a few adjustable properties, selection, and preservation of accepted decisions.
license: Apache-2.0; see LICENSE and NOTICE.md
---

# Visual Variants

Adapted from Impeccable's generate/live planning and selection mechanisms; see [upstream sources](../../references/upstream-sources.md). Read the [method contract](../../references/method-contract.md). This portable adaptation uses ordinary previews rather than Impeccable's binary helper or event protocol.

## Plan differences before rendering

Identify the invariant content and accepted identity: palette roles, type voice, layout relationships, contour/material, and relevant behavior. Preserve them for refinement. For an open brief or requested new direction, explore broader identities.

Choose a distinct primary axis for each candidate: hierarchy, spatial arrangement, color strategy, material, density, or movement. Make each direction concrete enough that its difference can be explained without generic adjectives. Plan the few parameters worth exposing at the same time. Do not merely generate unrelated seeds.

## Execute comparison

Use the actual construction method for each candidate: [canvas](../canvas-design/SKILL.md), [algorithmic rules](../algorithmic-art/SKILL.md), [motion](../animate/SKILL.md), [scene modeling](../scene-3d/SKILL.md), [web 3D](../web-3d/SKILL.md), or [video](../remotion-video/SKILL.md). Load only the chosen construction method.

Use [the comparison starter](templates/compare.html) when a local browser is useful. Its bundled cards are labeled examples; replace `variants` with the actual rendered candidates using same-origin `src` URLs or `srcdoc`, stable IDs, and descriptions. It displays previews and records a choice only after the user presses Choose. Recipe export collects each child preview's `exportRecipe()` when available; otherwise it explicitly records that live parameters are unavailable.

The viewer can export a selection record; it does not modify artwork source or infer acceptance from the first displayed candidate. If the browser cannot be shared, show a rendered comparison sheet and obtain feedback in conversation.

## Refine and commit the choice

Translate the chosen parts into the parent decision record. Preserve the accepted baseline and vary one or two unresolved properties. A selection may combine parts of candidates or reject them all. When embedding the final choice into a real project, edit its owning source, not generated build output, and remove temporary comparison wrappers only after the accepted result is preserved.

Return candidate sources and previews, intentional differences, captured parameter values, actual confirmation status, and the next uncertainty. Do not wait for or invent an Impeccable event in this portable workflow.
