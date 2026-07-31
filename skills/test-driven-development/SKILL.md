---
name: test-driven-development
description: Use when implementing any feature or bugfix, before writing implementation code
---

# Test-Driven Development

## The Iron Law

```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

Write code before the test? **Delete it. Start over.** Don't keep it as "reference", don't "adapt" it while writing tests. Delete means delete.

If you didn't watch the test fail, you don't know it tests the right thing.

## The Cycle

1. **RED** — one minimal test: one behavior, a name that describes the behavior, real code (mocks only when unavoidable).
2. **Verify RED** — run it. Confirm it *fails* (not errors), for the expected reason (feature missing, not a typo). Passes immediately → you're testing existing behavior; fix the test.
3. **GREEN** — the simplest code that passes. No extra features, no "improvements" beyond the test (YAGNI).
4. **Verify GREEN** — run it. Test passes, other tests still pass, no new warnings. Test fails → fix the code, not the test.
5. **REFACTOR** — only while green: remove duplication, improve names. No new behavior.
6. Repeat for the next behavior.

## Why order matters

Tests written after code pass immediately, which proves nothing — you test what you built, not what's required, and you never saw the test catch the bug. Tests-first forces edge-case discovery before implementation.

## Bug fixes

Bug found → write a failing test that reproduces it → fix → verify. Never fix bugs without a test; the test proves the fix and prevents regression.

## Red flags — delete the code and start over with TDD

- Code before test, or tests added "later"
- Test passes on the first run
- "I already manually tested it" (ad-hoc ≠ systematic, can't re-run)
- "Too simple to test" / "just this once" / "keep it as reference"

## When stuck

| Problem | Solution |
|---------|----------|
| Don't know how to test | Write the wished-for API; write the assertion first; ask |
| Test too complicated | Design too complicated — simplify the interface |
| Must mock everything | Code too coupled — use dependency injection |
| Huge test setup | Extract helpers; still complex → simplify design |

## Exceptions

Throwaway prototypes, generated code, config files — **ask your human partner first**. "Skip TDD just this once" is rationalization.

## Checklist before claiming done

- [ ] Every new function has a test
- [ ] Watched each test fail before implementing, for the expected reason
- [ ] Minimal code per test; all tests pass; output clean
- [ ] Edge cases and error paths covered
