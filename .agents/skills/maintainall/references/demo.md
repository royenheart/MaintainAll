# MaintainAll README demo case

The README uses one live English light-theme GIF. There is no banner and no launch film.

## Goal

Show a complete MaintainAll workflow without a first-time viewer having to infer transitions:

1. start a blank session;
2. run a real deploy check;
3. save the session as an ops task;
4. run the task once;
5. enter the replay session immediately and land on `DEPLOY_CHECK_OK`.

The artifact must also prove the real model, task, and replay path worked.

## Current artifact

- `docs/assets/maintainall-demo.gif`
- 28.8 s, 950×563, 3.6 MB, 12 fps
- live capture with a post-composed chapter rail
- visible replay run: `20261028-030658-cf17aabf`
- task: `payments-deploy-light2`
- code commit: `5ea65f1`

## Decisions

- English light theme; no dark-mode variant.
- Five-stage vertical chapter rail: initialize, run checks, save task, replay, result.
- Large `01–05` chapter index, one-line uppercase labels, floating white active card, green completed chapters, dynamic footer.
- Rail width is set from the longest label, not from a fixed narrow column.
- No decorative cursor, spinning dot, or random blue frame.
- Task fields are typed at 18–70 ms per character; the save dialog remains readable.
- Run once dispatches a replay session; the recorder opens that session immediately and waits there.
- The rail is an overlay on the live capture; interactions are not rebuilt.
- Trim only the first 0.8 s of idle load.

## Pitfalls observed

- A 112 px rail with 40 px circles and 2–3 line labels overflows.
- A progress rail that covers the product's own sidebar creates two competing navigations.
- A focus frame that is not tied to the current action looks random.
- Filling a form instantly makes the save step unreadable.
- Waiting on the task panel and later jumping to the result breaks the causal chain.
- A live badge is not evidence by itself; the task/run IDs and commit belong next to the artifact.
- Splicing different takes changes rail state and UI state; avoid it.

## Production recipe

1. Boot a scratch DSH home and workspace; use the English light theme.
2. Inject the chapter rail and redaction overlay.
3. Drive the real prompt, wait for the actual result table, and open Save.
4. Type every field at a readable cadence; choose a valid trigger.
5. Confirm the task exists through the API before continuing.
6. Open Ops, run once, then open the newly created replay session.
7. Stay in the session until the result; take the final still/frame there.
8. Encode at 12–15 fps with a fixed palette; inspect the exported GIF at README width.

This file holds only the project-specific decisions and evidence.
