# Construct and Refine Browser 3D

Follow the Three.js [scene guide](https://threejs.org/manual/pages/creating-a-scene.html) and [responsive guide](https://threejs.org/manual/pages/responsive.html) for the runtime's current details; reuse the target project's version when available.

1. Establish scene, camera, and renderer using the display container's ratio and a deliberate camera target.
2. Construct geometry from the brief: primitives, profiles, extrusion, explicit meshes, or suitable assets.
3. Choose materials and lights. Hold geometry and lighting fixed for material comparisons; hold material fixed for lighting comparisons.
4. Expose useful controls and current values. Rebuild/dispose geometry for shape changes; update camera or material without replacing the accepted mesh.
5. Update camera projection and renderer size on container resize. Bound pixel ratio, avoid unnecessary continuous work, and dispose replaced resources.
6. Display the rendered scene and exercise its controls.

The starter uses a lathe mesh, a perspective camera, ambient plus directional lighting, and a roughness-adjustable material. Its explicit controls make studies replayable. When testing color or roughness, keep view and light fixed. When testing camera perspective, keep object dimensions fixed. Explain what each difference shows, then return user feedback to the parent workflow.

CDN imports load the module and its internal dependencies. For an offline environment, use a compatible local module or the project's bundler. Serve previews over HTTP and record the library version and path.

For a static form study, display an offline-rendered mesh image or SVG projection.
