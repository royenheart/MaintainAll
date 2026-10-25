# Complex reference-task observations

The fixed `gpt-6.1-sol` / `low` comparison completes twelve CLI invocations: two tasks, two frozen skill snapshots, and three genuine turns per conversation. Every turn passes the declared delivery/container checks and returns image-tool items; the reference bytes remain unchanged. These checks do not establish independent source reconstruction or artistic quality. Completion is derived from the immutable result rows. The stored `manifest.state` label remains `running` and is not a completion verdict.

The root agent reviews 28 unique PNGs across 48 preview slots, reusing observations only for identical SHA-256 images. All 94 applicable ratings are frozen before the arm map is read. This is a single-agent artifact review with partial anonymization, not independent human preference validation. The frozen rating record has SHA-256 `ab70418c3c78ec441e05a40490c0f6a5f9b941812d5c04379ef4132f530da7d5`; the aggregate record is in [review summary](complex-review-summary.json).

| Snapshot | Rating 2 | Rating 1 | Rating 0 | Withheld / unverifiable |
| --- | ---: | ---: | ---: | ---: |
| Frozen v1 (`old`) | 43 | 3 | 0 | 1 |
| Current (`new`) | 42 | 4 | 0 | 1 |

These two tasks do not show a quality gain or stable version separation. Both costume outputs only partially convey construction and attachment-side ownership in round 1. Both round-3 airy material treatments remain relatively flat and partly depend on handoff annotation. The current exhibition's round-1 small-corner `FREE ENTRY` readability receives a partial rating; that observation does not define a universal pixel threshold.

The exhibition `reading-hierarchy` atom requires date and venue to precede supporting copy, while the first-round prompt only requests a clear reading order. Its round-1 score is withheld for both snapshots as a task/rubric alignment limit, not a model error. After round 2 explicitly introduces that priority, both receive 2. The [costume](cases/complex/tasks/reference-costume.json) and [exhibition](cases/complex/tasks/editorial-transfer.json) cards, rating record and model outputs remain unchanged.

Normalized total time is 747.619 seconds for the frozen v1 snapshot and 937.518 seconds for the current snapshot; uncached input tokens are 117,514 and 164,746 respectively. The current snapshot is slower and uses more uncached tokens in this sample. Two tasks, one repetition and fixed ordering do not support a causal or general performance claim. The framework's mechanical `quality_status: unassessed` remains separate from the saved review's `manual_review` status; neither produces an automatic aesthetic pass or aggregate aesthetic score.
