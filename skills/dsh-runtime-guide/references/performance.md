# Performance and resource limits

- Long sessions grow context and session logs; compaction can reduce context but a
  too-low threshold causes repeated compaction and re-reading. Inspect compaction
  events before blaming the model.
- Background jobs and subagents can multiply token, process, and memory use. Bound
  their count, set timeouts, and collect/kill them before delivery.
- Builds, tests, browser drivers, and Docker should not run unbounded in the live host.
  Use a separate profile/port, a bounded job, or a throwaway checkout.
- File replacement can fail with EBUSY when another process holds a lock (including the
  session JSONL lease); identify the lock owner before stopping anything.
- A successful exit code is not a boot check. Read the host's activation/pending
  output and one real path.

Measure token/cache/tool behavior with `dsh-observability` rather than guessing.
