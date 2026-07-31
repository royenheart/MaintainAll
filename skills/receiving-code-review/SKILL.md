---
name: receiving-code-review
description: Use when receiving code review feedback, before implementing suggestions, especially if feedback seems unclear or technically questionable - requires technical rigor and verification, not performative agreement or blind implementation
---

# Receiving Code Review

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

If ANY item in multi-item feedback is unclear, STOP and clarify before implementing anything. Items may be related; partial understanding = wrong implementation.

> "I understand items 1,2,3,6. Need clarification on 4 and 5 before proceeding."

## External reviewers (not your human partner)

Before implementing their suggestion, check: correct for this codebase? Breaks existing functionality? Works on all platforms? Does the reviewer have full context? Conflicts with your human partner's prior decisions → discuss first.

**YAGNI check** for "implement this properly" suggestions: grep for actual usage. Unused → propose removing the endpoint instead.

## Implementation order for multi-item feedback

1. Clarify everything unclear first
2. Blocking issues (breaks, security) → simple fixes → complex fixes
3. Test each fix individually; verify no regressions

## Push back when

The suggestion breaks functionality, violates YAGNI, is technically wrong for this stack, or the reviewer lacks context. Use technical reasoning, reference working tests/code, involve your human partner on architectural questions.

**If your pushback was wrong:** state the correction factually ("I checked X — it does Y. Implementing now.") and move on. No long apologies.

## GitHub

Reply to inline review comments in their thread (`gh api repos/{owner}/{repo}/pulls/{pr}/comments/{id}/replies`), not as top-level PR comments.
