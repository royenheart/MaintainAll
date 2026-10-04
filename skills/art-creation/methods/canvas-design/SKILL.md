---
name: canvas-design
description: Use within art-creation for static composition, poster, illustration, typography, or palette studies that need editable 2D construction and rendered comparisons.
license: Apache-2.0; see LICENSE.txt
---

# Canvas Design

Adapted from Anthropic's canvas-design; see [upstream sources](../../references/upstream-sources.md). Read the [method contract](../../references/method-contract.md) for round inputs and handoff. Use [layout and typography](references/layout-and-type.md) for details.

## Establish a direction

Describe the compositional rule in a few concrete sentences: what leads, how supporting content relates to it, how space is divided, and which palette or material quality carries the intended effect. Preserve required content. The user's brief determines text density, playfulness, and medium; minimal text, thin type, and an abstract art aesthetic are not universal constraints.

## Construct a static study

1. Set the actual canvas ratio and output dimensions. Mark coarse composition studies as coarse; do not treat them as finished paintings.
2. Separate background, primary subject, supporting forms, and text into editable layers. Use SVG for simple vector work, canvas or a drawing library for raster strokes, or the project's established renderer. Reuse supplied imagery when it is part of the chosen design.
3. Establish focal size, placement, alignment anchors, and empty space before adding fine texture. Use [the SVG starter](templates/composition.svg) as an executable layout example only when that structure fits the experiment.
4. Use available project or system fonts; identify a substitution. No bundled font directory or external font download is required. Check actual glyphs, text bounds, wrapping, and contrast with the selected font.
5. Render and display actual output. For an SVG-only display limitation, use an available rasterizer or screenshot. Export PNG/PDF when that is the requested final medium and preserve editable source alongside it.

## Diagnose and improve

When feedback says crowded, inspect occupied area, competing focal elements, line length, and separation. When it says weak, inspect scale hierarchy and contrast before adding decoration. When a style feels inconsistent, inspect repeated shape, type, spacing, and texture rules. Treat these as hypotheses to compare visually, not universal interpretations of the user's words.

For initial exploration, vary composition or visual mechanism substantially. After acceptance, keep content and layout stable while testing a small change. Respect useful intentional overlaps; fix accidental collisions and clipping.

Return source, displayed preview, dimensions, font/assets, measured versus suggested values, the tested hypothesis, and the next feedback question. A self-polished composition remains a candidate until the user accepts it.
