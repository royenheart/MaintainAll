---
name: verification-before-completion
description: Use when about to claim work is complete, fixed, or passing, before committing or creating PRs - requires running verification commands and confirming output before making any success claims; evidence before assertions always
---

# Verification Before Completion

## The Iron Law

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

If you haven't run the verification command in this message, you cannot claim it passes. Claiming completion without verification is dishonesty, not efficiency.

## The Gate

Before ANY success claim, expression of satisfaction, commit, or PR:

1. **IDENTIFY** the command that proves the claim
2. **RUN** it — full, fresh, complete
3. **READ** the output: exit code, failure counts
4. Output confirms the claim? → state the claim WITH evidence. Doesn't? → state the actual status.

## What each claim requires

| Claim | Requires | NOT sufficient |
|-------|----------|----------------|
| Tests pass | Test run output: 0 failures | Previous run, "should pass" |
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

Run the command. Read the output. THEN claim the result.
