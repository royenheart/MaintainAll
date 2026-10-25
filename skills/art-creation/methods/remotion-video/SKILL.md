---
name: remotion-video
description: Use within art-creation for frame-based video composition, shot timing, animated graphics, or reproducible video variants in an existing Remotion project.
license: MIT; see LICENSE
---

# Frame-Based Video

Adapted from the MIT-licensed official Remotion Codex plugin; see [upstream sources](../../references/upstream-sources.md). Read the [method contract](../../references/method-contract.md) first.

## Choose references on demand

| Need | Read |
|---|---|
| Timing, easing, and bounded interpolation | [Timing](references/timing.md) |
| Shot intervals and overlaps | [Sequencing](references/sequencing.md) |
| Composition registration and metadata | [Compositions](references/compositions.md) |
| Audio timing or levels | [Audio](references/audio.md) |
| Three.js content rendered to video | [3D](references/3d.md) |

Match the reference APIs to the project's installed Remotion version.

## Construct a temporal description

Specify resolution, frame rate, total duration, essential content, shot intervals, subject versus camera motion, and sound requirements. Convert seconds to explicit frame ranges and separate source observations from suggested timings.

Create the simplest composition that tests the hypothesis. Hold assets and content fixed between variants. For each moving property, derive its state from `useCurrentFrame()` and the declared parameters. Use `interpolate()` with explicit clamping when the property should stop at its endpoints. Reset any simulation or seeded randomness so seeking to a frame yields the same result.

Use [the composition starter](templates/CreativeStudy.jsx) in an existing project. It uses React.createElement and frame-derived states. Register separate compositions or parameter sets for different motion directions and preserve accepted timing. Reference project assets explicitly; source URLs, fonts, and audio are dependencies.

## Preview, diagnose, and export

Open a Studio/player preview. Seek to start, transitions, overlap boundaries, and end; then play the sequence. Compare rhythm, attention, continuity, and audio sync through user feedback. Inspect representative frames before video export.

Return the editable composition, parameters, frame ranges, assets, playback or rendered video, and user feedback.
