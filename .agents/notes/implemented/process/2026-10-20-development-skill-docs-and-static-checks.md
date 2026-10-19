# Agent Note: Development skill documentation ownership and static checks

Status: implemented — development skills preserve task scope and repository ownership without prescribing workflow artifacts or persistent plans.

## Problem

Fixed skill-specific plan locations produce parallel documentation without a repository owner. Repeated procedural instructions also obscure which constraints can be checked mechanically.

## Decision

[Brainstorming](../../../../skills/brainstorming/SKILL.md) owns design choices and implementation planning, with task boundaries, dependencies, acceptance criteria, and runnable checks. Working designs and plans stay in conversation or host state by default. Repository persistence follows an explicit request or repository policy; existing records and formats take precedence.

The [shared model policy](../../../../skills/model-policy/SKILL.md#repository-scope) applies task scope to the development skills and their supporting prompts. Workflow examples do not authorize new project directories, reports, policy files, dependencies, configuration, branches, or commits. Scratch uses host state or external temporary storage by default. Git delivery follows host/user instructions, with full-diff and resource-ownership checks in the shared policy rather than a separate lifecycle skill. [Delegation prompts](../../../../skills/subagent-driven-development/SKILL.md) accept inline requirements and uncommitted diffs, [debugging](../../../../skills/systematic-debugging/SKILL.md) removes temporary diagnostics, and [plugin development](../../../../skills/dsh-plugin-development/SKILL.md) treats layout and live installation as task-dependent choices.

The shared policy owns final-artifact verification and the [documentation and static-check reference](../../../../skills/model-policy/references/docs-and-static-checks.md). Its evidence supplement supplies verification guidance to every execution profile. The reference distills documentation ownership, executable command inventories, source-based verification, declared build prerequisites, bounded scheduling, and honest failure reporting from the inspected DeepSeek Harness checkout. Repository-specific directory trees, templates, translation rules, budgets, and mandatory records remain local policy.

[Writing skills](../../../../skills/writing-skills/SKILL.md) distinguishes structural validation from behavioral evaluation. Mechanical rules belong in reusable checks; small prose changes do not require an independent model evaluation or saved report.

Delegation guidance identifies concrete opportunities: independent investigations, bounded implementation with disjoint ownership, and a fresh review of completed work. It focuses on handoff and integration instead of repeating instruction precedence or imposing a task-size threshold. Host-supported model configuration and the shared policy supply model guidance.

Generic review etiquette, standalone plan/verification checklists, and CLI-help wrappers have no separate skill entry. The [repository tool index](../../../../README.md) points directly to the [modulefile CLI](../../../../scripts/modulefiles/manage_modules.py) and its help; the tool and templates remain available.

## Alternatives considered

- Keep a universal spec/plan directory: creates a competing documentation hierarchy and unnecessary files.
- Copy the complete harness documentation and gate inventory: imports project-specific obligations and duplicates executable configuration.
- Add a separate generic skill: adds discovery and packaging overhead for guidance already owned by the shared policy.
- Retain a dedicated Git lifecycle skill: duplicates host instructions and ordinary Git knowledge; the shared scope policy owns the few additional delivery checks.

## Consequences

The policy ships its reference directory under the [distribution contract](../../../../skills/model-policy/methodology.md#adaptation-and-distribution); the installation checker rejects a missing reference. Supporting-skill dependencies name only active entries. The [model-policy tests](../../../../tests/test_model_policy.py) cover those dependencies, relocated/renamed bundles, missing resources, and linked files throughout the development corpus. Static validation establishes structural consistency, not empirical improvement in agent behavior. Repository-required Agent Notes remain applicable.
