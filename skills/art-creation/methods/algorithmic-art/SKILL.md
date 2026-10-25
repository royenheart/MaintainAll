---
name: algorithmic-art
description: Use within art-creation when a visual idea can be expressed through procedural rules, particles, flow fields, geometric systems, or seeded textures, and needs reproducible parameter exploration.
license: Apache-2.0; see LICENSE.txt
---

# Algorithmic Art

Adapted from Anthropic's algorithmic-art; source revision and modifications are in [upstream sources](../../references/upstream-sources.md). Read the [method contract](../../references/method-contract.md) before executing a round.

## Express the idea as rules

Write a short direction tied to the user's idea: entities, relationships, evolution, constraints, and palette roles. Read [rule construction](references/rules.md) when choosing or refining an algorithm. Explore distinct governing rules for initial directions.

1. Choose entities: points, strokes, cells, curves, or agents.
2. Define spatial relationships or update rules: adjacency, attraction, repulsion, field following, growth, symmetry, or constrained displacement.
3. Define boundaries and stopping conditions, relating each rule to the intended visual quality.
4. Expose a few useful dimensions in everyday language, such as density, softness, regularity, or speed. Keep all other generation settings fixed for comparison.

## Build and show

Adapt [the viewer](templates/viewer.html), a seeded flow-field example with controls, reset, PNG export, and recipe export. Replace its algorithm and interface to match the brief. [The upstream generator reference](templates/generator_template.js) provides implementation patterns.

The viewer uses p5.js 1.7.0 from a CDN and can use a compatible local runtime. Load it in the browser and display the preview.

Seed random and noise sources on each deterministic render. Record dimensions, parameters, palette, algorithm version, seed, and iteration count. For motion, derive state from frame/time or use a fixed-step simulation with a reset path.

## Improve through feedback

Show contrasting rules at comparable fidelity, then return the user's choice to the parent workflow. During refinement, preserve the rule and seed while changing one or two meaningful parameters. Diagnose clutter through density, overlap, or contrast; diagnose weak structure through field coherence, focal distribution, or repetition. Change the mechanism that caused the issue and render again.

Check seed replay, parameter changes, reset, recipe export, and visual output. Return the source, displayed preview, recipe, and next decision.
