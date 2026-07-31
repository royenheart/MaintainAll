---
name: writing-plans
description: Use when you have a spec or requirements for a multi-step task, before touching code
---

# Writing Plans

Write implementation plans assuming the engineer has **zero context** for the codebase: exact files, complete code, exact commands, how to verify. Bite-sized tasks. DRY. YAGNI. TDD. Frequent commits.

**Save plans to:** `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md` (user preference overrides).

**Scope check:** if the spec covers multiple independent subsystems, write separate plans — each must produce working, testable software on its own.

## File structure first

Map out which files are created/modified and what each is responsible for — decomposition decisions lock in here. One clear responsibility per file; prefer smaller focused files; files that change together live together. In existing codebases follow established patterns.

## Plan header

```markdown
# [Feature Name] Implementation Plan

**Goal:** [One sentence]
**Architecture:** [2-3 sentences]
**Tech Stack:** [Key technologies]

---
```

## Task structure

Each task lists its files, then checkbox steps of one action each (2-5 minutes): write the failing test → run it, verify it fails → minimal implementation → run, verify pass → commit.

````markdown
### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Test: `tests/exact/path/to/test.py`

- [ ] **Step 1: Write the failing test**

```python
def test_specific_behavior():
    assert function(input) == expected
```

- [ ] **Step 2: Run test, verify it fails**

Run: `pytest tests/path/test.py::test_specific_behavior -v`
Expected: FAIL ("function not defined")

- [ ] **Step 3: Minimal implementation** (show the complete code)

- [ ] **Step 4: Run test, verify it passes** — Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/path/test.py src/path/file.py
git commit -m "feat: add specific feature"
```
````

## No placeholders

These are **plan failures** — never write them:
- "TBD", "TODO", "implement later"
- "Add appropriate error handling" / "handle edge cases" (show HOW)
- "Write tests for the above" (without the actual test code)
- "Similar to Task N" (repeat the code — tasks may be read out of order)
- References to types/functions not defined in any task

## Self-review (inline, fix and move on)

1. **Spec coverage:** every spec requirement points to a task? Add missing tasks.
2. **Placeholder scan:** any patterns from above? Fix.
3. **Type consistency:** names/signatures in later tasks match earlier definitions?

## Execution handoff

After saving the plan, execute with subagent-driven-development — fresh subagent per task, two-stage review between tasks.
