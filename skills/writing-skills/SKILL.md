---
name: writing-skills
description: Use when creating new skills, editing existing skills, or verifying skills work before deployment
---

# Writing Skills

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
- `description`: **third person, triggering conditions ONLY — start with "Use when..."**

**Never summarize the skill's workflow in the description.** Agents read the description to decide whether to load the skill; if it summarizes the process, they follow the description instead of the skill body (a description saying "code review between tasks" produced ONE review when the skill required TWO). Describe the problem and symptoms, not the process:

```yaml
# ❌ Use for TDD - write test first, watch it fail, write minimal code
# ✅ Use when implementing any feature or bugfix, before writing implementation code
```

Include searchable keywords: error messages, symptoms, synonyms, tool names.

## Token efficiency

Frequently-loaded skills load into every conversation — every token counts. Frequently-loaded: <200 words; others: <500. Move flag-level detail to `--help`, cross-reference other skills by name instead of repeating their content, one excellent example instead of many.

Cross-reference as `**REQUIRED SUB-SKILL:** Use <skill-name>` — never `@`-link skill files (force-loads them, burning context).

## Test before deploying (TDD for documentation)

Writing skills IS TDD applied to process docs:

1. **RED (baseline):** run the scenario with a subagent WITHOUT the skill. Note what it does wrong and any rationalizations verbatim.
2. **GREEN:** write the skill addressing those specific failures. Re-run the scenario WITH the skill — the agent should now comply.
3. **REFACTOR:** new rationalization found → add an explicit counter (rationalization table, red-flags list) and re-verify.

For discipline-enforcing skills, apply pressure (time, sunk cost, exhaustion) in test scenarios. Don't deploy untested skills — "obviously clear" to you ≠ clear to another agent.

## Anti-patterns

- Narrative examples ("in session 2025-10-03 we found...") — too specific, not reusable
- The same example in 5 languages — one great example is enough
- Flowcharts for reference material or linear steps — use tables/lists; flowcharts only for non-obvious decisions
