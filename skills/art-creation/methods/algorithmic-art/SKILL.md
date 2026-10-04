---
name: algorithmic-art
description: Use within art-creation when a visual idea can be expressed through procedural rules, particles, flow fields, geometric systems, or seeded textures, and needs reproducible parameter exploration.
license: Apache-2.0; see LICENSE.txt
---

# Algorithmic Art

Adapted from Anthropic's algorithmic-art; source revision and modifications are in [upstream sources](../../references/upstream-sources.md). Read the [method contract](../../references/method-contract.md) before executing a round.

## Express the idea as rules

Write a short direction tied to the user's actual hypothesis, not a mandatory manifesto. Specify the entities, relationships, evolution, constraints, and palette roles. Read [rule construction](references/rules.md) when choosing or repairing an algorithm. Different initial directions should change the governing rule, not just produce different seeds of one effect.

1. Choose entities: points, strokes, cells, curves, or agents.
2. Define spatial relationships or update rules: adjacency, attraction, repulsion, field following, growth, symmetry, or constrained displacement.
3. Define boundaries and stopping conditions. Explain which rule expresses the intended visual quality; random variation alone is not the concept.
4. Expose a few useful dimensions in everyday language, such as density, softness, regularity, or speed. Keep all other generation settings fixed for comparison.

## Build and show

Read [the viewer](templates/viewer.html) before constructing a p5.js preview. It is an executable seeded flow-field example with controls, reset, PNG export, and recipe export. Its interface is neutral and customizable; it is not the required visual identity of the artwork. Replace the example algorithm to match the brief. [The upstream generator reference](templates/generator_template.js) contains implementation patterns, not another complete runnable artwork.

The viewer uses p5.js 1.7.0 from a CDN. Reuse an existing compatible local runtime when available. Check script loading before reporting a visible preview; network access is a runtime dependency, not guaranteed by a single HTML file.

Seed random and noise sources on each deterministic render. Record dimensions, parameters, palette, algorithm version, seed, and iteration count. For motion, make state a reproducible function of frame/time or record a fixed-step simulation and reset path; an arbitrary screenshot time does not establish repeatability.

## Improve through feedback

Show contrasting rules at comparable fidelity, then return the user's choice to the parent workflow. During refinement, preserve the rule and seed while changing one or two meaningful parameters. Diagnose clutter through density, overlap, or contrast; diagnose weak structure through field coherence, focal distribution, or repetition. Change the mechanism that caused the issue and render again.

Verify seed replay, changed-parameter effect, reset, exported recipe, and actual visual output. Hand off the HTML/source, displayed preview, precise recipe, fidelity limits, and next decision according to the method contract.
