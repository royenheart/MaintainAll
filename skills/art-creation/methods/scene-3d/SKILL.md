---
name: scene-3d
description: Use within art-creation for procedural 3D form, silhouette, camera, or spatial arrangement studies that need editable meshes and actual projected previews.
---

# Procedural 3D Scenes

Read the [method contract](../../references/method-contract.md), then [modeling and refinement](references/modeling.md) for construction details.

## Build the simplest actual geometry

Translate the desired effect into object proportions, contour/profile, spatial relationships, camera projection, and lighting direction. Separate object shape from the camera's view of it. Establish scale and axes explicitly.

Use primitives, extrusion, lathe surfaces, or repeated instances to express the idea. For detailed mesh, material, or render work, use a modeler such as Blender and its installed API.

[The portable scene generator](scripts/scene.py) uses Python's standard library to construct a closed lathe mesh. It exports OBJ, a scene recipe, and a flat-shaded orthographic SVG from the same vertices. Run it with a task-local output directory:

```bash
python3 <method-dir>/scripts/scene.py --shape vase --width 1.0 --height 2.0 --yaw 30 --output ./study-a
```

Replace `<method-dir>` with this method's directory and read `--help` for shapes and parameters. Use a new output directory for each iteration. Change profiles for broad directions; keep geometry fixed when testing camera yaw.

## Render and improve

Display the SVG directly or rasterize it. Inspect silhouette, proportions, overlap, depth ordering, and framing. For an unclear contour, compare profile and camera changes separately. For a faceted surface, adjust resolution or smoothing settings.

For interactive orbiting or realistic materials, use [web 3D](../web-3d/SKILL.md) or a 3D renderer.

For application backends, consult [Blender execution](references/blender.md) or [Houdini execution](references/houdini.md). For clothing or avatars, use [Fashion and avatar design](../../references/fashion-design.md).

Return the model, recipe, displayed preview, parameters, and next decision.
