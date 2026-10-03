# Agent Note: paseo-daemon .path unit must not quote PathModified

Status: implemented — systemd [Path] settings take the value literally; the
quotes written by install.sh made `paseo-supervisor-refresh.path` unloadable
("bad unit file setting"), so `enable --now` failed on every re-run.

## Problem

`refresh_path_body()` passed the package scope dir through `systemd_quote`,
producing `PathModified="/home/…/@getpaseo"`. That quoting is correct for
`ExecStart=` lines — systemd strips quotes when splitting command arguments —
but `[Path]` settings use the raw value: a leading `"` makes the path
non-absolute, systemd logs `PathModified= path is not absolute, ignoring`
plus `Path unit lacks path setting. Refusing.`, and the unit enters
`bad-setting` state. Every re-run of install.sh then died at
`systemctl --user enable --now paseo-supervisor-refresh.path`.

The failure was compounded by `run_systemctl`, which appended its "run this
script from a real login session" hint to *any* systemctl failure — the user
was already in a real login session, so the hint pointed at the wrong cause.

## Decision

- `refresh_path_body()` writes `PathModified=$PKG_SCOPE_DIR` unquoted, guarded
  by a new `validate_path_setting()`: the path must be absolute and free of
  leading/trailing whitespace, quotes, backslash, CR/LF, and `%` (a unit-file
  specifier even inside [Path] values). Internal spaces are kept — verified
  `systemd-analyze verify` accepts them.
- `run_systemctl()` now only prints the user-bus hint when the output matches
  bus-connection errors; other failures die with the raw output and exit code.

## Alternatives considered

- **Keep quoting and escape for [Path] semantics**: systemd path settings
  have no escape mechanism the way Exec lines do; there is nothing to escape
  *to*, so rejecting unencodable paths is the only safe option.
- **Quote only when the path contains spaces**: quotes are literal in [Path]
  values regardless of whether they wrap spaces — always wrong, not
  conditionally wrong.
- **Leave run_systemctl's hint unconditional**: it misdiagnoses every
  non-bus failure (this bug included); narrowing the pattern keeps the useful
  case (missing user bus) without the false lead.

## Consequences

- Deployments with the broken unit file keep failing until the unit is
  regenerated: re-run install.sh, or rewrite
  `~/.config/systemd/user/paseo-supervisor-refresh.path` without quotes and
  `systemctl --user daemon-reload && systemctl --user enable --now
  paseo-supervisor-refresh.path`.
- `test_install_sh.py` gained `RefreshPathBodyTest` pinning the unquoted
  output and the rejection rules.
