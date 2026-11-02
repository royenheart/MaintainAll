---
name: dsh-sandbox-attribution
description: Use when a command in this session cannot see or open a GPU or /dev node the task needs, before concluding that the host lacks it or that the application is broken.
---

# DSH sandbox attribution

Separate three layers before giving a cause:

1. the host;
2. an outer container or CI jail, if one exists;
3. the DSH inner sandbox.

Do not stop at "the command failed". Find which layer removed the object and say so explicitly.

## Procedure

1. Name the exact object and the exact failing command.
2. Read `/proc/self/mountinfo` and look at `/dev` entries:
   - a `/dev` tmpfs whose parent is another `/dev` mount means a later sandbox layer created its own `/dev`;
   - a mountinfo line that binds a device path under `/dev` means the device exists on a lower layer, even if a later `/dev` mount hides it from `ls`;
   - `/proc/1/cmdline` shows the inner DSH bwrap argv; it does not by itself distinguish outer from inner.
3. For GPU cases, read `/proc/driver/nvidia/version` and `lspci -nn | grep -i nvidia`.
4. Compare:
   - device bind exists + later `/dev` mount hides it -> `dsh`;
   - two stacked `/dev` tmpfs mounts, no device bind -> `both` (outer and inner); cite both mount lines, otherwise the claim is incomplete;
   - one `/dev` tmpfs, lower `/dev` is the host devtmpfs, driver present in `/proc/driver/nvidia` -> `dsh`;
   - no device bind anywhere + host driver/device exists and there is independent evidence of an outer layer -> `outer`;
   - host driver missing and the application itself errors -> host/app, not a sandbox;
   - neither pattern fits -> `ambiguous`.
5. Cite the exact line that shows which layer removed the object, and state the layer label (`dsh`, `outer`, `both`, `ambiguous`) in the blocker text. Copy a verbatim substring from the tool output; do not paraphrase (for example, `no nvidia mount lines` is not evidence). Do not cite command header lines such as `=== nvidia mentions ===`; cite the output line itself. If no layer can be identified, say `ambiguous` rather than guessing.
6. An `unavailable` escalation is evidence that the current session cannot widen the sandbox; record it once instead of retrying.

## Negative controls

A real application bug or a genuinely missing input is not a sandbox blocker. If the app crashes with a traceback, fix or report the app; if the input file is absent, report `missing-input`.
