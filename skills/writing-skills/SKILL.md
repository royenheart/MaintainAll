---
name: writing-skills
description: Use when creating, editing, evaluating, or packaging reusable agent skills. Shared model index is provided by the model-policy skill.
---

# Writing Skills

## Model adaptation

Load the skill named `model-policy` using its exact location and reader from the host skill catalog. The catalog location takes precedence over directory names. For a filesystem installation without a catalog entry, try [the sibling policy](../model-policy/SKILL.md), relative to the resolved location of this `SKILL.md`, never the working directory. Do not guess filesystem paths for opaque resource URIs. Resolve this skill by its frontmatter name and apply the returned profile and applicable supplements once. If the policy or registry cannot be read, report that adaptation is unavailable, use bounded steps and observable checks, and continue authorized work without inventing a model tier.

A **skill** is a reusable reference guide for a proven technique, pattern, or tool — not a narrative of how you solved a problem once.

**Don't create skills for:** one-off solutions, standard practices documented elsewhere, project-specific conventions (put those in CLAUDE.md/AGENTS.md), or mechanically enforceable constraints (automate those instead).

## Structure

```
skills/
  skill-name/
    SKILL.md          # required
    supporting-file   # only for heavy reference (100+ lines) or reusable tools
```

Flat namespace. Keep principles, concepts, and short code patterns inline.

## Frontmatter

- `name`: letters, numbers, hyphens only
- `description`: clear task/trigger conditions, plus the shared model-policy index pointer; keep a single line for this repository's loader

**Never summarize the skill's workflow in the description.** Agents read the description to decide whether to load the skill; if it summarizes the process, they follow the description instead of the skill body (a description saying "code review between tasks" produced ONE review when the skill required TWO). Describe the problem and symptoms, not the process:

```yaml
# ❌ Use for TDD - write test first, watch it fail, write minimal code
# ✅ Use when implementing any feature or bugfix, before writing implementation code
```

Include searchable keywords: error messages, symptoms, synonyms, tool names.

## Token efficiency

Skill metadata is indexed; bodies load on demand in supporting hosts — every token counts. Frequently-loaded: <200 words; others: <500. Move flag-level detail to `--help`, cross-reference other skills by name instead of repeating their content, one excellent example instead of many.

Use explicit skill names and relative resource links; do not assume every host implements @ links the same way. Package dependencies together.

## Test before deploying (TDD for documentation)

Writing skills IS TDD applied to process docs:

1. **RED (baseline):** run the scenario with a subagent WITHOUT the skill. Note what it does wrong and any rationalizations verbatim.
2. **GREEN:** write the skill addressing those specific failures. Re-run the scenario WITH the skill — the agent should now comply.
3. **REFACTOR:** new rationalization found → add an explicit counter (rationalization table, red-flags list) and re-verify.

For discipline-enforcing skills, apply pressure (time, sunk cost, exhaustion) in test scenarios. Include negative triggers, unknown models, missing tools and already-authorized work. If only static checks were possible, state that limitation; do not claim empirical model improvements.

## Central model policy

Maintain model IDs, effort variants, evidence, tiers, task mappings and supplements only in the `registry.json` resource of the catalog-resolved model-policy skill. In this repository its source path is `skills/model-policy/registry.json`; installed paths may differ. Update its skill entry when adding a development skill. Validate registry references and helper behavior. Package the policy resources and supporting skills, then run the installation check on the destination; do not silently mutate user-installed settings.

## Anti-patterns

- Narrative examples ("in session 2025-10-03 we found...") — too specific, not reusable
- The same example in 5 languages — one great example is enough
- Flowcharts for reference material or linear steps — use tables/lists; flowcharts only for non-obvious decisions
