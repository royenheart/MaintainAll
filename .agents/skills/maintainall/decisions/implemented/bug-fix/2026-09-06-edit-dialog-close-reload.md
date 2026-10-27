# Decision: edit dialog close and sidebar refresh

Status: implemented — edit dialog closes through one path and the sidebar reloads after edit.

## Problem

Editing a task from the Ops drawer had two defects: the task icon/color changes never appeared in the sidebar after saving, and clicking Edit a second time did not reopen the dialog. The modal overlay and Cancel button called `setOpen(false)` directly, bypassing `onClose`, so `editingTask` stayed set and the mounted dialog kept `open: false` on the next edit. The manual edit submit also posted to `POST /save`, which requires a live source session, so the request was rejected and the list was never reloaded.

## Decision

- `SaveOpsAction.close()` is the single close path: it sets `open` false and then invokes `onClose`; overlay and Cancel use it.
- The Ops drawer's `onClose` clears `editingTask` and calls `reload()`, so the list reflects new icon/color/name immediately.
- Manual edits post to `POST /tasks/<id>/edit` with `materialize: true`, which updates the task asset without a source session; after writing, the host reloads its in-memory registry from disk and calls `TriggerEngine.reload()`, so `GET /tasks` reflects the new name/icon/color immediately.
- Natural-language edits post to the same route with `auto: true`, which opens the edit session.

## Alternatives considered

- **Keep `/save` for manual edits and make `sessionId` optional.** Rejected: `/save` is semantically "cut a seed from a session"; edits are metadata-only and have no session.
- **Only clear `editingTask` on submit, leave overlay/cancel as `setOpen(false)`.** Rejected: any non-submit close would still wedge the dialog closed.

## Consequences

- The edit dialog unmounts on every close, so each Edit click mounts a fresh dialog with the latest task detail.
- Sidebar task rows update without reopening the drawer.
