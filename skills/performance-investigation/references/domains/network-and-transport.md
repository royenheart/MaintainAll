# Network and transport

## Locate the movement and waiting boundaries

Reconstruct connection establishment/reuse, protocol exchanges, buffering, serialization, encryption/compression, forwarding and consumption. Inspect the actual connection/process lifetime rather than inferring a new handshake or round trip from every logical operation.

Correlate operation identifiers and local intervals at both ends where possible. Distinguish application demand, transmitted representation and receiver work. A smaller payload representation or local IPC event count does not by itself locate the user's delay.

## Test the path's sensitivity

- Vary latency, loss, bandwidth or competing traffic in an isolated path to distinguish exchange count, transfer volume and queueing effects. Relate emulated conditions to a real deployment before generalizing.
- Compare new/reused connections and relevant protocol modes with equivalent delivered data. Examine retry, timeout and multiplexing behavior at the transition.
- Vary frame/message sizes, batching or compression and observe both endpoint work and completion. Look for work moved between CPU, buffers, network and the receiver.
- Compare loopback, local forwarding and separate-machine paths when they answer different deployment questions. Inspect the critical path rather than attributing every remote delay to the wire.

When a shared channel stalls, identify the ordering/flow-control dependency that blocks the operation. Packet-level activity alone may miss application queues or renderer work; application traces alone may miss transport behavior. Combine layers to test the explanation.

## Instrumentation leads

Packet captures, TCP/socket diagnostics, network emulation, throughput probes, application traces and endpoint profiles offer different interventions and views. Tools may include Wireshark/tcpdump, platform/eBPF networking diagnostics or controlled path/load utilities. Select them for a concrete hypothesis and consult platform capabilities for collection.

Preserve payload identity, ordering and error behavior when changing framing or bridge representations. Validate sustained flow and connection cleanup as well as an isolated transfer.
