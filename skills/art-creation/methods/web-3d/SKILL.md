---
name: web-3d
description: Use within art-creation for browser-rendered 3D scene, camera, geometry, or material exploration with interactive controls and actual WebGL previews.
---

# Web 3D Exploration

This is an original method informed by the Three.js [scene guide](https://threejs.org/manual/pages/creating-a-scene.html) and [responsive guide](https://threejs.org/manual/pages/responsive.html). Read the [method contract](../../references/method-contract.md), then [browser scene construction](references/browser-scenes.md) when implementing.

## Create a view that tests the question

Separate scene, camera, geometry, material, lighting, and interaction. Choose an orthographic view for proportions or a perspective view when depth is the subject of the experiment. Begin with primitives or a procedural mesh instead of unrelated model assets. Keep page chrome from competing with the actual scene.

[The Three.js starter](templates/scene.html) builds actual lathe geometry, exposes shape, width, camera angle, and material roughness, and exports the current recipe. It loads Three.js 0.180.0 from a pinned CDN URL; an explicit `three` query parameter can point to an available same-origin module instead. The matching core module must also be available for that build. Serve the copied study over HTTP, verify runtime loading and WebGL, and then display it. Neither the library nor a browser is installed by this skill.

## Make experiments interpretable

Render several distinct form or material directions under comparable framing. After the user chooses, retain the mesh and adjust one or two dimensions. Rebuild geometry only for geometry changes; camera and material adjustments should preserve shape. Display current values and provide reset. Capture the current recipe when the user selects a result, not just startup defaults.

Size the renderer to the actual container, update camera projection on resize, and bound pixel ratio for the target device. Dispose of replaced geometry and stop unneeded work when hidden. Keep a static fallback when WebGL is unavailable, clearly identifying which interactive/material properties it cannot demonstrate.

Check loading errors, nonempty pixels, resizing, changed-control effects, reset, and recipe replay. For motion destined for video, load [Remotion video](../remotion-video/SKILL.md); a free-running render loop is not a frame-accurate export. Return editable scene, actual preview, recipe, dependency requirements, limitations, and the next feedback decision.
