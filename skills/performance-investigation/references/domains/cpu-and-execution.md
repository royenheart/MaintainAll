# CPU and execution

## Separate excess work from expensive execution

Model useful work as input size/shape changes. Compare operation counts and scaling curves before optimizing an instruction-level hotspot. Repeated traversal, recomputation, serialization, dispatch and algorithmic growth can produce the same sampled hot function but call for different interventions.

Ask whether the limit is work volume, instruction execution, data access, scheduling or coordination. Correlate stacks with thread state and the enclosing operation. Follow off-CPU intervals and wakeup chains when runnable work does not explain elapsed time; inspect other participants when the sampled process mostly waits.

## Choose perturbations that distinguish mechanisms

- Hold useful work fixed while varying workers, placement or competing load. Locate the transition from parallel benefit to coordination, bandwidth or scheduling cost; inspect the changed region rather than tuning only the best point.
- Change data size, layout, locality or access order while preserving the algorithmic result. Use the response to distinguish computation from movement and locality effects.
- Remove or batch a repeated unit, then check whether reduced instructions/calls also shorten the critical path. If not, investigate overlap or another limiting stage.
- Compare relevant runtime/build states with symbols/source attribution. Separate interpreter/JIT warmup and optimization effects from changes in the source algorithm.

For shared-state workloads, examine lock ownership, false sharing, queue structure and work imbalance together. A faster local loop can increase downstream contention. Test both the isolated unit and the enclosing execution policy.

## Instrumentation leads

Seek system-wide and per-thread scheduling views, call stacks, hardware-event correlation and blocked-stack ownership. Depending on the platform, leads include perf/eBPF, ETW/WPA, Instruments or hardware-vendor profilers. Use compiler optimization reports, disassembly or source-level tools only when the current hypothesis requires that resolution. Select events and collection scope from the installed tool and hardware capabilities.

Validate the proposed mechanism with a workload or implementation intervention and rerun at the original operating point. Distinguish optimization of local work from improved parallel scaling or system completion.
