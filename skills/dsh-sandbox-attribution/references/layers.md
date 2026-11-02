# Layer evidence

- Inner DSH bwrap: a second `/dev` tmpfs after the outer mount. `/proc/1/cmdline` shows the inner bwrap but not which layer removed a device.
- Outer jail: independent evidence that an outer container/CI layer exists (a separate parent mount or an outer host process).
- Device bind: a `/proc/self/mountinfo` line that mounts a device path under `/dev`.
- Host driver: `/proc/driver/nvidia/version` or `lspci -nn | grep -i nvidia`.
- Escalation: `sandbox escalation ... requires approval ... no approval channel` proves the current mode cannot widen; cite it once.

Do not claim the host lacks a device from a confined probe alone.
