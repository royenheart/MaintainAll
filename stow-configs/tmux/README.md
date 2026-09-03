# tmux

## Periodic autosave (backed by tmux-resurrect)

Prevents losing window state on an unexpected shutdown/disconnect. The current
state is shown in the status bar, right of the session name, left of the clock
and separated from it by `|`:

- Green `AUTOSAVE ON(5m)` — enabled; the label in parentheses is the interval
- Red `AUTOSAVE OFF` — disabled (`prefix + Ctrl+s` still saves manually)

### Keys

| Key | Action |
|---|---|
| `prefix + S` | Toggle autosave on/off (turning it on saves immediately) |
| `prefix + M-s` | Open the settings popup (toggle + interval editor) |
| `prefix + Ctrl+s` | Save now (tmux-resurrect) |
| `prefix + Ctrl+r` | Restore the latest snapshot (tmux-resurrect) |
| `prefix + M-r` / `M-d` | Restore / delete a snapshot from the fzf menu |

In the settings popup, type digits into the **number box** (left) and cycle the
**unit box** (right) with the **up/down arrows** through `s m h d`. `space`
toggles autosave, `s` saves now, `r` resets the interval to `300s`, and
`q` / `Esc` / `Enter` closes. Every change is applied immediately.

### Options

Defaults are **enabled**, interval **300 seconds (5m)**. Adjust at runtime
(applies from the next save cycle; the status label refreshes via the popup or
the next loop wake):

```tmux
tmux set -g @autosave-enabled 1     # 1 = on / 0 = off
tmux set -g @autosave-interval 300  # interval in seconds
```

- Saving reuses tmux-resurrect's `save.sh` (`quiet`), so restoring still goes
  through `prefix + Ctrl+r` or the `prefix + M-r` snapshot menu. Unchanged
  layouts are de-duplicated by resurrect (no file spam).
- `prefix + r` reloads never reset the runtime toggle/interval: defaults are
  written only when the option is unset (edit those defaults in the two
  `if-shell` lines of `.tmux.conf` §4.1).
- Depends on tmux-resurrect (declared in `.tmux.conf` via TPM). While the
  plugin is missing the loop skips saving and picks it up automatically once
  installed.

### Implementation

`.tmux/scripts/tmux-autosave.sh` is the background loop, started by
`.tmux.conf` via `run-shell -b`; its PID lives in `@autosave-loop-pid` so every
tmux server has exactly one instance and reloads are harmless. The interval is
stored in seconds (`@autosave-interval`) and humanized into
`@autosave-interval-label` for the status line. `.tmux/scripts/tmux-autosave-menu`
is the settings popup.

If you manage `~/.tmux/scripts/` with per-file symlinks and the two new files
are missing, link them once and reload with `prefix + r`:

```bash
ln -s "$PWD/stow-configs/tmux/.tmux/scripts/tmux-autosave.sh"  ~/.tmux/scripts/tmux-autosave.sh
ln -s "$PWD/stow-configs/tmux/.tmux/scripts/tmux-autosave-menu" ~/.tmux/scripts/tmux-autosave-menu
```

## Auto-update tmux

A tmux 3.3+ version is recommended for better copying. After loading the
config, `prefix + T` builds and installs the latest tmux into
`~/.local/tmux` in the background.

## Copying does not work on macOS terminals

OSC 52 needs to be enabled:

1. iterm: settings -> general -> selection -> enable "Applications in terminal
   may access clipboard".
