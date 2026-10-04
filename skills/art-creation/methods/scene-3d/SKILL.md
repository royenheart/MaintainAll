---
name: scene-3d
description: Use within art-creation for procedural 3D form, silhouette, camera, or spatial arrangement studies that need editable meshes and actual projected previews.
---

# Procedural 3D Scenes

This is an original method, not a copied upstream skill. Read the [method contract](../../references/method-contract.md), then [modeling and refinement](references/modeling.md) for construction details.

## Build the simplest actual geometry

Translate the desired effect into object proportions, contour/profile, spatial relationships, camera projection, and lighting direction. Separate object shape from the camera's view of it. Establish scale and axes explicitly.

Use primitives, extrusion, lathe surfaces, or repeated instances when they can express the hypothesis. For more detailed mesh, material, or render work, use the available project modeler such as Blender after inspecting its version and APIs. Do not claim a procedural study is a finished production or manufacturing model.

[The portable scene generator](scripts/scene.py) requires only Python's standard library. It constructs a closed lathe mesh and exports OBJ, the exact scene recipe, and an SVG projected from the same vertices with simple directional shading. Its rendering is a flat-shaded orthographic form study, not a physically based material render. Run it from a task-local output directory:

```bash
python3 <method-dir>/scripts/scene.py --shape vase --width 1.0 --height 2.0 --yaw 30 --output ./study-a
```

Resolve `<method-dir>` to this skill's actual location; never execute the placeholder. Read `--help` for other shapes and bounds. Change shape profiles for broad directions; keep geometry fixed when testing camera yaw. The script refuses to overwrite its three output artifacts, so each new iteration uses a new directory.

## Render and improve

Display the generated SVG directly or rasterize it with an available renderer. Inspect silhouette, proportions, overlap, depth ordering, and framing. To improve an unclear contour, compare profile or camera changes separately; to improve a faceted surface, change resolution or the target renderer's smoothing settings. Lighting or camera changes must not silently replace the accepted geometry.

For interactive orbiting or realistic material studies, use [web 3D](../web-3d/SKILL.md) or the available 3D runtime. Confirm the actual mesh, view, and render rather than presenting an invented lookalike.

Return model/recipe, displayed preview, projection and shading limitations, exact parameters, and next decision to the parent. A `.blend` export requires Blender; the portable script produces an OBJ and does not pretend otherwise.
