# Construct and Refine Browser 3D

Follow the Three.js [scene guide](https://threejs.org/manual/pages/creating-a-scene.html) and [responsive guide](https://threejs.org/manual/pages/responsive.html) for the runtime's current details; reuse the target project's version when available.

1. Establish scene, camera, and renderer. Use the display container's ratio and a deliberate camera target, not a guessed window size.
2. Construct geometry from the brief: primitives, profiles, extrusion, or explicit meshes. Reuse licensed assets only when they are needed for this experiment.
3. Choose a material and actual lights suited to the question. A material comparison must retain geometry and lighting; a light comparison must retain the material.
4. Expose useful controls and current values. Rebuild/dispose geometry for shape changes; update camera or material without replacing the accepted mesh.
5. Update camera projection and renderer size on container resize. Bound pixel ratio, avoid unnecessary continuous work, and dispose replaced resources.
6. Verify rendered pixels and actual interaction. Catch module/WebGL failures and show a clear limitation; do not leave an empty canvas described as a preview.

The starter uses a lathe mesh, a perspective camera, ambient plus directional lighting, and a roughness-adjustable material. Its explicit controls make studies replayable. When testing color or roughness, keep view and light fixed. When testing camera perspective, keep object dimensions fixed. Explain what each difference shows, then return user feedback to the parent workflow.

CDN imports require network access and include the module's internal dependencies. For an offline environment, point the starter to an existing local compatible module or use the project's bundler. Serve module previews over HTTP. Record the library version and path used; copying the HTML does not install the runtime.

If WebGL is unavailable, display an actual offline-rendered mesh preview when possible, with its projection/material limits. A SVG form study can answer a silhouette question but cannot demonstrate a Three.js material or orbit control.
