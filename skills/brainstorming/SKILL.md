---
name: brainstorming
description: Use when a feature or behavior change needs requirements clarification, design choices, or an implementation plan. Shared model index is provided by the model-policy skill.
---

# Design and Implementation Planning

## Model adaptation

Load `model-policy` once from its exact host catalog location and apply its repository scope and model guidance. Without a catalog entry, filesystem hosts may use [the sibling policy](../model-policy/SKILL.md) relative to this skill's resolved location, never the working directory. If unavailable, report that limitation and use bounded steps with observable checks; do not invent a model tier.

Check the conversation for existing goals, constraints and authorization. An explicit request to implement a change and open a PR already authorizes routine implementation choices. Ask only about consequential ambiguity, material scope/cost changes, or actions outside that authorization. A short design is enough for a small change.

1. Read relevant files, documentation and recent changes. Split multi-component work into coherent subprojects when that improves clarity.
2. Identify missing context that would change the approach. Ask focused questions about goals, constraints or acceptance criteria; continue independent work.
3. For a meaningful design choice, compare 2–3 feasible approaches and their tradeoffs. State the recommendation and its reason first.
4. Describe necessary interfaces, data flow, failure behavior and acceptance checks. Clarify unresolved consequential decisions without adding routine approval rounds.
5. Keep the design in the conversation or host plan by default. Save a repository document only when the user requests it or repository policy requires it; use the existing owner and format. See [documentation ownership](../model-policy/references/docs-and-static-checks.md#documentation-ownership) when a lasting record is required.
6. Self-review for placeholders, contradictions and an oversized scope. Record low-risk assumptions; clarify major ambiguity instead of presenting it as a user requirement.
7. For multi-step implementation, outline affected files and responsibilities, ordered tasks, dependencies, observable acceptance criteria, and runnable checks with working directories. Distinguish source-only checks from checks requiring generated contracts or build artifacts. A short checklist is enough for a small change; do not paste complete implementations or invent paths or line numbers.
8. Check that every requirement has an owning task and acceptance check, then proceed under existing authorization. Preserve any review gate explicitly requested.

Keep responsibilities focused, interfaces clear and components independently testable. Follow existing conventions and omit features that do not serve the current goal.
