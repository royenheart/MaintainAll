# Construct and Refine Generative Rules

## From impression to a mechanism

Identify what repeats, what changes, and what constrains the change. Start from the user's hypothesis instead of selecting a fashionable effect.

| Desired relation | Possible rule | Useful controls | Diagnose |
|---|---|---|---|
| Related strokes moving together | Agents follow a spatially coherent direction field | Density, field scale, step length | Incoherence: inspect field continuity before slowing everything |
| Organic but orderly distribution | Constrained sampling or repulsion between points | Separation, irregularity, focal bias | Clumps: inspect minimum distance and boundary handling |
| Growth or accumulation | Iterative branching or deposition with bounded budgets | Branch ratio, spread, steps | Noise: limit offspring or overlap rather than adding blur |
| Geometry with a human irregularity | A stable grid plus bounded displacement | Spacing, displacement, repetition | Lost structure: inspect perturbation relative to cell size |
| Tension through repetition | Repeated shapes with a controlled gradient of scale/orientation | Scale ratio, angle range, rhythm | Weak focus: inspect distribution of extremes |

These are construction hypotheses, not universal mappings from adjectives. For each candidate state the actual rule, expected visible effect, and comparison that can confirm whether it moves toward the user's intent.

## Make the implementation inspectable

Separate initialization, state updates, rendering, and controls. Define units and boundary behavior. Clamp indices before reading a field; wrap, reflect, or stop agents deliberately. Avoid mixing random calls from UI behavior with the artwork's seeded generator. Reset the full state when a parameter or seed changes.

For a static result, render a fixed number of steps from the seed. For animation, use fixed simulation steps or compute state from time/frame; pin capture time when comparing. Seed alone does not preserve output if algorithm, assets, size, step count, or dependency version differs.

## Improve through experiments

Preserve the seed when testing rule parameters. Preserve parameters when exploring seeds. If a feature is absent across seeds, repair its mechanism rather than searching indefinitely for one lucky sample. Inspect composition and palette roles at a reduced scale before increasing particle counts or adding texture.

The bundled viewer demonstrates a coherent field, bounded particle movement, palette roles, and deterministic static accumulation. Its trail control changes simulation length; it is not a measurement of a reference video's duration. Replace the mechanism when the user's idea requires a different one.
