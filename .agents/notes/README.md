# Agent Notes

One kind of design doc lives here: an **Agent Note** records a decision or proposal that affects this codebase — the why and what was given up. The format mirrors `deepseek-harness/.agents/notes/README.md`, simplified for this plugin.

## Layout and naming

- Path: `{lifecycle}/{class}/yyyy-mm-dd-title.md`
- Lifecycle: `proposed/` (reviewed before implementation), `implemented/` (shipped, present tense), `rejected/` (declined, kept only while it prevents a mistake).
- Class: `architecture`, `feature`, `simplification`, `process`, `testing`, `bug-fix`.

## Format

Every active Agent Note starts:

```markdown
# Agent Note: <title>

Status: proposed | implemented | rejected — <one-line reason>
```

`proposed/` body: `## Problem`, `## Proposal`, `## Alternatives considered`, `## Acceptance criteria`, `## Risks`.
`implemented/` body: `## Problem`, `## Decision`, `## Alternatives considered`, `## Consequences`.
`rejected/` keeps the proposal and adds the rejection reason on the `Status:` line.

`## Alternatives considered` is mandatory: each genuine alternative and why it lost.

## When to write one

Every non-trivial change adds or updates at least one Agent Note in the same change. Non-trivial means behavior, architecture, contract, storage/wire format, testing strategy, or a decision a maintainer may revisit.
