# Storage and data systems

## Recover the data-access plan

Follow logical demand into queries, access paths, files, buffering, locks and persistence. Identify the actual data shape: cardinality, skew, selectivity, locality and update pattern can change the plan. Separate time spent choosing/planning work from executing it and waiting for other participants.

Compare estimated and observed work at the relevant stage. A slow data operation can be dominated by excess candidates, poor access order, lock ownership, repeated metadata work, durability boundaries or remote storage rather than one expensive read.

## Choose data-sensitive interventions

- Vary size, selectivity, ordering or skew and examine plan/work changes. Check where scaling changes regime rather than extrapolating from a tiny uniform fixture.
- Push a predicate, reduce materialization, batch operations or change an access structure while verifying complete results and ordering. Avoid silently improving performance by narrowing eligible data.
- Distinguish cold and reused state at the relevant cache layers. Use isolated test resources for destructive cache/state resets; do not assume a reconnect or process restart clears every layer.
- Vary concurrency and transaction boundaries to investigate lock owners, snapshots and write amplification. Validate consistency/durability requirements with the proposed execution policy.

For filesystems, trace discovery/metadata and content work separately and include network/FUSE behavior when deployed that way. For data platforms, account for partitioning, exchange, shuffle, spill and uneven participants rather than only a final query duration.

## Instrumentation leads

Use actual query/execution plans, engine statistics, lock/transaction diagnostics and host I/O traces according to the suspected boundary. [PostgreSQL's plan analysis](https://www.postgresql.org/docs/current/using-explain.html) illustrates estimated-versus-executed work; other engines have their own observation semantics. Execution-based diagnostics can run the operation and alter state, so use the authorized test workload. Filesystem/OS tracing or storage telemetry can discriminate lower-layer explanations.

Recheck the original access path and representative concurrency after a change, including affected ingestion/update costs and cache/invalidation behavior.
