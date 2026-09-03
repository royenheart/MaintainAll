#!/usr/bin/env bash
# tmux-autosave.sh — background loop for periodic autosave (backed by tmux-resurrect)
#
# Started from ~/.tmux.conf via `run-shell -b`, which also happens on every
# prefix + r reload; the single-instance guard below (PID stored in the
# global option @autosave-loop-pid) makes reloads harmless.
#
# Every wake the loop:
#   1. refreshes @autosave-interval-label (humanized @autosave-interval),
#   2. when @autosave-enabled = 1 and tmux-resurrect's save.sh exists, calls
#      it quietly to snapshot all sessions. A missing plugin is simply
#      skipped and picked up from the next cycle.
#
# Options (all server-global):
#   @autosave-enabled          1 = on, 0 = off (default 1)
#   @autosave-interval         interval in whole seconds (default 300)
#   @autosave-interval-label   humanized label, e.g. 5m / 90s / 2h / 1d
#                              (maintained by this script and the settings popup)
#   @autosave-loop-pid         PID of the running loop (maintained here)
#
# Usage:
#   tmux-autosave.sh            refresh the label, then start (or join) the loop
#   tmux-autosave.sh label      refresh @autosave-interval-label and exit
set -u

tmux_cmd="${TMUX_CMD:-tmux}"

get_opt() { # $1 option name, $2 default — prints the value or the default
	local name="$1" default="$2" val
	val="$("$tmux_cmd" show-option -gqv "$name" 2>/dev/null)" || val=""
	if [ -n "$val" ]; then printf '%s' "$val"; else printf '%s' "$default"; fi
}

# Humanize N seconds: 300 -> 5m, 90 -> 90s, 7200 -> 2h, 172800 -> 2d.
humanize() {
	local secs="$1"
	if [ $((secs % 86400)) -eq 0 ]; then
		printf '%sd' "$((secs / 86400))"
	elif [ $((secs % 3600)) -eq 0 ]; then
		printf '%sh' "$((secs / 3600))"
	elif [ $((secs % 60)) -eq 0 ]; then
		printf '%sm' "$((secs / 60))"
	else
		printf '%ss' "$secs"
	fi
}

refresh_label() {
	local secs interval label
	interval="$(get_opt @autosave-interval 300)"
	case "$interval" in
		''|*[!0-9]*) interval=300 ;;
	esac
	[ "$interval" -ge 1 ] 2>/dev/null || interval=300
	label="$(humanize "$interval")"
	"$tmux_cmd" set-option -g @autosave-interval-label "$label" >/dev/null 2>&1 || true
}

# One-shot label refresh (used by the settings popup after changing the interval)
if [ "${1:-}" = "label" ]; then
	refresh_label
	exit 0
fi

# Refresh the label up front so reloads update it even when the loop is already
# running (the guard below then exits without starting a second loop).
refresh_label

# Single-instance guard
existing="$(get_opt @autosave-loop-pid '')"
if [ -n "$existing" ] && kill -0 "$existing" 2>/dev/null; then
	exit 0
fi
"$tmux_cmd" set-option -g @autosave-loop-pid "$$"
trap '$tmux_cmd set-option -g -u @autosave-loop-pid >/dev/null 2>&1 || true' EXIT

save_script="${TMUX_AUTOSAVE_SCRIPT:-$HOME/.tmux/plugins/tmux-resurrect/scripts/save.sh}"

while :; do
	# Sleep a full interval first: a freshly started loop does not save at
	# boot (the first snapshot appears one interval later). Toggling autosave
	# on saves immediately instead.
	interval="$(get_opt @autosave-interval 300)"
	case "$interval" in
		''|*[!0-9]*) interval=300 ;;
	esac
	[ "$interval" -ge 1 ] 2>/dev/null || interval=300
	sleep "$interval"

	# Leave quietly once the owning tmux server is gone, so we never write an
	# empty snapshot against a dead server.
	if ! "$tmux_cmd" show-option -gqv @autosave-enabled >/dev/null 2>&1; then
		exit 0
	fi

	refresh_label
	if [ "$(get_opt @autosave-enabled 1)" = "1" ] && [ -f "$save_script" ]; then
		"$save_script" quiet >/dev/null 2>&1 || true
	fi
done
