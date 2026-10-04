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

These are imported instructions. Match APIs to the installed Remotion version; do not assume every newer Studio feature exists. Dependency installation is an implementation step only when it belongs to the user's requested project.

## Construct a temporal description

Specify resolution, frame rate, total duration, essential content, shot intervals, subject versus camera motion, and sound requirements. Convert seconds to explicit frame ranges and separate source observations from suggested timings.

Create the simplest composition that tests the hypothesis. Hold assets and content fixed between variants. For each moving property, derive its state from `useCurrentFrame()` and the declared parameters. Use `interpolate()` with explicit clamping when the property should stop at its endpoints. Reset any simulation or seeded randomness so seeking to a frame yields the same result.

Use [the composition starter](templates/CreativeStudy.jsx) in an existing project. It uses React.createElement and frame-derived states. Register separate compositions or parameter sets for different motion directions and preserve accepted timing. Reference project assets explicitly; source URLs, fonts, and audio are dependencies.

## Preview, diagnose, and export

Open an actual Studio/player preview before claiming a temporal result. Seek to start, transitions, overlap boundaries, and end; also play the sequence. Compare rhythm, attention, continuity, and audio sync based on user feedback. Inspect a few representative rendered frames before final video export.

CSS or browser wall-clock animation does not define reproducible Remotion motion. The imported 3D reference explains the same restriction for Three.js content. If this runtime is unavailable, a timeline and playable native-browser study can still test direction; label that fallback and do not claim a Remotion render.

Return editable composition, parameters, frame ranges, asset list, actual playback or rendered video, verification scope, and user decision. The skill-package MIT license is separate from the Remotion runtime's own terms.
