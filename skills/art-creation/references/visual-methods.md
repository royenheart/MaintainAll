# Programmatic Visual Methods

Choose tools and representations that answer the current visual question, using the project's renderer and available inspection tools where useful.

## Analysis and preview index

| Material / question | Inspectable method | Useful output |
|---|---|---|
| Web layout and typography | Source, computed DOM styles, element rectangles | Region map, layout alternatives, rendered HTML/CSS |
| Raster palette and contrast | Named pixel samples, histograms, color clustering | Palette roles, sampled values, and sampling settings |
| Image structure | Dimensions, edges, masks, contours, connected components | Silhouettes, composition guides, overlays |
| Illustration and poster direction | SVG paths, text, grids, procedural strokes, canvas | Composition, type, and surface studies |
| 3D composition and lighting | Parameterized meshes, cameras, lights, materials | Views that vary perspective, silhouette, or lighting |
| Clip structure and rhythm | Metadata, timecodes, shot boundaries, frame sampling, waveforms | Timeline, frame contact sheet, playback |
| Motion between frames | Feature tracking or optical flow with global/local displacement | Arrows, trajectories, stabilized comparisons |
| Animation creation | Keyframes, paths, easing curves, frame-index functions | Scrubbable or playable comparisons |

## Direct annotation on the actual input

1. Resolve the material and its dimensions. For a webpage, capture the supplied route at a recorded viewport; for a clip, extract frames and retain their timecodes.
2. Choose an overlay method. For a raster image, an SVG with an embedded original image plus transparent rectangles and numbered labels is sufficient. A raster drawing library can instead composite the same marks over a copy. For a webpage, a temporary DOM overlay can use actual bounding rectangles, or annotate its screenshot.
3. Use one coordinate system. Keep native dimensions or apply the same scale and crop transform to the source and markings. Separate CSS pixels from screenshot pixels when device pixel ratio differs; include scroll offsets for full-page views.
4. Keep regions and components identifiable. Use red strokes, contrast-backed numbers, and leaders where needed. Fit markers within the display area and avoid key text. For nested or very long input, make separate overview/detail views with continuous IDs and explicit crop/parent context.
5. Render the overlay and check dimensions, boundaries, label visibility, and table IDs against the source base layer.
6. Display SVG or HTML inline, or rasterize the overlay and embed the resulting image.

The [browser capture helper](../scripts/capture_browser.py) uses Chromium to save a local page's screenshot, viewport, source hash, and execution status. Read `--help` for usage, then inspect and display the captured image.

## Comparable previews

- Use the same content, canvas dimensions, scale, and rendering conditions across variants unless the variation explicitly tests one of them.
- Display rendered SVG/HTML/canvas/model output, with screenshots or image exports for a comparison sheet.
- Label variant ID and intended change. Choose detail appropriate to the question, from a layout wireframe to a material study.
- Expose understandable controls such as spacing, softness, density, or pace. Retain precise values in the editable source and explain units when useful.
- Use playback for motion comparisons; timestamped frames and timing descriptions can accompany it.

## Motion as an explicit language

Describe each important movement by object, trigger or start time, initial and final state, path, duration, easing, relationship to other movement, and intended effect. For video, record frame rate, shot intervals, camera versus subject motion, transitions, and relevant sound timing. Mark reference observations separately from proposed timings.

A parameterized animation expresses properties of object and time through keyframes or functions, supporting precise revision and playback.

For interface animation, inspect purpose, interruption, repeated use, device performance, and reduced-motion behavior. For expressive animation, develop a motion vocabulary from the character or film brief.
