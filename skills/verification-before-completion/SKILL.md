---
name: verification-before-completion
description: Use before claiming work is complete, a bug is fixed, tests pass, or a change is ready for delivery. Model policy index - model-policy/registry.json.
---

# Verification Before Completion

## Model adaptation

Load the sibling [model-policy](../model-policy/SKILL.md) once and resolve this skill's entry. Apply its profile and applicable supplements. If unavailable, use small explicit steps and evidence-based verification; do not guess model identity or change permissions.

## The Iron Law

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

Use evidence from the final artifact in this task. Reuse checks only while the checked code and relevant environment are unchanged; rerun checks invalidated by edits. State command, scope and limits.

## The Gate

Before a completion or delivery claim:

1. **IDENTIFY** the command that proves the claim
2. **RUN** it — full, fresh, complete
3. **READ** the output: exit code, failure counts
4. Output confirms the claim? → state the claim WITH evidence. Doesn't? → state the actual status.

## What each claim requires

| Claim | Requires | NOT sufficient |
|-------|----------|----------------|
| Tests pass | Test run output: 0 failures | A run invalidated by later changes, "should pass" |
| Linter clean | Linter output: 0 errors | Partial check |
| Build succeeds | Build exit 0 | Linter passing |
| Bug fixed | Original symptom re-tested | "I changed the code" |
| Regression test works | Red-green verified: revert fix → test MUST FAIL → restore | Test passing once |
| Agent completed | VCS diff inspected | Agent's success report |
| Requirements met | Line-by-line checklist vs plan | Tests passing |

## Red flags — run the command instead

- "should", "probably", "seems to"
- "Great!" / "Done!" before verification
- Trusting a subagent's report without checking the diff
- Partial verification, "just this once", tired and wanting it over

Run the command. Read the output. THEN claim the result. Offline validation is not live-provider evaluation, and a targeted suite is not the full suite. Stop optional testing after material risks and required gates are covered.
