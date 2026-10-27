# Decision: Direct guidance for Art Creation

Status: implemented — creative instructions focus on construction, comparison, and feedback.

## Problem

The [Art Creation bundle](../../../../../../skills/art-creation/SKILL.md) repeated approval language, evidence disclaimers, warnings about overclaiming, and prohibitions across the entrypoint, workflow, methods, references, and helper descriptions. These repetitions occupied the same context needed for creative exploration.

## Decision

The bundle uses concise descriptions of techniques, selection criteria, tool operations, and outputs. Redundant defensive clauses and the repeated execution checklist are removed. The shared [method contract](../../../../../../skills/art-creation/references/method-contract.md) describes the handoff; individual methods contain construction and refinement guidance. The two-chapter analysis format, progressive resource indexes, technical API requirements, licenses, and executable validation behavior remain part of the bundle.

Helper descriptions and the portable scene caption use direct descriptions of their output. The [source lock](../../../../../../skills/art-creation/upstream-lock.json) records the current hashes of adapted upstream files.

## Alternatives considered

- Replacing every prohibition with an equivalent positive instruction would retain the repeated rules and context cost. The edit removes redundant requirements and keeps useful procedures.
- A shared disclaimer page would relocate the same material. The bundle instead relies on host instructions for general agent conduct.
- Removing technical constraints and runtime error handling would change helper behavior beyond a prose review. Concrete API requirements and executable checks stay with their implementation.

## Consequences

Entry and method guidance are shorter, with more room for task-specific interpretation. The [resource checker](../../../../../../skills/art-creation/scripts/check_index.py), skill frontmatter validation, English-resource checks, and existing helper tests cover packaging and executable consistency. Frozen benchmark inputs and historical results keep their original skill snapshots; this edit is a new candidate for a future comparison.
