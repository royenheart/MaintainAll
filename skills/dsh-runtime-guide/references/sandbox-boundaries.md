# DSH sandbox boundaries

DSH's process sandbox is a **file-effect confinement seam**, not a VM or a full security
boundary. It shares the host kernel and filesystem. The modes are:

| Mode | File effects |
|---|---|
| `read-only` | no writes; `/dev/null` remains a sink |
| `workspace-write` | writes only under the session workspace, explicit extra roots, and the backend temp area |
| `danger-full-access` | no confinement; the sandbox provider is not consulted |

Network access, process visibility, credentials, syscalls, devices and GPU are **outside**
the file-effect vocabulary. The local Linux backend uses bwrap with:

- a read-only host root;
- a fresh, private `/dev` (only basic nodes, **not** `/dev/nvidia*` or `/dev/dri`);
- `/proc` from a private PID namespace (host processes are not visible);
- an ephemeral `/tmp`;
- writable binds for the workspace and explicit extra roots.

Enforcement is reported as `full` or `partial`; older Landlock and Windows ACL are partial
cases. If no runner can enforce a confined mode the call fails closed with
`SANDBOX_UNAVAILABLE`; a denial is `denied: true`, not a task failure. The default policy
is `read-only`; deployments opt into `workspace-write`.

## Host fact vs sandbox artifact

Do not conclude "the host has no GPU / no network / no process" from a confined command.
Distinguish:

| Observation | Meaning |
|---|---|
| `nvidia-smi` exit 9, no `/dev/nvidia*` in the confined process | the sandbox did not expose devices; host may still have one |
| `/sys/class/drm` has render nodes, `/proc/driver/nvidia/version` exists | host kernel/driver evidence; still not proof the caller can open devices |
| `danger-full-access` (approved) sees `/dev/nvidia*` and `nvidia-smi` works | host capability confirmed; the confined view was the limitation |
| `codex`/nested agent says `Read-only file system` under `~/.codex` | nested runtime cannot write its state in this sandbox; not an audit failure |
| `SANDBOX_UNAVAILABLE` | runner could not enforce the mode; do not silently run unconfined |

Diagnosis order:

1. Record the active sandbox mode and workspace (session `sandbox/mode`, `sandbox:policy`).
2. Check whether `/dev` is a private tmpfs and whether `/proc` is a private PID namespace.
3. Check host evidence separately (`/sys/class/drm`, `/proc/driver/nvidia/version`,
   `/sys/module/nvidia`) without claiming it is accessible.
4. If the task needs hardware, devices, a display, host processes, or a nested agent's
   state, request the narrowest wider mode with a one-sentence justification. Retry the
   **exact** command; the approval is external to the command.
5. If no approval is possible, report the boundary and a host-run/isolated-container
   alternative. Never rewrite the finding as "host absent".

## Stable or changing?

The package reference calls the sandbox the default local backend and describes the modes
as the contract; the implementation is fail-closed and covered by kernel-level e2e tests.
The documented limitations are current constraints, not a roadmap promise:

- file effects only; no network/process/syscall/device policy;
- Linux bwrap's private `/dev` and `/proc`;
- runner selection is cached for the provider lifetime;
- custom `runnerCommand` is an operator assertion;
- Windows/Landlock partial enforcement;
- no out-of-band runner-status channel yet (stderr dialect).

No official statement was found that bwrap device visibility or `/dev` behavior will change.
Treat the current behavior as the supported contract and pin/verify the dsh version when a
task depends on devices.

Sources in the dsh checkout: `packages/sandbox/sandbox/README.md`,
`packages/sandbox/sandbox-local/README.md`, `packages/shell/bash-sandbox/README.md`,
`docs/subsystems/sandbox.md`.
