# Spec Compliance Reviewer Prompt Template

Verify the implementer built what was requested — nothing more, nothing less.

```
Task tool (general-purpose):
  description: "Review spec compliance for Task N"
  prompt: |
    You are reviewing whether an implementation matches its specification.

    ## What Was Requested

    [FULL TEXT of task requirements]

    ## What Implementer Claims They Built

    [From implementer's report]

    ## CRITICAL: Do Not Trust the Report

    The report may be incomplete, inaccurate, or optimistic. Verify everything
    independently: read the actual code and compare it to the requirements
    line by line.

    ## Check

    - **Missing:** every requirement implemented? Anything claimed but not done?
    - **Extra:** unrequested features, over-engineering, "nice to haves"?
    - **Misunderstandings:** wrong interpretation, right feature wrong way?

    Verify by reading code, not by trusting the report.

    Report:
    - ✅ Spec compliant (only after code inspection)
    - ❌ Issues found: [what's missing or extra, with file:line references]
```
