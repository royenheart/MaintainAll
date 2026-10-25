# Houdini Execution

Use Houdini for procedural geometry, attributes, constraints, simulation, or reusable assets. See the [method contract](../../../references/method-contract.md) for handoff and [Tool capabilities](../../../references/tool-capabilities.md) for setup.

Represent semantic parts and relationships explicitly in SOP geometry and attributes. Choose VEX for element-level rules and HOM Python for scene orchestration, parameter exposure, and output. Inspect current node types, parameters, inputs, and evaluated output; keep version-specific names in the task recipe.

An available licensed Python runtime can execute a task-local script:

    <hython> task.py

Replace `<hython>` with the executable path. HOM constructs nodes through `hou.node(...).createNode(...)`; connect the network, set parameters, cook it, and inspect geometry and errors. Save the scene and display a viewport capture or render.

For rules and constraints, retain part identities and relationships. For Vellum cloth, keep panels/seams, initial placement, materials, collision state, timing, and caches with the scene. Package useful controls as an HDA for reuse. Select an export route supported by the project's license mode and destination format.

Primary references: [HOM](https://www.sidefx.com/docs/houdini/hom/), [node API](https://www.sidefx.com/docs/houdini/hom/hou/Node.html), [Vellum paneling](https://www.sidefx.com/docs/houdini/vellum/paneling_draping.html), [licensing](https://www.sidefx.com/Support/licensing/). Optional programming references: [hou-python and hou-vex](https://github.com/rheadsh/audiovisual-production-skills/tree/8616953f90933cd25205c77b40f5db0a94b46f74); inspect only what the task needs.
