# Decision records

Historical design decisions for MaintainAll. They explain why a choice was made and what was traded away. They are not current operating instructions; the code, `docs/`, and `.agents/skills/maintainall/SKILL.md` are the source of truth for current behavior.

## Layout

- `{lifecycle}/{class}/yyyy-mm-dd-title.md`
- Lifecycle: `proposed/`, `implemented/`, `rejected/`.
- Class: `architecture`, `feature`, `simplification`, `process`, `testing`, `bug-fix`.

Read only the category relevant to the current task. Do not load the whole tree.

## Writing

Routine repository knowledge belongs in `.agents/skills/maintainall/SKILL.md` or its focused references. Add a decision record only when a choice is substantial, non-obvious, and likely to be revisited by a future maintainer. Record the problem, decision, alternatives, and consequences; do not turn a release note into a decision record.
