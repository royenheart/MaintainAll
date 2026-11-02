# Upgrade and recovery

## Global dsh upgrade from inside a session is structurally unsafe

The session executes from the package tree that npm is replacing. An interrupted
install can leave package content present without regenerated shims; the `dsh`
command can disappear. Never run a global install from a session on that host.

Correct hand-off:

1. Stop the dsh processes that own this install prefix/profile/port (a browser refresh is
   not a stop). Identify them first; do not kill unrelated hosts. A running host can hold the session-log lease or a file lock (`EBUSY`);
   identify the owner rather than assuming a native module.
2. From an external terminal, run a pinned install:
   `npm install -g @deepseek-ai/dsh@<exact-version>`.
3. Start `dsh web`, hard-refresh the browser, verify version markers and plugins.

A bare package name follows the `latest` dist-tag and can silently downgrade; use an
exact version.

## Interrupted install

Do not hand-copy package directories or hand-write shims. Re-run the pinned formal
install from an external shell. If the command is gone, repair the package manager
entry from an external environment with the same prefix.

## Ghost host

The disk can say the new version while the running process executes the old code.
Compare the process start time with the checkout's last change, and with the mtime of
the actually loaded entry. A dirty working tree or an entry modified after start is a
stronger signal than the commit alone. Then probe a behavior that differs across
generations. If it is a ghost, restart it or pin the analysis to its actual generation.`scripts/inspect-host.mjs` reports start/commit, dirty status, entry mtime and `exePath`;
it does not prove generation by itself.
