---
name: subagent-driven-development
description: Use when the user requests subagents or an implementation benefits from delegated execution or review. Shared model index is provided by the model-policy skill.
---

# Subagent-Driven Development

## Model adaptation

Load `model-policy` once from its exact host catalog location and apply its repository scope and model guidance. Without a catalog entry, filesystem hosts may use [the sibling policy](../model-policy/SKILL.md) relative to this skill's resolved location, never the working directory. If unavailable, report that limitation and use bounded steps with observable checks; do not invent a model tier.

Useful delegation opportunities include independent investigations, bounded implementation tasks with disjoint ownership, and a fresh review of completed work. Sequence dependent or shared-file tasks.

## Task handoff

Give each worker the task requirements, relevant context, owned files, dependencies, acceptance checks, and the user's delivery scope. Inline requirements and uncommitted diffs are sufficient. Keep reports in messages; do not require plan files, worktrees, or per-task commits.

Use [the implementer prompt](implementer-prompt.md) when useful. Workers preserve others' edits; parallel writes require disjoint ownership and independent contracts. Sequence shared-file or dependent tasks. Independent investigations may run in parallel with their own evidence and bounded questions.

## Review and integration

Check [specification compliance](spec-reviewer-prompt.md) before [code quality](code-quality-reviewer-prompt.md); one reviewer may cover both when appropriate. Reviewers inspect read-only and return concrete findings. Fix material issues and recheck affected behavior before proceeding.

For an ad-hoc review, use [the review prompt](code-reviewer.md). Include the task baseline or intended target's merge-base, staged/unstaged changes, and relevant new files; do not assume the last commit represents the task. Verify a worker's report against the actual diff and test evidence.

After all tasks, inspect the combined diff, resolve overlaps, and run relevant integration checks. Deliver within the user's requested scope.

## Uncertainty and model guidance

Workers report completion, concerns, missing context, or a blocker with evidence and the next useful action. Resolve missing context or split an oversized task before retrying. Continue independent authorized work while consequential questions remain open.

Use the host-supported model configuration for each role. Model-policy provides advisory guidance; model identity may remain unassessed.
