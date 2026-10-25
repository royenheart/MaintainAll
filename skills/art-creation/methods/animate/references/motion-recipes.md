# Construct and Refine Motion

Write motion as an object and property changing over an explicit interval. Define start/end states, trigger, path, duration, progress curve, sequencing, and what happens on interruption. Label measured reference timing versus suggested timing.

| Motion idea | Construction | What playback tests |
|---|---|---|
| Arrival or departure | Interpolate position and opacity | Direction, travel, acceleration, and visibility |
| Reveal | Change a clip or mask while content stays placed | Whether the reveal supports the composition |
| Focus/depth | Scale with limited opacity/material change | Where attention settles and whether space feels coherent |
| Continuous state relation | Shared geometry or aligned endpoints | Whether the viewer understands the connection |
| Coordinated sequence | Explicit offsets between object intervals | Rhythm and competition for attention |

Begin with one main relation, then add supporting movement to clarify the chosen effect.

For native browser studies, Web Animations API provides explicit keyframes, duration, `currentTime`, play/pause, and restart. The bundled starter allows scrubbing to compare the same progress across mechanisms; playing is still required to judge temporal feel. Reset when changing a mechanism, and keep progress stable when comparing a duration change if that is the intended experiment.

For sluggish feedback, compare delay separately from duration. For an abrupt transition, compare boundary speed and endpoint states. For chaos, compare the timing of simultaneous focal events.

For reduced-motion interface preferences, retain visible state feedback with less spatial movement. Check rapid repeat actions and interruptions. Use the video method for frame-based export.
