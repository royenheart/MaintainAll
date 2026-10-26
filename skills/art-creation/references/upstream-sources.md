# Adopted Sources and Local Adaptations

Reviewed: 2026-10-04. This bundle contains adapted instructions and selected resources. The [source lock](../upstream-lock.json) records revisions, source paths, original and current hashes, and modification status. Original resources are identified below.

## Source inventory

| Local method | Pinned upstream source | License | Included resources and changes |
|---|---|---|---|
| [Algorithmic art](../methods/algorithmic-art/SKILL.md) | Anthropic [algorithmic-art](https://github.com/anthropics/skills/blob/8a1541c4a3ffa5a20a5a91de0dcf3f0bab1d1ef4/skills/algorithmic-art/SKILL.md) | [Apache 2.0](../methods/algorithmic-art/LICENSE.txt) | Adapted entrypoint, generator patterns, and viewer. The viewer includes a seeded flow example, parameter reset, fixed simulation steps, recipe export, and neutral styling. The rule/diagnosis guide is original. |
| [Canvas design](../methods/canvas-design/SKILL.md) | Anthropic [canvas-design](https://github.com/anthropics/skills/blob/8a1541c4a3ffa5a20a5a91de0dcf3f0bab1d1ef4/skills/canvas-design/SKILL.md) | [Apache 2.0](../methods/canvas-design/LICENSE.txt) | Adapted entrypoint with a concise brief, user-directed typography and density, and visual feedback. Original layout/type guide and editable SVG starter. |
| [Animate](../methods/animate/SKILL.md) | Impeccable [animate](https://github.com/pbakaus/impeccable/blob/e103efe779e2dd01274dabae83531fef00bf2563/skill/reference/animate.md) | [Apache 2.0](../methods/animate/LICENSE), [notice](../methods/animate/NOTICE.md) | Adapted motion-purpose and verification workflow; original motion recipes and playable/scrubbable native-browser study. Motion preferences remain contextual, and reduced motion is observable. |
| [Visual variants](../methods/visual-variants/SKILL.md) | Impeccable [live](https://github.com/pbakaus/impeccable/blob/e103efe779e2dd01274dabae83531fef00bf2563/skill/reference/live.md), with [generate](https://github.com/pbakaus/impeccable/blob/e103efe779e2dd01274dabae83531fef00bf2563/skill/reference/generate.md) as a researched comparison | [Apache 2.0](../methods/visual-variants/LICENSE), [notice](../methods/visual-variants/NOTICE.md) | Adapted comparison/selection guidance; original iframe comparison template with click selection and current child-parameter capture. |
| [Remotion video](../methods/remotion-video/SKILL.md) | Official [Remotion Codex plugin](https://github.com/remotion-dev/codex-plugin/blob/10bf0018eb1d5ca03d08116c97416972d3ee0b47/skills/remotion-markup/SKILL.md) | [MIT](../methods/remotion-video/LICENSE) | Adapted entrypoint and timing, sequencing, compositions, metadata, composition connection, audio, and 3D references. Original frame-derived composition starter. |
| [Scene 3D](../methods/scene-3d/SKILL.md) | Original implementation | [MPL 2.0](../LICENSE) | Modeling/diagnosis guide and standard-library OBJ + SVG generator with replayable mesh/camera parameters and orthographic, depth-sorted projection. |
| [Web 3D](../methods/web-3d/SKILL.md) | Original implementation, informed by official [Three.js scene](https://threejs.org/manual/pages/creating-a-scene.html) and [responsive rendering](https://threejs.org/manual/pages/responsive.html) guides | [MPL 2.0](../LICENSE) | Browser scene guide and open lathe-surface example with geometry, camera, material controls, reset, resize, and recipe export. |
| [Game engine](../methods/game-engine/SKILL.md) | Original implementation, informed by official [Godot](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_web.html) and [Temporal](https://docs.temporal.io/workflows) documentation | [MPL 2.0](../LICENSE) | Native GDScript comparison starter, build-linked human reactions, engine helper, and game/workflow guidance. Runtime binaries are installed separately under their own licenses. |

Full upstream license and notice files are retained. Adapted entrypoints link here for attribution. Local adaptations use concise construction guidance and natural paragraph lines; the source lock tracks their current hashes.

Imported and adapted files retain the licenses shown above. Original resources follow the repository's [MPL 2.0 license](../LICENSE), included for standalone distribution. Runtime applications carry their own licenses.

## Runtime and packaging

- Copy the complete `art-creation/` directory for distribution. Resolve relative links from their containing file.
- Register the root skill for discovery and load nested methods through the [iterative method index](iterative-creation.md#detailed-description-and-construction-methods).
- The [method contract](method-contract.md) connects construction output to the iterative workflow.
- The procedural viewer loads p5.js 1.7.0 from a CDN. The browser-3D example loads Three.js 0.180.0; its `three` URL parameter can select a compatible local module with matching imported dependencies.
- Motion and comparison templates use native browser APIs. The mesh generator uses Python 3; SVG raster export uses an available renderer. The video starter integrates into a React/Remotion project.
