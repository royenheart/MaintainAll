# Code Quality Reviewer Prompt Template

Verify the implementation is well-built. **Dispatch only after spec compliance passes.**

```
Task tool (general-purpose):
  Use the template at ./code-reviewer.md with:

  DESCRIPTION: [task summary, from implementer's report]
  PLAN_OR_REQUIREMENTS: Task N from [plan-file]
  BASE_SHA: [commit before task]
  HEAD_SHA: [current commit]
```

In addition to the standard checks, the reviewer should verify:
- Each file has one clear responsibility with a well-defined interface
- The implementation follows the file structure from the plan
- This change didn't create large new files or significantly grow existing ones
  (don't flag pre-existing file sizes — only what this change contributed)
