---
name: test-driven-development
description: Use when changing executable behavior or fixing a bug that benefits from a reproducible regression test. Shared model index is provided by the model-policy skill.
---

# Test-Driven Development

## Model adaptation

Load `model-policy` once from its exact host catalog location and apply its repository scope and model guidance. Without a catalog entry, filesystem hosts may use [the sibling policy](../model-policy/SKILL.md) relative to this skill's resolved location, never the working directory. If unavailable, report that limitation and use bounded steps with observable checks; do not invent a model tier.

## The Iron Law

```
FOR NONTRIVIAL EXECUTABLE CHANGES, ESTABLISH A FAILING BEHAVIOR TEST FIRST
```

Preserve existing and user-written code. If implementation already exists, demonstrate regression-test sensitivity using an isolated baseline or a reversible fault, then restore. Never delete work merely to enforce chronology.

Use the existing test framework and file conventions. Test-first work does not justify a new test directory, dependency, runner, configuration, or repository scaffold unless the requested behavior needs it. Keep disposable reproductions outside the checkout, or in an existing task-appropriate scratch location, and remove temporary faults and instrumentation before delivery.

If you didn't watch the test fail, you don't know it tests the right thing.

## The Cycle

1. **RED** — one minimal test: one behavior, a name that describes the behavior, real code (mocks only when unavoidable).
2. **Verify RED** — run it. Confirm it *fails* (not errors), for the expected reason (feature missing, not a typo). Passes immediately → you're testing existing behavior; fix the test.
3. **GREEN** — the simplest code that passes. No extra features, no "improvements" beyond the test (YAGNI).
4. **Verify GREEN** — run it. Test passes, other tests still pass, no new warnings. Test fails → fix the code, not the test.
5. **REFACTOR** — only while green: remove duplication, improve names. No new behavior.
6. Repeat for the next behavior.

## Why order matters

Tests-first helps expose missing behavior. A later regression test is still useful if it fails against the unfixed behavior. Test observable contracts and failure paths, not incidental implementation details.

## Bug fixes

Bug found → write a failing test that reproduces it → fix → verify. Never fix bugs without a test; the test proves the fix and prevents regression.

## Red flags — check test sensitivity and coverage

- A test that never demonstrates sensitivity to the missing/broken behavior
- A passing test that only mirrors the implementation
- "I already manually tested it" (ad-hoc ≠ systematic, can't re-run)
- Skipping relevant checks without considering actual risk

## When stuck

| Problem | Solution |
|---------|----------|
| Don't know how to test | Write the wished-for API; write the assertion first; ask |
| Test too complicated | Design too complicated — simplify the interface |
| Must mock everything | Code too coupled — use dependency injection |
| Huge test setup | Extract helpers; still complex → simplify design |

## Exceptions

Use risk-appropriate validation for documentation, generated code, formatting, and trivial configuration: schema checks, rendering, linting or dry runs may be sufficient. Honor required repository gates and existing user authorization; do not add ritual approval requests.

## Checklist before claiming done

- [ ] Meaningful changed behaviors and relevant failure paths have coverage
- [ ] Demonstrated regression/acceptance test sensitivity for the expected reason
- [ ] Minimal code per test; all tests pass; output clean
- [ ] Edge cases and error paths covered
