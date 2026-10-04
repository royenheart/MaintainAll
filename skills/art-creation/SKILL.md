---
name: art-creation
description: Use when analyzing visual references or helping a non-expert express and refine an artistic idea for painting, illustration, graphic design, web visuals, animation, or video. Applies to vague aesthetic requests, sketches, style breakdowns, and iterative creative direction; not ordinary software architecture or debugging.
---

# Art Creation

Turn references and rough ideas into observable design decisions, visible alternatives, and an executable creative brief. The user does not need specialist vocabulary.

## Capability index

| User need | Capability | Read |
|---|---|---|
| Understand a supplied image, webpage, or design; learn how to describe its style | Style analysis with direct annotation and a two-chapter teaching report | [Style analysis](references/style-analysis.md) |
| Start with a vague idea, sketch, or reference and discover the desired result through feedback | Progressive creative exploration with contrasting previews and controlled refinement | [Iterative creation](references/iterative-creation.md) |

Load only the relevant capability. When both are requested, use analysis to inform exploration. The exact two-chapter format applies to the full analysis report; ordinary exploration rounds stay compact. Do not impose a full report before every revision. Add future capabilities as separate linked references here.

## Shared rules

- Write reports and creative guidance in accessible Chinese unless the user requests another language. Explain a technical term on first use.
- Separate direct observations, measurements, interpretations, user-confirmed preferences, and implementation suggestions. Inferred intent is a hypothesis.
- Prefer natural language and inspectable programs for analysis and construction. Start from available text, source, geometry, pixel statistics, or timelines; use SVG, HTML/CSS, canvas, procedural models, or frame-based rendering when suitable. Use multimodal or world-model assistance only for an identified need that those methods cannot adequately resolve. Scope the fallback to that need and explain it.
- Actually render and display annotations and alternatives when the environment supports it. Code, file paths, and download links alone are not visual previews. Disclose a specific rendering/display limitation when it prevents this.
- Annotate the actual supplied material. Keep recreated alternatives visibly distinct from reference annotations; never substitute a generated lookalike.
- Preserve the requested medium, content, and confirmed constraints. A geometric sketch can test a painting's composition without becoming its final deliverable.
- Keep accepted decisions stable while varying unresolved ones. User feedback, rather than self-assessed beauty, determines whether the result matches intent.

For concrete inspection, overlay, rendering, and motion methods, read [Programmatic visual methods](references/visual-methods.md) when needed.

Progressive disclosure follows `Art Creation -> Iterative Creation -> chosen method SKILL.md -> its relevant reference or template`. The [method index](references/iterative-creation.md#detailed-description-and-construction-methods) selects concrete algorithmic, canvas, motion, variant, 3D, browser-3D, or video guidance. Load one construction method at a time; add a comparison method only when needed. Skill files and resources are included; renderer runtimes remain environment dependencies.

For research comparisons, read [Practice review](references/practice-review.md). For adopted source revisions, licenses, and local changes, read [Upstream sources](references/upstream-sources.md). Existing specialist tools can support a chosen method within the requested task's scope.
