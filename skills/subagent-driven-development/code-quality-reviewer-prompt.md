# Code Quality Reviewer Prompt Template

Verify the implementation is well-built. **Dispatch only after spec compliance passes.**

```
Task tool (general-purpose):
  Use the template at ./code-reviewer.md with:

  DESCRIPTION: [task summary, from implementer's report]
  PLAN_OR_REQUIREMENTS: [inline task requirements or an existing plan reference]
  BASE_SHA: [recorded task baseline or merge-base]
  HEAD_SHA: [current commit, plus staged/unstaged and relevant new files]

  MODEL_POLICY: [host-confirmed model/config, review task domain, profile and applicable supplements; unknown identity stays unassessed]
```

In addition to the standard checks, the reviewer should verify:
- Each file has one clear responsibility with a well-defined interface
- The implementation follows the file structure from the plan
- Added files and structure serve the requested behavior and existing conventions; file size alone does not justify splitting, new scaffolding, or cleanup outside scope
