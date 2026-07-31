---
name: subagent-driven-development
description: Use when executing implementation plans with independent tasks in the current session
---

# Subagent-Driven Development

Execute the plan by dispatching a **fresh subagent per task**, with two-stage review after each: **spec compliance first, then code quality**. Subagents get precisely crafted context — never your session history — which keeps them focused and preserves your context for coordination.

**Continuous execution:** do not pause to check in between tasks. Stop only for: an unresolvable BLOCKED, genuine ambiguity, or all tasks complete.

## Per task

1. **Dispatch implementer** with `./implementer-prompt.md` — paste the FULL task text plus scene-setting context. Never make the subagent read the plan file.
2. Answer its questions before letting it proceed.
3. Implementer reports a status (see below).
4. **Dispatch spec reviewer** with `./spec-reviewer-prompt.md`. Issues → implementer fixes → re-review. Only when spec is ✅:
5. **Dispatch code quality reviewer** with `./code-quality-reviewer-prompt.md` (needs BASE_SHA/HEAD_SHA). Issues → implementer fixes → re-review.
6. Mark task complete. Next task.

After all tasks: dispatch a final reviewer for the whole implementation, then use branch-lifecycle.

## Ad-hoc review (no plan workflow)

Not running a plan? A review is still valuable before merge, after a major feature, or when stuck. Get the range (`BASE_SHA=$(git rev-parse HEAD~1)`, `HEAD_SHA=$(git rev-parse HEAD)`), dispatch a reviewer with `./code-reviewer.md`, fill `{DESCRIPTION}` / `{PLAN_OR_REQUIREMENTS}` / SHAs. Fix Critical immediately, Important before proceeding, push back with technical reasoning if the reviewer is wrong.

## Parallel investigations

Multiple INDEPENDENT failures (different test files/subsystems) → dispatch one investigation agent per domain in parallel, each self-contained (paste the error messages and context). Do NOT parallelize implementers — they edit the same tree and conflict. After parallel agents return: check for overlapping edits, then run the full suite.

## Implementer status handling

- **DONE** → proceed to spec review.
- **DONE_WITH_CONCERNS** → read the concerns; correctness/scope doubts → address before review; observations → note and proceed.
- **NEEDS_CONTEXT** → provide the missing context, re-dispatch.
- **BLOCKED** → context problem: more context, same model. Reasoning problem: more capable model. Task too large: split it. Plan wrong: escalate to the human.

Never ignore an escalation or make the same model retry without changing something.

## Model selection

Use the least powerful model that fits: 1-2 files + complete spec → cheap/fast model; multi-file integration → standard; architecture/judgment/review → most capable.

## Red flags

- Implementing on main/master without explicit consent
- Skipping either review, or starting quality review before spec ✅
- Moving to the next task with open review issues
- Dispatching multiple implementers in parallel (they conflict)
- Making the subagent read the plan file instead of pasting the task text
- Letting the implementer's self-review replace the two real reviews
