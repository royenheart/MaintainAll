---
name: writing-plans
description: Use when a multi-step change needs ordered implementation tasks, dependencies, acceptance criteria, and verification commands. Model policy index - model-policy/registry.json.
---

# Writing Plans

## Model adaptation

Load the sibling [model-policy](../model-policy/SKILL.md) once and resolve this skill's entry. Apply its profile and applicable supplements. If unavailable, use small explicit steps and evidence-based verification; do not guess model identity or change permissions.

Write implementation plans assuming the engineer has **zero context** for the codebase: affected files, contracts, dependencies, acceptance criteria, and runnable checks with working directories. Keep detail proportional; do not duplicate complete implementations or invent line numbers.

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

Each task lists files, dependencies, acceptance criteria and appropriate checks. The example below is for executable behavior that warrants TDD; documentation/configuration tasks can use validation or a dry run. Choose useful commit boundaries rather than committing each small step.

````markdown
### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py` (name the affected component)
- Test: `tests/exact/path/to/test.py`

- [ ] **Step 1: Write the failing test**

```python
def test_specific_behavior():
    assert function(input) == expected
```

- [ ] **Step 2: Run test, verify it fails**

Run: `pytest tests/path/test.py::test_specific_behavior -v`
Expected: FAIL ("function not defined")

- [ ] **Step 3: Minimal implementation** (describe the required behavior and contracts)

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
- "Write tests for the above" (without observable acceptance criteria or runnable checks)
- "Similar to Task N" without specifying the contract or dependency
- References to types/functions not defined in any task

## Self-review (inline, fix and move on)

1. **Spec coverage:** every spec requirement points to a task? Add missing tasks.
2. **Placeholder scan:** any patterns from above? Fix.
3. **Type consistency:** names/signatures in later tasks match earlier definitions?

## Execution handoff

Execute when already authorized. Resolve task-domain profiles via model-policy. Delegate only when useful and supported; otherwise work sequentially. Preserve research-only scope and the requested branch/PR delivery.
