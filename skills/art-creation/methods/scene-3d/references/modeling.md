# Model and Refine a 3D Form

## Select a construction rule

- Primitives and transforms: block out proportions and spatial arrangements.
- Extrusion: extend a contour into depth when the cross-section is the concept.
- Lathe: rotate a radius/height profile around an axis for vessels and axial forms.
- Repetition/instancing: organize repeated objects with explicit spacing and variation.
- Editable meshes: add detail only where the selected silhouette or structure needs it.

Separate geometry, camera, lighting, and material parameters. An apparent shape change may be a viewpoint change; compare them independently after selecting a form. Record coordinate axes, scale, transforms, profile/topology, and camera projection.

## Portable lathe study

The bundled Python generator samples radius/height profiles into rings, joins neighboring rings with quads, and closes ends with triangles. The vase profile forms a solid mesh. OBJ indices are one-based. The same vertices are rotated for the camera view and projected into SVG; faces are depth-sorted and receive normal-based shading.

The SVG preview uses orthographic projection and painter-style face ordering. Use a 3D renderer or the browser-3D method for perspective, materials, transparency, shadows, and intersecting geometry.

## Improve a selected model

For silhouette changes, adjust profile or proportions. For depth, compare view angles or projection while preserving the mesh. For faceting, adjust radial segments or smoothing. For materials, compare roughness, light placement, or texture scale in a material renderer.

Inspect mesh bounds, coordinates, indices, face orientation, and open or closed surfaces. For production export, use the target application's topology, units, normals, and format requirements.
