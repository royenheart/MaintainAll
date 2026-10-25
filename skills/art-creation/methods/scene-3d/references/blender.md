# Blender Execution

Use Blender for editable geometry, materials, cameras, cloth, or asset preparation. See the [method contract](../../../references/method-contract.md) for handoff and [Tool capabilities](../../../references/tool-capabilities.md) for setup.

Inspect the installed Python API for node types, sockets, properties, and evaluated geometry. Build editable meshes, Geometry Nodes, materials, cameras, or simulation as needed. Connect fields to geometry consumers to produce the intended output.

An available CLI can run a task-local construction script without the UI:

    <blender> --background --factory-startup --python-exit-code 1 --python task.py

Replace `<blender>` with the executable path. Use factory startup for a new study or load the source file for an existing project. Save geometry, parameters, and the `.blend` file, then render and inspect the scene.

Keep camera, lighting, scale, assets, seeds, and simulation state comparable. For garments, choose direct modeling, patterns, or cloth according to the current question. Display renders or playback and prepare the chosen runtime representation.

Primary references: [CLI arguments](https://docs.blender.org/manual/en/latest/advanced/command_line/arguments.html), [Python API](https://docs.blender.org/api/current/). Workflow background: [NodeCue source](https://github.com/nodecue/blender-node-skills/tree/0179e84a6b3e016478b944dc9d6d9862429dce86).
