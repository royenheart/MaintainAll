---
name: minimal-probe
description: Use when a command in this session cannot see or open a GPU or /dev node the task needs.
---

# Probe the layers

When a GPU or `/dev` object is missing:

1. read `/proc/self/mountinfo` and `/proc/driver/nvidia/version`;
2. quote the exact `/dev` mount or device-bind lines;
3. name which layer removed it: `dsh`, `outer`, `both`, or `ambiguous`.

Do not use a decision table; report what the probes show.
