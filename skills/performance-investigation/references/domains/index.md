# Domain methods

Enter by the execution boundary or unresolved question, not by a tool already available. Read one relevant guide first and add another when evidence crosses the boundary. The guides offer ways to discriminate mechanisms and identify useful observation capabilities; commands and tool operation belong to installed help/current documentation.

| Current question | Read |
|---|---|
| Execution hot path, parallel scaling, scheduling or hardware sensitivity | [CPU and execution](cpu-and-execution.md) |
| Device submission/completion, kernels, transfer/overlap or accelerator scaling | [GPU and accelerators](gpu-and-accelerators.md) |
| Allocation, retention, pauses, JIT/runtime state or memory-pressure behavior | [Memory and runtimes](memory-and-runtimes.md) |
| Loading, interaction, rendering, UI framework or compositor latency | [Browser and UI](browser-and-ui.md) |
| Web/backend throughput, queues, fan-out, distributed critical paths or overload | [Services and distributed systems](services-and-distributed.md) |
| Query plans, data access, caching, filesystems or persistence | [Storage and data systems](storage-and-data.md) |
| Connections, framing, payload movement or network-path behavior | [Network and transport](network-and-transport.md) |
| Build/test pipelines, imports, dependency discovery or cold startup | [Build and startup](build-and-startup.md) |

A problem can involve several domains: a browser can wait on backend queues, a GPU can wait on a data loader, and a database can spend time on host scheduling or network storage. Use a system timeline and a targeted perturbation to decide where to move next.

For an unlisted domain, identify its useful completion event, work unit, execution/dependency graph, controllable inputs and resource constraints. Search the system's native diagnostics and existing benchmarks for observations that distinguish those mechanisms. Adapt a nearby method rather than forcing the workload into a checklist; extend the index only when a reusable decision technique warrants it.
