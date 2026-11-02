# Compaction

DSH compacts when the assembled history crosses a model/window threshold. The
`compaction-basic` plugin exposes `thresholdRatio`, `headroomTokens`, `retainRatio` or
`retainTokens`, `maxTokens`, `auto`, and per-model policies.

Observed events: `compaction/start`, `compaction/end`, `compaction/summary` (summary
text), `compaction/prune` (shadowed event sequences). A healthy compaction reduces
context and lets the turn continue; a too-low threshold with a tiny retention budget
can cause re-reading and repeated compaction with no forward progress.

Check:

1. context window and case size;
2. compaction count and summary/prune counts;
3. tokens before/after if available;
4. whether the final answer still contains the required facts (post-compaction recall);
5. whether the case actually edited/verified the artifact.

A zero count is not evidence that compaction is unnecessary; it means the case did
not create pressure.
