# Design constraints

## Composition

Preserve a compact personal homepage: avatar and two navigation links, an uninterrupted central scene, a bottom music area and official registration links. Desktop uses a narrow left rail; widths at or below 720 CSS pixels use a horizontal top navigation. Avoid introducing a marketing hero, dashboard cards, or a different information hierarchy.

The original desktop composition was captured before migration and compared with the live rebuilt scenes at 1440x900. The scene math and shaders preserve the large perspective cube cloud and the bright golden rim/dark core/accretion bands. A screenshot is permitted only as a loading or unavailable-graphics poster. Do not substitute it for working scene geometry.

## Tokens and layout

`src/styles/tokens.css` is the shared token source for the light cyan chrome, dark ink, borders, focus color, rail width, footer height, timing, and system font stack. Scene palettes belong to `src/content/scenes.json`. Keep font sizes relative to the root font size so text enlargement is effective.

Use CSS Grid and Flexbox for page structure, container queries for music density, `clamp()` for continuous dimensions, dynamic viewport units for browser chrome, and safe-area insets. Tailwind 4 supplies the shared CSS tooling and utilities. Do not maintain separate mobile/tablet/desktop component trees or a JavaScript device-size registry.

The scene may intentionally crop at different aspect ratios; navigation, focus rings, music controls, and registration content must remain accessible. Very short screens may scroll vertically. Horizontal document overflow and clipped controls are defects. Track titles may use ellipsis when the full label is available through the title or native selector.

Controls have at least 44px height. Scene controls also have at least 44px width. The keyboard skip link, visible focus treatment, accessible scene names, and keyboard dismissal of music are part of the design.

## Motion and rendering

- Motion owns DOM enter/scene-change feedback. Keep the single live Canvas stable across scene changes.
- R3F owns frame scheduling and canvas sizing. Use frame refs instead of React state for per-frame values.
- Drei measures sustained rendering pressure and reduces DPR/instance density. Library adaptation does not guarantee identical frame rates across devices.
- Pause stops continuous render submissions. Reduced motion and hidden/offscreen content use a demand loop. Resizing and scene changes may still request a necessary frame.
- Seed particle placement. `capture=1` freezes time for reproducible review; normal rendering remains animated.
- Dispose geometries/materials and detach listeners. A failed chunk, missing WebGL, or lost context preserves both scene choices through posters.

## Review evidence

Inspect actual screenshots at phone, tablet, and desktop dimensions, including both scenes. Check shapes and composition, not only the presence of a canvas. Then run the shared geometry oracle and interaction tests. Test width and height independently around the breakpoint. Keep browser/OS and software rendering limitations with performance evidence.

Scene math can remain custom because it defines the artwork. Renderer construction, animation scheduling, resizing, and device adaptation should remain library-owned.
