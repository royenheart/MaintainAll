# Programmatic Visual Methods

Choose tools that answer the current visual question. Inspect what is available before choosing a renderer; no named package or model is required by this skill. Use existing tools and project infrastructure rather than installing a large stack for a simple experiment. Verify current library details if implementation needs them.

## Analysis and preview index

| Material / question | Inspectable method | Useful output | Limit |
|---|---|---|---|
| Web layout and typography | Read source and computed DOM styles; measure actual element rectangles | Region map, layout alternatives, rendered HTML/CSS preview | Source-only reading does not establish runtime appearance |
| Raster palette and contrast | Read pixels; sample named regions; histogram or cluster colors with documented settings | Palette roles and sampled values | Compression, antialiasing, crops, and clustering affect values; no proof of style or mood |
| Image structure | Dimensions, edges, masks, contours, connected components, explicit coordinates | Silhouettes, composition guides, overlays | Detected boundaries do not identify subjects or component purpose reliably |
| Illustration and poster direction | SVG paths, text, grids, procedural strokes, or canvas | Comparable composition, type, and surface studies | A coarse sketch does not reproduce photographic or expressive detail |
| 3D composition and lighting | Parameterized primitive meshes, camera, lights, and materials | Views that vary perspective, silhouette, or lighting | A simple scene does not establish complex physical behavior |
| Clip structure and rhythm | Metadata, timecodes, shot boundaries, frame sampling, waveform when relevant | Timeline, frame contact sheet, short actual playback | A contact sheet omits continuous timing and sound |
| Motion between frames | Classical feature tracking or optical flow; separate global and local displacement | Arrows, trajectories, stabilized comparisons | Occlusion, cuts, camera motion, and low texture can mislead; vectors are not action semantics |
| Animation creation | Keyframes, paths, easing curves, frame-index functions, existing animation runtime | Scrubbable or playable comparisons | A single frame cannot show speed or easing |

These are options, not required steps. When a measurement cannot settle a semantic question, mark its limit and use only the assistance needed for that question. Do not present a generated or procedurally reconstructed reference as a measurement.

## Direct annotation on the actual input

1. Resolve the actual material and its dimensions. For a webpage, render the supplied route and capture it at a recorded viewport; for a clip, extract actual frames and keep their timecodes. If input is unavailable, do not invent a substitute.
2. Choose an overlay method. For a raster image, an SVG with an embedded original image plus transparent rectangles and numbered labels is sufficient. A raster drawing library can instead composite the same marks over a copy. For a webpage, a temporary DOM overlay can use actual bounding rectangles, or annotate its screenshot.
3. Use one coordinate system. Keep native dimensions or apply the same scale and crop transform to the source and markings. Separate CSS pixels from screenshot pixels when device pixel ratio differs; include scroll offsets for full-page views.
4. Keep regions and components identifiable. Use red strokes, contrast-backed numbers, and leaders where needed. Fit markers within the display area and avoid key text. For nested or very long input, make separate overview/detail views with continuous IDs and explicit crop/parent context.
5. Render the overlay and inspect correspondence against the actual input. Check dimensions, valid boundaries, label visibility, and table IDs. Keep the original unchanged and ensure it is the actual base layer.
6. Directly display the resulting view. If the host can render SVG or HTML inline, use that; if it only displays raster images, rasterize or screenshot the overlay with an available renderer and embed/display that output. A local path alone does not prove the user can see it.

Making and displaying an overlay are separate capabilities. If one route fails, try an available equivalent that preserves the original. If no route can work, name the precise failure (for example, image-only display but no available SVG rasterizer), then provide locations and containment without claiming visible annotation. Merely lacking a dedicated image-editing tool is not a sufficient reason.

## Comparable previews

- Use the same content, canvas dimensions, scale, and rendering conditions across variants unless the variation explicitly tests one of them.
- Render actual SVG/HTML/canvas/model output rather than showing only its source. Screenshot or export to a supported image format when needed. A comparison sheet can combine rendered alternatives without altering source-reference annotations.
- Label variant ID, fidelity, and intended change. A layout wireframe tests spatial structure; it should not claim to prove paint texture or facial expression.
- Expose meaningful parameters only when they help the next decision. Translate internals into understandable controls such as spacing, softness, density, or pace. Retain precise values in the editable source and explain units when useful.
- If playback cannot be displayed, show timestamped frames and a timing description, explicitly identifying which temporal properties remain unverified. Do not claim a still-frame fallback fully demonstrates the animation.

## Motion as an explicit language

Describe each important movement by object, trigger or start time, initial and final state, path, duration, easing, relationship to other movement, and intended effect. For video, record frame rate, shot intervals, camera versus subject motion, transitions, and relevant sound timing. Mark reference observations separately from proposed timings.

A parameterized animation can be expressed as properties of object and time, with keyframes or functions controlling them. This supports precise revision and playback; it does not establish that inferred movement matches an unseen reference.

For interface animation, inspect purpose, interruption, repeated use, actual device performance, and reduced-motion behavior. For expressive animation, let the brief determine its motion vocabulary; UI timing and style preferences are not universal rules for character animation or film.
