---
name: canvas-design
description: Use within art-creation for static composition, poster, illustration, typography, or palette studies that need editable 2D construction and rendered comparisons.
license: Apache-2.0; see LICENSE.txt
---

# Canvas Design

Adapted from Anthropic's canvas-design; see [upstream sources](../../references/upstream-sources.md). Read the [method contract](../../references/method-contract.md) for round inputs and handoff. Use [layout and typography](references/layout-and-type.md) for details.

## Establish a direction

Describe the compositional rule: what leads, how supporting content relates to it, how space is divided, and which palette or material quality carries the intended effect. Set content, text density, and visual character from the brief.

## Construct a static study

1. Set canvas ratio, output dimensions, and the level of detail needed for the study.
2. Separate background, primary subject, supporting forms, and text into editable layers. Use SVG for simple vector work, canvas or a drawing library for raster strokes, or the project's established renderer. Reuse supplied imagery when it is part of the chosen design.
3. Establish focal size, placement, alignment anchors, and empty space before adding fine texture. Use [the SVG starter](templates/composition.svg) as an executable layout example only when that structure fits the experiment.
4. Choose fonts for the intended hierarchy and character. Check glyphs, text bounds, wrapping, and contrast in the renderer.
5. Display the render directly or through a rasterized image or screenshot. Export PNG/PDF when requested and retain editable source.

## Diagnose and improve

When feedback says crowded, compare occupied area, focal elements, line length, and separation. When it says weak, compare scale hierarchy and contrast. When a style feels inconsistent, compare repeated shape, type, spacing, and texture rules.

For initial exploration, vary composition or visual mechanism substantially. After acceptance, keep content and layout stable while testing a small change. Respect useful intentional overlaps; fix accidental collisions and clipping.

Return source, displayed preview, dimensions, fonts/assets, the tested idea, and the next feedback question.
