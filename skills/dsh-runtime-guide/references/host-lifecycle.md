# Host lifecycle

DSH has four separate scopes; do not collapse them:

| Scope | What it is | Change takes effect |
|---|---|---|
| Host process | the running Node/dsh process | restart |
| Session | one conversation/log stream inside the host | only within that host process |
| Profile | `$DSH_HOME/profiles/<name>/package.json`, patch, `node_modules` | next boot of that profile |
| Workspace | the repository cwd the agent edits | immediately for files; build/restart for servers |

A client bundle can be served and refreshed without a host restart only while its
registration and composition stay unchanged, and only when `pnpm run dev:web` is
running; otherwise rebuild and hard-refresh. A host plugin row, inject list, profile
bundle, or dependency change needs a host restart. A change to the dsh package itself
needs an external stop/install/start.

The host is also the session. Stopping it terminates the current turn; the agent may
not receive a tool result for the command that stopped it. Prefer a supervisor or an
external shell when the change can kill the caller.

## Restart checklist

1. Record version, profile, port, PID, and the exact files that will change.
2. Stop the processes that own this profile/install and native modules (not unrelated
   hosts); confirm the port is free.
3. Start the same pinned version/profile under the supervisor.
4. Read the boot output for `pending`, `plugin tree failed`, or a missing roster entry.
5. Verify the web/client or one host path; record what was not tested.
