# Avatar Runtimes

Read for model playback after selecting the delivery route. Choose the editor, rendering library, or tracking application needed by the task. See [Tool capabilities](tool-capabilities.md) for setup.

| Route | Execution sequence | Inspect |
|---|---|---|
| Live2D Web | Select compatible Cubism Core and Framework versions, load MOC3 and textures, initialize WebGL and the renderer, then apply model parameters | Parameter IDs/ranges, drawable geometry, and combined rendered states |
| Custom VRM | Export meshes, UVs/materials, and weighted skeleton as glTF with the VRM extension and humanoid mapping, then import through a VRM-aware target | Extension/version, mapped bones, materials, and pose deformation |

Read the selected version's API and loaded model schema. Use its parameter IDs and bones to construct meaningful poses and combined states, then compare them under consistent views.

The [official Live2D Web SDK](https://www.live2d.com/en/sdk/download/web/) supplies Core, Framework, and sample materials with their respective licenses. Use Cubism Editor for rig editing and MOC3 export, and Core for runtime playback.

[three-vrm](https://github.com/pixiv/three-vrm) provides a browser VRM loader on Three.js. Select compatible dependencies and consult the [VRM specification](https://github.com/vrm-c/vrm-specification) for the requested version. Inspect skinning, materials, poses, expressions, spring bones, and tracking as relevant to the character.

Keep version information and reusable commands with the project.
