# Services and distributed systems

## Follow demand through the system

Map request creation, admission, queues, fan-out, remote work, retries and completion. Relate the offered workload to what is accepted, completed, rejected or abandoned. A lower latency result achieved by reducing delivered work or hiding queue time answers a different question.

Correlate operation identities and execution relationships across participants. Use local timing and known clock relationships; a collection of spans is not automatically an additive critical path. Include client/load-generator behavior when it can throttle or reshape the workload.

## Discriminate queueing, work and coordination

- Sweep arrival rate or concurrency across the operating region. Find where latency/work/error behavior changes and inspect that transition instead of reporting only an uncongested point.
- Choose open- or closed-loop load according to the traffic being modeled. Check completion accounting and whether the generator suppresses observations during stalls.
- Isolate a downstream dependency, change its latency or replace one stage with a controlled equivalent. Observe queue growth, fan-out, cancellation and retry amplification before assigning the cause to that dependency alone.
- Vary skew, tenant mix, cache state or failure rate where they affect the execution policy. Inspect slow operation paths and participants rather than only fleet aggregates.

Test changes to admission, batching, concurrency, caching and cancellation as system policies. Measure their effect on delivered work, latency and recovery together. Check whether the improvement survives another operating point or merely shifts saturation elsewhere.

## Instrumentation leads

Use distributed traces and application/runtime/host diagnostics at complementary scopes. [OpenTelemetry traces](https://opentelemetry.io/docs/concepts/signals/traces/) and trace backends can help recover relationships; load generators and native service diagnostics test the resulting model. Sampling, context propagation and uninstrumented queues affect what the trace can establish. Discover the deployment's existing instrumentation before adding another collection stack.

Validate with the real topology and request mix appropriate to the claim, retaining dependency, load-generator and observer boundaries in the result.
