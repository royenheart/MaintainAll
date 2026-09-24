---
name: receiving-code-review
description: Use when assessing or implementing review feedback, especially disputed findings, unclear requests, or possible regressions. Model policy index - model-policy/registry.json.
---

# Receiving Code Review

## Model adaptation

Load the sibling [model-policy](../model-policy/SKILL.md) once and resolve this skill's entry. Apply its profile and applicable supplements. If unavailable, use small explicit steps and evidence-based verification; do not guess model identity or change permissions.

Verify before implementing. Ask before assuming. Technical correctness over social comfort.

## The pattern

1. **READ** all feedback without reacting
2. **UNDERSTAND** — restate the requirement in your own words, or ask
3. **VERIFY** against the codebase
4. **EVALUATE** — technically sound for THIS codebase?
5. **RESPOND** — technical acknowledgment or reasoned pushback
6. **IMPLEMENT** one item at a time, testing each

## Forbidden responses

Never: "You're absolutely right!" / "Great point!" / "Thanks for catching that!" / "Let me implement that now" (before verification).

Instead: restate the requirement, ask a clarifying question, push back with reasoning — or just fix it and let the code speak. If you catch yourself writing "Thanks", delete it and state the fix.

## Unclear feedback — clarify FIRST

Clarify ambiguous items and pause only work that depends on them. Continue independent, confirmed fixes. Track each finding's evidence, dependencies and disposition.

> "I understand items 1,2,3,6. Need clarification on 4 and 5 before proceeding."

## External reviewers (not your human partner)

Before implementing their suggestion, check: correct for this codebase? Breaks existing functionality? Works on all platforms? Does the reviewer have full context? Conflicts with your human partner's prior decisions → discuss first.

**YAGNI check** for "implement this properly" suggestions: grep for actual usage. Check public contracts, dynamic callers and compatibility before proposing removal.

## Implementation order for multi-item feedback

1. Clarify blocking dependencies; continue independent confirmed fixes
2. Blocking issues (breaks, security) → simple fixes → complex fixes
3. Test each fix individually; verify no regressions

## Push back when

The suggestion breaks functionality, violates YAGNI, is technically wrong for this stack, or the reviewer lacks context. Use technical reasoning, reference working tests/code, involve your human partner on architectural questions.

**If your pushback was wrong:** state the correction factually ("I checked X — it does Y. Implementing now.") and move on. No long apologies.

## GitHub

Only when the user authorized posting, reply to inline review comments in their thread (`gh api repos/{owner}/{repo}/pulls/{pr}/comments/{id}/replies`), not as top-level PR comments.
