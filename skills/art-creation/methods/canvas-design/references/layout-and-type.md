# Static Layout and Typography Studies

## Construct a composition

Set canvas ratio, margins, alignment anchors, and major regions before details. Choose a focal element and a specific relationship to supporting elements: alignment, containment, overlap, separation, repetition, or deliberate imbalance. Broad candidates can change that relationship while keeping the same content.

Treat typography as visible shapes and as readable content. Establish display, supporting, and detail roles; choose relative size and weight before naming a font family. Measure actual glyph bounds and line wrapping in the selected renderer. When a font is substituted, record the substitute and recheck layout rather than assuming metrics are interchangeable.

For SVG, use explicit dimensions/viewBox, named groups, palette roles, and editable text when possible. Convert text to paths only when necessary for delivery and retain an editable source. For raster work, keep source layers or drawing commands so a local correction does not require reconstructing the entire composition.

## Translate feedback into bounded changes

| Reaction | Inspect before editing | A useful comparison |
|---|---|---|
| Too crowded | Competing focal regions, occupied area, spacing, wrapping | Keep hierarchy; reduce one density source |
| Too weak | Relative scale, contrast, subject placement | Keep palette; strengthen one focal relation |
| Too mechanical | Repetition, symmetry, contour uniformity | Compare bounded irregularity against baseline |
| Too decorative | Relation of ornament to content and hierarchy | Remove one class of ornament while keeping structure |
| Not enough material feel | Texture scale, contour, edge/light behavior | Keep layout; compare a specific material treatment |

The user determines which interpretation fits. Keep the accepted result available. Check clipping, accidental collision, unreadable text, and export dimensions. Differentiate useful intentional overlap from mistakes rather than applying a universal ban on overlapping elements.

## Render and deliver

Use an available browser, SVG rasterizer, or drawing renderer to display the actual artifact. Keep the same font and viewport when comparing. Export the final format at the requested resolution, retain editable source, and label estimated or recommended values rather than presenting them as measured from a reference.
