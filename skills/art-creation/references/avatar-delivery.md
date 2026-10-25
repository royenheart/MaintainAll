# Avatar Delivery

Choose the production route for the intended character and application. The [avatar runtime guide](avatar-runtimes.md) covers model playback.

| Route | Construction and delivery |
|---|---|
| Live2D | Separate layers, draw hidden areas, assign meshes/deformers/parameters, and preview combined motion through Cubism Core |
| VRoid | Choose garment geometry, edit its UV texture, inspect texture mapping, save the source, and export VRM |
| Custom real-time 3D | Build meshes, UVs/materials, skeleton/weights, and runtime cloth or secondary motion; export and inspect intended poses in the target application |

For parts that move independently, define attachment and motion ownership. Preview relevant combinations and viewing angles, including hidden or overlapping content exposed by movement.

Keep the editable source, export, renderer version, and preview together. Derive resource budgets and motion ranges from the target application.

Implementation references: [VRoid custom items](https://vroid.pixiv.help/hc/en-us/articles/900005583186-How-to-Use-Custom-Items), [Live2D material separation](https://docs.live2d.com/en/cubism-editor-manual/divide-the-material/), [VRM specification](https://github.com/vrm-c/vrm-specification). Community workflows: [VRoid skill](https://github.com/Sunwood-ai-labs/build-vroid-character-skill/tree/e0a4e461b4568c3eadd5f1838a6b2e9893eaec29), [Live2D kit](https://github.com/Ariakage/live2d-agent-kit/tree/94e79e3a94753ae1bd29204d3ed685a3c7b59022).
