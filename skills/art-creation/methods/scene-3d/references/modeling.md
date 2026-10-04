# Model and Refine a 3D Form

## Select a construction rule

- Primitives and transforms: block out proportions and spatial arrangements.
- Extrusion: extend a contour into depth when the cross-section is the concept.
- Lathe: rotate a radius/height profile around an axis for vessels and axial forms.
- Repetition/instancing: organize repeated objects with explicit spacing and variation.
- Editable meshes: add detail only where the selected silhouette or structure needs it.

Separate geometry, camera, lighting, and material parameters. An apparent shape change may be a viewpoint change; compare them independently after selecting a form. Record coordinate axes, scale, transforms, profile/topology, and camera projection.

## Portable lathe study

The bundled Python generator samples explicit radius/height profiles into rings, joins neighboring rings with quads, and closes ends with triangles. The vase profile is a solid silhouette study, not a hollow vessel. OBJ indices are one-based. The same vertices are rotated for the chosen camera view and projected into SVG; faces are depth-sorted and receive simple normal-based shading.

This preview uses orthographic projection and painter-style face ordering. It does not model perspective, realistic materials, transparency, cast shadows, or general intersecting-scene occlusion. Use a real 3D renderer for those questions, or use the browser-3D method. The recipe records these limits.

## Improve a selected model

If the silhouette is wrong, adjust its profile or proportions. If depth is unclear, test view angle or projection while preserving the mesh. If faceting is the issue, increase radial segments or use the target renderer's smoothing; extra geometry does not fix an unsuitable overall form. For materials, compare roughness, light placement, or texture scale in an actual material renderer.

Before an export claim, inspect bounds, finite coordinates, valid indices, face orientation, and whether required surfaces are open or closed. For production work, check the target application's topology, units, normals, and export needs. Choose an available modeler for detailed editing; report its actual version and the artifact it produces. A shape study cannot certify fabrication suitability.
