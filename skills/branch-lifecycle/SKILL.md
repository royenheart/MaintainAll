---
name: branch-lifecycle
description: Use when isolating development in a branch/worktree or delivering, retaining, merging, or discarding completed changes. Shared model index is provided by the model-policy skill.
---

# Branch Lifecycle

## Model adaptation

Load the skill named `model-policy` using its exact location and reader from the host skill catalog. The catalog location takes precedence over directory names. For a filesystem installation without a catalog entry, try [the sibling policy](../model-policy/SKILL.md), relative to the resolved location of this `SKILL.md`, never the working directory. Do not guess filesystem paths for opaque resource URIs. Resolve this skill by its frontmatter name and apply the returned profile and applicable supplements once. If the policy or registry cannot be read, report that adaptation is unavailable, use bounded steps and observable checks, and continue authorized work without inventing a model tier.

Two phases: isolate the work, then deliver the requested result.

## Setup

1. Inspect `git status`, the current branch, remotes and repository instructions.
   Preserve user changes. Compare `git rev-parse --git-dir` with
   `git rev-parse --git-common-dir` to identify a linked worktree, after checking
   `git rev-parse --show-superproject-working-tree` for a submodule. Reuse existing
   task isolation; do not create nested worktrees.
2. Resolve the intended PR target from the existing PR, the user's instruction or
   the remote default, in that order unless the user explicitly retargets it. Record
   its remote, branch and commit SHA before creating task isolation; do not assume
   main/master or use the current checkout's HEAD. Refresh the target ref when
   available. If it cannot be refreshed, report the unverified freshness of the
   recorded SHA. For existing task isolation, inspect its baseline and complete diff
   against the target; preserve task/user commits without silently resetting or rebasing.
3. If task isolation does not exist, use the user's requested branch/worktree or
   choose a suitable task branch/worktree.
   A PR request already authorizes routine branch creation. Prefer a host-native
   worktree capability when available, then use Git if necessary.
4. Prefer an explicitly requested location, then an existing worktree convention.
   Before creating an in-repository worktree, verify the chosen directory is ignored
   with `git check-ignore`. If it is not, prefer an external task directory over an
   unrelated ignore-file change. Create the worktree with
   `git worktree add -b <branch> <path> <target-sha>`, or create a branch with
   `git switch -c <branch> <target-sha>` in a suitable clean checkout. Use a different
   starting commit only for an explicitly intended stacked/dependent change, recording
   its relationship to the PR target. Report permission failures and use another
   authorized, non-destructive isolation method.
5. Inspect dependencies and installation scripts. Run relevant baseline checks in the
   available environment. Distinguish pre-existing failures, environmental blockers
   and new regressions; continue work that does not depend on a blocked check.

## Finish

1. Inspect the complete diff and run checks appropriate to the changed behavior.
   Fix new failures. Explain unavailable checks or baseline failures honestly; use a
   draft PR when the remaining uncertainty warrants it.
2. Recheck the recorded target branch and SHA for drift. Review the full PR diff
   against that target and identify unrelated commits before delivery. Preserve user
   changes; do not silently change the target or rewrite history to refresh the base.
3. Perform the already requested delivery. If no outcome was specified, offer the
   appropriate choices: PR, retain, merge or discard. Do not repeat that question
   after the user has selected an outcome.
4. Deliver according to that choice:
   - **PR:** push only the task branch and open the PR against the target. Keep the
     worktree for review iterations.
   - **Retain:** report the branch and worktree path without deleting them.
   - **Merge:** only when requested, inspect the target worktree, update it without
     overwriting user work, merge and verify the resulting revision. Clean up only
     resources owned by this task.
   - **Discard:** show the exact branch, commits and worktree to remove, obtain
     explicit confirmation, then remove the owned worktree before deleting its branch.
5. Record ownership when creating resources; a directory name does not prove ownership.
   Do not remove host-managed worktrees. Run worktree removal from outside the worktree
   being removed, then prune stale metadata if needed.

## Constraints

- Never claim checks passed without evidence or hide verification limits.
- Do not remove a PR/retained worktree or resources this task did not create.
- Do not discard work or force-push without explicit authorization.
- In connector-only workflows, preserve the base tree, write to a separate branch,
  and verify the remote diff and PR URL. Never move the base reference.
