---
name: brainstorming
description: Use when a feature or behavior change needs design decisions, requirements clarification, or comparison of approaches. Shared model index is provided by the model-policy skill.
---

# Brainstorming Ideas Into Designs

## Model adaptation

Load the skill named `model-policy` using its exact location and reader from the host skill catalog. The catalog location takes precedence over directory names. For a filesystem installation without a catalog entry, try [the sibling policy](../model-policy/SKILL.md), relative to the resolved location of this `SKILL.md`, never the working directory. Do not guess filesystem paths for opaque resource URIs. Resolve this skill by its frontmatter name and apply the returned profile and applicable supplements once. If the policy or registry cannot be read, report that adaptation is unavailable, use bounded steps and observable checks, and continue authorized work without inventing a model tier.

Check the conversation for existing goals, constraints and authorization. An explicit
request to implement a change and open a PR already authorizes routine implementation
choices. Ask only about consequential ambiguity, material scope/cost changes, or actions
outside that authorization. A short design is enough for a small change.

1. Read relevant files, documentation and recent changes. Split multi-component work
   into coherent subprojects when that improves clarity.
2. Identify missing context that would change the approach. Ask focused questions about
   goals, constraints or acceptance criteria; continue independent work.
3. For a meaningful design choice, compare 2–3 feasible approaches and their tradeoffs.
   State the recommendation and its reason first.
4. Describe necessary interfaces, data flow, failure behavior and acceptance checks.
   Clarify unresolved consequential decisions without adding routine approval rounds.
5. When a lasting record is useful or requested, save the design under
   `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`, honoring user preferences.
6. Self-review for placeholders, contradictions and an oversized scope. Record low-risk
   assumptions; clarify major ambiguity instead of presenting it as a user requirement.
7. Proceed under existing authorization. Use writing-plans for complex implementation;
   implement a simple change directly. Preserve any review gate explicitly requested.

Keep responsibilities focused, interfaces clear and components independently testable.
Follow existing conventions and omit features that do not serve the current goal.
