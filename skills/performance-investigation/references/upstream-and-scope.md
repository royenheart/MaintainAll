# Upstream and change scope

Inspect the latest relevant branch and search issues/PRs by symptom, symbols and paths. For broad audits, record pagination/search scope; changed-file overlap can discover work with different terminology. Inspect candidate diffs before declaring a duplicate.

Distinguish merged/present, open competing work, closed-unmerged, superseded, partial and unrelated changes. Check the implementation or containing commit. A closed PR is not proof the code ships, and a history-replay fix may leave enumeration unchanged.

Pin revision/date and refresh relevant states before delivery. If files or the affected method match the measured baseline, record that exact comparison. Patch-application checks establish applicability, not new runtime measurements.

Trace apparently wasteful branches back to their constraint: older candidates, encoding identity, errors or another supported path. Keep documented intent distinct from an inferred oversight, preserving the necessary behavior while fixing redundant work or mistaken classification.

Review contracts the patch actually changes: membership/order, pending snapshots/deadlines, cache invalidation, retry/errors, process ownership, keyboard/focus/DOM availability, interfaces, wire/persistence and platform paths. State relevant changes without inventing a vulnerability or wrong-result bug for an efficiency enhancement.

[Change-review guidance](../../change-review-preview/references/review-and-publication.md) owns public wording and publication; this skill owns experiments and attribution.
