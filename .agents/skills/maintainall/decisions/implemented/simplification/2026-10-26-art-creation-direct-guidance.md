# Decision: Direct guidance for Art Creation

Status: implemented — creative instructions focus on construction, comparison, and feedback.

## Problem

The [Art Creation bundle](../../../../../../skills/art-creation/SKILL.md) repeated approval language, evidence disclaimers, warnings about overclaiming, and prohibitions across the entrypoint, workflow, methods, references, and helper descriptions. These repetitions occupied the same context needed for creative exploration.

## Decision

The bundle uses concise descriptions of techniques, selection criteria, tool operations, and outputs. Repeated prohibitions and the repeated execution checklist are removed. Three operative criteria were not redundant and remain: a preview is the rendered artifact rather than a path or source listing, the supplied material must be annotated rather than replaced by a reconstruction, and measured, estimated, proposed, and inferred claims must remain distinguishable. The shared [method contract](../../../../../../skills/art-creation/references/method-contract.md) describes the handoff; individual methods contain construction and refinement guidance. The two-chapter analysis format, progressive resource indexes, technical API requirements, licenses, and executable validation behavior remain part of the bundle.

Helper descriptions and the portable scene caption use direct descriptions of their output. The [source lock](../../../../../../skills/art-creation/upstream-lock.json) records the current hashes of adapted upstream files.

## Classification: repeated prohibitions vs. operative criteria

- **Repeated prohibitions:** duplicated approval, evidence, and overclaiming warnings across the entrypoint, methods, and references. These were consolidated; the repeated execution checklist was removed.
- **Operative criteria:** a preview must be visible as a rendered artifact, annotations must use the supplied material, and measurements, estimates, proposals, and inferred intent must stay distinguishable. These are acceptance checks, not duplicate warnings. Removing them changed behavior, so they are restored as short positive criteria.

## Alternatives considered

- Replacing every prohibition with an equivalent positive instruction would retain the repeated rules and context cost. The edit removes repeated prohibitions but keeps the minimal operative criteria above.
- A shared disclaimer page would relocate the same material. The bundle instead relies on host instructions for general agent conduct.
- Removing technical constraints and runtime error handling would change helper behavior beyond a prose review. Concrete API requirements and executable checks stay with their implementation.

## Consequences

Output now defaults to the language of the user's current input rather than a fixed language requirement. Entry and method guidance are shorter, with more room for task-specific interpretation. The [resource checker](../../../../../../skills/art-creation/scripts/check_index.py), skill frontmatter validation, English-resource checks, and existing helper tests cover packaging and executable consistency. Frozen benchmark inputs and historical results keep their original skill snapshots; this edit is a new candidate for a future comparison.
