# Agent Note: paseo daemon environment must pin the install-time npm

Status: implemented — `sync_login_env.py --ensure-path-dir` prepends the resolved `paseo`/`node` bin directories to the exported PATH, and `install.sh` always passes them.

## Problem

On `nebusec-dev` the GUI's "update daemon" failed with "@getpaseo/cli is not installed with npm -g on this host". The daemon checks its self-update precondition by running `npm -g ls @getpaseo/cli --json` **with its own PATH** (see `npm-global-cli.js` in the server package). That host has a system node at `/usr/bin/node`, and the user's nvm setup is not exported by login shells, so the probe behind `60-paseo.conf` captured a PATH without the nvm bin directory. The daemon therefore ran every npm operation through the system npm, whose global prefix does not contain `@getpaseo/cli` — `npm -g ls` found nothing and the update refused to run. The unit's `ExecStart` was correct (absolute resolved path under nvm); only the daemon's *environment* pointed at the wrong toolchain. The existing guard — refuse to write when the probed PATH lacks `node` — could not catch this, because `/usr/bin/node` satisfied it while being the wrong pairing.

## Decision

Pin the toolchain the installer actually verified:

- `install.sh` computes the bin directories of `command -v paseo` (the npm global shim location) and `command -v node` and passes them to `sync_login_env.py` as repeated `--ensure-path-dir DIR`.
- `sync_login_env.py` merges them into the probed PATH with a pure `merge_path` function: extra dirs first, de-duplicated, empty entries dropped; applied both to the written `60-paseo.conf` and to `--emit-env PATH` (the value pushed into the user manager). The node guard runs against the merged PATH, so a probe that lacks node entirely now still exports a usable one.
- No behavior change on hosts where the probe already has the same dirs first (the common nvm case): the merge is a no-op there.

## Alternatives considered

- Document "make your login shell export nvm". The deploy cannot enforce user dotfiles; the snapshot exists precisely because login-shell contents are unreliable, and headless servers commonly load nvm only in interactive shells.
- Write `npm_config_prefix` or an absolute npm path into the daemon env. Couples to npm internals and breaks the moment the node version changes; a PATH entry follows the resolved toolchain naturally.
- Resolve npm's global root at install time and hard-code it. The daemon spawns `npm` by name, so PATH is the lever that decides which npm runs; fixing the root without fixing the binary would still run the wrong npm for the install step itself.

## Consequences

After re-running `install.sh`, the daemon's PATH starts with the install-time toolchain dir (for nvm, `~/.nvm/versions/node/<ver>/bin`), so its self-update probes and installs through the owning npm. A side effect: the daemon's shebang `node` now also resolves to that toolchain instead of a system node, which is the pairing the installer verified. Switching node versions still requires re-running `install.sh`, same as before. `merge_path` is covered by unit tests with synthetic inputs; no real environment or secret is needed.
