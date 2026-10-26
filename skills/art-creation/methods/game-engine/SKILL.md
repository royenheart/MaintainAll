---
name: game-engine
description: Use within art-creation to turn game ideas, sketches, and player feedback into native engine prototypes, playable comparisons, and verified builds. Includes game controls and rules as well as visuals.
---

# Native Game Construction

Read [Progressive game creation](../../references/game-creation.md) for requirements and human feedback. Start playable work in the selected game engine and evolve that same project. Establish the [feedback path](../../references/feedback-setup.md) with native playback, a compatible engine Web export, or streamed native execution. [Remote preview](references/remote-preview.md) compares these delivery routes. Game behavior stays in the native project throughout iteration.

## Construct the next experiment

Translate the next hypothesis into engine scenes, nodes, resources, input actions, state transitions, and a short play scenario. Keep accepted properties stable while changing the properties being tested. Use named parameters or resources for meaningful alternatives; save sources and build identity with the result.

For Godot, read [Godot execution](references/godot.md). The [project helper](scripts/godot_project.py) copies a native starter, checks a scene, exports Web/Linux builds, and serves an exported game. Its [starter project](templates/feel-lab/project.godot) compares two movement profiles in one level and records compact human reactions through Godot controls. Adapt its scenes, rules, and questions to the intended experiment.

Use existing art methods for assets when useful: [procedural rules](../algorithmic-art/SKILL.md), [2D composition](../canvas-design/SKILL.md), [3D modeling](../scene-3d/SKILL.md), and [clothing or avatars](../../references/fashion-design.md). Verify imported assets, animation, timing and interaction in the actual engine scene.

## Play, measure, and refine

Verify resource import and startup, then exercise the intended controls, state change, failure/recovery path, and delivery target. A headless scene check covers startup behavior; camera, audio, motion, input feel, and browser compatibility need actual execution and appropriate observation.

Deliver the playable link/build, a brief action to try, the relevant comparison, and a few build-linked questions. Include measured observations where useful and preserve the user's preference answers independently. Carry accepted choices into the next build.

Return native editable source, engine/version and export settings, current decision records, and the reproducible build command. For a future application that enforces this loop, consult [Workflow orchestration](references/workflow-orchestration.md).
