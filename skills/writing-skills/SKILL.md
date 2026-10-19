---
name: writing-skills
description: Use when creating, editing, evaluating, or packaging reusable agent skills. Shared model index is provided by the model-policy skill.
---

# Writing Skills

## Model adaptation

Load `model-policy` once from its exact host catalog location and apply its repository scope and model guidance. Without a catalog entry, filesystem hosts may use [the sibling policy](../model-policy/SKILL.md) relative to this skill's resolved location, never the working directory. If unavailable, report that limitation and use bounded steps with observable checks; do not invent a model tier.

Keep a skill only when it adds a reusable technique, tool procedure, or non-obvious decision rule. Retire skills that repeat host instructions, ordinary tool knowledge, or another skill. Put project conventions with their existing owner and mechanical constraints in checks when the task calls for them.

## Content and location

Use the user's destination or the host's skill installation location. Do not create a project skill tree or copy policy dependencies merely to consume a skill. A bundle needs `SKILL.md`; add references, scripts, or templates only when they materially help, and link resources where they become relevant.

Keep the entry short and actionable. Remove generic advice, repeated rules, incident narratives, and redundant examples. Preserve existing namespaces. Write natural paragraphs without fixed-width wrapping.

Frontmatter needs a lowercase hyphenated `name` and a concise `description` of when the skill applies. Describe task triggers rather than the workflow. Skills in this development collection retain the shared model-policy pointer; unrelated skills do not need that integration.

## Validation and distribution

Validate frontmatter, relative links/anchors, resource packaging, and changed executable helpers. Reuse existing validators and [static-check guidance](../model-policy/references/docs-and-static-checks.md). For substantial behavioral changes, use realistic comparison scenarios when authorized; structural checks alone do not establish model improvement.

Keep plans and results in conversation or host state unless the user or repository requires a file. When distribution is requested, copy complete selected bundles and their actual dependencies, check the destination, and preserve unrelated installed settings. Keep this collection's model mappings in the catalog-resolved policy registry; do not duplicate them in individual skills.
