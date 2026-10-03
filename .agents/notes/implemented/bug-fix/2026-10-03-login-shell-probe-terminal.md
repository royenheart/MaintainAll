# Agent Note: login-shell probes run in their own session, never the installer's

Status: implemented — the interactive login-shell probe could stop the whole
installer process group with `kill(0, SIGTTIN)`; probes now run via
`start_new_session=True` (+ stdin=DEVNULL) so no controlling terminal exists
at all.

## Problem

Over an interactive SSH session, install.sh stopped right after the
"Sniffing the login shell" step: `[1]+ Stopped ./install.sh`. Forensics on
the stopped processes showed install.sh, its `sync_login_env.py` child, and
the probe bash all stopped in the same process group, and the probe frozen
mid-`kill(0, SIGTTIN)` — bash's job-control guard
(`while (tcgetpgrp(tty) != getpgrp()) kill(0, SIGTTIN);`).

Mechanism: the snapshot runs three probes, two with `-i` so rc-file
interactivity guards pass. Interactive bash opens **/dev/tty** for job
control even when its stdio is piped or /dev/null — it does not use the stdio
fds. Probe 2 (`bash -i`) setpgids itself and `tcsetpgrp`s its own group into
the foreground of the installer's terminal, then exits. Probe 3 (`bash -l -i`)
starts back in the installer's process group — now backgrounded — sees
`tcgetpgrp != getpgrp`, and stops its **whole** group with `kill(0, SIGTTIN)`.
Deterministic, and specific to interactive sessions where the outer shell
gives install.sh its own process group; under `ssh host 'bash -c ...'` the
installer shares the remote shell's group and the same sequence can leave the
foreground on a dead group without an obvious symptom, which is why early
reproduction attempts "passed".

An earlier `stdin=DEVNULL`-only change did not help: it keeps fd 0 away from
the probe but says nothing about /dev/tty.

## Decision

`default_runner()` passes `start_new_session=True` and `stdin=DEVNULL`. A
new session has no controlling terminal, so bash's open("/dev/tty") fails,
job control is off ("no job control in this shell" on its captured stderr),
and the steal-and-stop sequence is impossible regardless of how the
installer itself was launched. Probes still run rc files with `$-` containing
`i`, which is all the snapshot needs.

Verified on the affected host: an interactive-login-shell SSH session
(`bash -il`, like the reporter's) stopped 25s after the password prompt
before the fix and ran to "Installed. Common commands" after it.

## Alternatives considered

- **stdin=DEVNULL only**: shipped first, insufficient — bash job control
  hangs off /dev/tty, not fd 0; kept as defense in depth.
- **Drop the `-i` probes**: rc files gate toolchain exports behind
  `case $- in *i*)`; losing them was the original reason for the probes.
- **Capture the foreground group before probing and restore it after**:
  racy — a probe killed mid-sequence leaks the terminal state, and the
  restore needs privileges/ordering the installer does not have.
- **Document "if it stops, fg it"**: a deploy script that can park itself
  mid-install is a trap; the fix removes the cause.

## Consequences

- Probes are hermetic to the installer's terminal in every launch shape
  (interactive SSH, `ssh host cmd`, cron, CI); DefaultRunnerTest pins the
  subprocess contract.
- Any future probe that needs a pty (none today) must allocate its own.
