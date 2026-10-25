---
name: visual-variants
description: Use within art-creation when alternative visual expressions need visible comparison, a few adjustable properties, selection, and preservation of accepted decisions.
license: Apache-2.0; see LICENSE and NOTICE.md
---

# Visual Variants

Adapted from Impeccable's generate/live planning and selection mechanisms; see [upstream sources](../../references/upstream-sources.md). Read the [method contract](../../references/method-contract.md).

## Plan differences before rendering

Identify the invariant content and accepted identity: palette roles, type voice, layout relationships, contour/material, and relevant behavior. Preserve them for refinement. For an open brief or requested new direction, explore broader identities.

Choose a distinct primary axis for each candidate: hierarchy, spatial arrangement, color strategy, material, density, or movement. Describe the visible difference and choose a few parameters to expose.

## Execute comparison

Use the actual construction method for each candidate: [canvas](../canvas-design/SKILL.md), [algorithmic rules](../algorithmic-art/SKILL.md), [motion](../animate/SKILL.md), [scene modeling](../scene-3d/SKILL.md), [web 3D](../web-3d/SKILL.md), or [video](../remotion-video/SKILL.md). Load only the chosen construction method.

Use [the comparison starter](templates/compare.html) for a local browser comparison. Replace `variants` with rendered candidates using same-origin `src` URLs or `srcdoc`, stable IDs, and descriptions. The Choose button records a selection. Recipe export collects each child preview's `exportRecipe()` when available.

A rendered comparison sheet also supports selection and feedback in conversation.

## Refine and commit the choice

Translate the chosen parts into the parent decision record. Preserve the baseline and vary one or two unresolved properties. A selection may combine parts of candidates or reject them all. Integrate the chosen design into the project's source and remove temporary comparison wrappers.

Return candidate sources and previews, intentional differences, captured parameters, user feedback, and the next question.
