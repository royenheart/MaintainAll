# Tool Capabilities

Choose an application for the design question: editable geometry, cloth response, material rendering, or target-runtime playback.

The [runtime probe](../scripts/probe_runtime.py) locates Blender or Houdini executables and offers a Blender version query. Read `--help` for arguments and examples.

| Selected backend | Read when useful |
|---|---|
| Blender geometry, materials, cameras, cloth, or asset preparation | [Blender execution](../methods/scene-3d/references/blender.md) |
| Houdini rules, attributes, constraints, simulation, or reusable assets | [Houdini execution](../methods/scene-3d/references/houdini.md) |
| Avatar-specific editing and delivery | [Avatar delivery](avatar-delivery.md) |

For a selected backend, resolve its executable and version, complete the needed setup, create a small study, and display the result. Keep useful commands and version information with the task so later iterations can reuse the setup. Export in the format required by the chosen delivery route.
