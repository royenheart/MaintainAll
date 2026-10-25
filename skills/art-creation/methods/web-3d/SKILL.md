---
name: web-3d
description: Use within art-creation for browser-rendered 3D scene, camera, geometry, or material exploration with interactive controls and actual WebGL previews.
---

# Web 3D Exploration

This is an original method informed by the Three.js [scene guide](https://threejs.org/manual/pages/creating-a-scene.html) and [responsive guide](https://threejs.org/manual/pages/responsive.html). Read the [method contract](../../references/method-contract.md), then [browser scene construction](references/browser-scenes.md) when implementing.

## Create a view that tests the question

Separate scene, camera, geometry, material, lighting, and interaction. Choose an orthographic view for proportions or a perspective view for depth. Begin with primitives or a procedural mesh and give the scene visual prominence.

[The Three.js starter](templates/scene.html) builds lathe geometry with controls for shape, width, camera angle, and roughness, plus recipe export. It loads Three.js 0.180.0 from a CDN; the `three` query parameter selects a compatible same-origin module with its matching core dependency. Serve the study over HTTP and display it in a WebGL-capable browser.

## Make experiments interpretable

Render distinct form or material directions under comparable framing. After selection, adjust one or two unresolved properties. Rebuild geometry for shape changes and update camera/material properties independently. Display current values, provide reset, and capture the recipe on selection.

Size the renderer to its container, update camera projection on resize, and set pixel ratio for the target device. Dispose of replaced geometry and pause rendering when hidden. A rendered image can provide a static preview.

Check rendering, resizing, controls, reset, and recipe replay. For video export, use [Remotion video](../remotion-video/SKILL.md). Return the editable scene, preview, recipe, dependencies, and next feedback question.
