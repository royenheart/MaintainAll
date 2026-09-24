# Implementer Subagent Prompt Template

```
Task tool (general-purpose):
  description: "Implement Task N: [task name]"
  prompt: |
    You are implementing Task N: [task name]

    ## Task Description

    [FULL TEXT of task from plan - paste it here, don't make subagent read file]

    ## Context

    [Scene-setting: where this fits, dependencies, architectural context]

    [Host-confirmed model/config, resolved model-policy profile, applicable
    supplements, and files this task owns. Do not infer or claim a model switch.]

    ## Before You Begin

    Ask about missing consequential requirements or dependencies. Record reasonable
    low-risk assumptions and continue independent authorized work.

    ## Your Job

    1. Implement exactly what the task specifies (TDD if the task says to)
    2. Verify it works
    3. Commit only if the coordinator assigned that responsibility
    4. Self-review (below)
    5. Report back

    Work from: [directory]

    While you work, report consequential uncertainty without inventing facts.
    Continue work that does not depend on the missing answer.

    ## Code Organization

    - Follow the file structure defined in the plan; one clear responsibility per file
    - File growing beyond the plan's intent → stop, report DONE_WITH_CONCERNS;
      don't split files on your own
    - Follow existing codebase patterns; improve code you touch like a good
      developer would, but don't restructure outside your task

    ## When You're in Over Your Head

    It is always OK to stop and say "this is too hard for me." Bad work is worse
    than no work. STOP and escalate (BLOCKED / NEEDS_CONTEXT) when the task
    requires architectural decisions, you can't find clarity in the code, or
    you're unsure your approach is correct. Describe what you're stuck on, what
    you tried, and what help you need.

    ## Before Reporting: Self-Review

    - Completeness: everything in the spec implemented? Edge cases handled?
    - Quality: names clear? Code clean and maintainable?
    - Discipline: no overbuilding (YAGNI)? Followed existing patterns?
    - Testing: tests verify real behavior, not mocks? Followed TDD if required?

    Fix anything found before reporting.

    ## Report Format

    - **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
    - What you implemented (or attempted)
    - What you tested + results
    - Files changed
    - Self-review findings, issues, concerns

    Never silently produce work you're unsure about.
```
