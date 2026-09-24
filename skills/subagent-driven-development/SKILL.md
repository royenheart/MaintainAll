---
name: subagent-driven-development
description: Use when an implementation plan benefits from independent task execution or review and the host supports delegation. Shared model index is provided by the model-policy skill.
---

# Subagent-Driven Development

## Model adaptation

Load the skill named `model-policy` using its exact location and reader from the host skill catalog. The catalog location takes precedence over directory names. For a filesystem installation without a catalog entry, try [the sibling policy](../model-policy/SKILL.md), relative to the resolved location of this `SKILL.md`, never the working directory. Do not guess filesystem paths for opaque resource URIs. Resolve this skill by its frontmatter name and apply the returned profile and applicable supplements once. If the policy or registry cannot be read, report that adaptation is unavailable, use bounded steps and observable checks, and continue authorized work without inventing a model tier.

When delegation is useful and supported, give each subagent a bounded task and relevant artifacts. Review specification compliance before code quality. If unavailable, execute and review sequentially; disclose self-review. Tiny reversible edits do not require ceremonial multiple reviews.

**Continuous execution:** do not pause to check in between tasks. Stop only for: an unresolvable BLOCKED, genuine ambiguity, or all tasks complete.

## Per task

The following sequence applies when independent delegation/review is available and
warranted by the task. Otherwise perform these checks sequentially and label self-review.

1. **Dispatch implementer** with `./implementer-prompt.md` — paste the FULL task text plus scene-setting context. Never make the subagent read the plan file.
2. Answer its questions before letting it proceed.
3. Implementer reports a status (see below).
4. **Dispatch spec reviewer** with `./spec-reviewer-prompt.md`. Issues → implementer fixes → re-review. Only when spec is ✅:
5. **Dispatch code quality reviewer** with `./code-quality-reviewer-prompt.md` (needs BASE_SHA/HEAD_SHA). Issues → implementer fixes → re-review.
6. Mark task complete. Next task.

After all tasks: inspect the combined diff and run integration checks; use independent review when risk warrants it, then honor the user's delivery request via branch-lifecycle.

## Ad-hoc review (no plan workflow)

Not running a plan? A review is still valuable before merge, after a major feature, or when stuck. Use the recorded task baseline, or the merge-base with the intended target branch, through the current HEAD; do not assume HEAD~1 covers a whole feature. Include staged, unstaged and relevant new files when work is not committed. Dispatch a reviewer with `./code-reviewer.md`, filling requirements and the exact review scope. Fix Critical immediately, Important before proceeding, and push back with evidence if the finding is wrong.

## Parallel investigations

Multiple INDEPENDENT failures (different test files/subsystems) → dispatch one investigation agent per domain in parallel, each self-contained (paste the error messages and context). Parallel implementers require disjoint write ownership and independent contracts; sequence shared-file tasks. After parallel agents return: check for overlapping edits, then run the full suite.

## Implementer status handling

- **DONE** → proceed to spec review.
- **DONE_WITH_CONCERNS** → read the concerns; correctness/scope doubts → address before review; observations → note and proceed.
- **NEEDS_CONTEXT** → provide the missing context, re-dispatch.
- **BLOCKED** → context problem: more context, same model. Reasoning problem: more capable model. Task too large: split it. Plan wrong: escalate to the human.

Never ignore an escalation or make the same model retry without changing something.

## Model selection

Resolve implementer and reviewer separately through model-policy using the actual model/config and task domain. Prefer the least costly option that meets evidence-backed requirements. File count, brand and parameter size alone do not establish capability. Never claim a switch if the host cannot perform it.

## Red flags

- Implementing on main/master without explicit consent
- Omitting applicable specification/quality checks, or reviewing quality before requirements
- Moving to the next task with open review issues
- Dispatching writers with overlapping ownership or dependent contracts
- Making the subagent read the plan file instead of pasting the task text
- Claiming independent review when only self-review occurred
