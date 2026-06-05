#!/usr/bin/env bash
set -euo pipefail

TARGET="$HOME/.local/tmux"
MIN_VERSION="3.3"

ok()   { echo "[OK] $*"; }
err()  { echo "[ERR] $*"; }
info() { echo "     $*"; }

# ── dependency check ──────────────────────────────────────────────

check_deps() {
	local missing=()

	for cmd in git make gcc; do
		command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
	done

	if ! command -v autoconf >/dev/null 2>&1 && ! command -v autoreconf >/dev/null 2>&1; then
		missing+=("autoconf")
	fi

	if ! command -v pkg-config >/dev/null 2>&1 && ! command -v pkgconf >/dev/null 2>&1; then
		missing+=("pkg-config")
	fi

	if ! pkg-config --exists libevent 2>/dev/null \
		&& ! pkg-config --exists libevent_core 2>/dev/null \
		&& [ ! -f /usr/include/event.h ]; then
		missing+=("libevent-devel")
	fi

	if ! pkg-config --exists ncurses 2>/dev/null \
		&& ! pkg-config --exists ncursesw 2>/dev/null \
		&& [ ! -f /usr/include/ncurses.h ]; then
		missing+=("ncurses-devel")
	fi

	if ! command -v bison >/dev/null 2>&1 \
		&& ! command -v byacc >/dev/null 2>&1 \
		&& ! command -v yacc >/dev/null 2>&1; then
		missing+=("bison")
	fi

	if [ ${#missing[@]} -gt 0 ]; then
		err "Missing build dependencies: ${missing[*]}"
		echo
		echo "Install with your package manager, e.g.:"
		echo "  dnf install ${missing[*]}"
		echo "  apt install ${missing[*]}"
		return 1
	fi
}

# ── version helpers ───────────────────────────────────────────────

current_version() {
	if [ -x "$TARGET/bin/tmux" ]; then
		"$TARGET/bin/tmux" -V 2>&1 | grep -oP '[\d]+\.[\d]+[^\s]*' || true
	elif command -v tmux >/dev/null 2>&1; then
		tmux -V 2>&1 | grep -oP '[\d]+\.[\d]+[^\s]*' || true
	else
		echo "none"
	fi
}

ver_ge() {
	printf '%s\n%s\n' "$2" "$1" | sort -V -C 2>/dev/null
}

# ── source management ─────────────────────────────────────────────

update_source() {
	if [ -d "$TARGET/.git" ]; then
		echo "==> Fetching latest tmux tags..."
		git -C "$TARGET" fetch --tags --depth=1 origin
	elif [ -d "$TARGET" ]; then
		err "ERROR: $TARGET exists but is not a tmux git repo."
		echo "Remove it manually and retry:  rm -rf $TARGET"
		return 1
	else
		echo "==> Cloning tmux source (shallow)..."
		git clone --depth=1 --branch master https://github.com/tmux/tmux.git "$TARGET"
		echo "==> Fetching tags..."
		git -C "$TARGET" fetch --tags --depth=1 origin
	fi
}

latest_stable_tag() {
	git -C "$TARGET" tag -l '[0-9]*.[0-9]*' \
		| grep -v 'rc\|beta\|alpha' \
		| sort -V \
		| tail -1
}

# ── build & install ───────────────────────────────────────────────

build_install() {
	local tag="${1:-}"
	if [ -z "$tag" ]; then
		tag="$(latest_stable_tag)"
	fi

	if [ -z "$tag" ]; then
		echo "No stable release tag found, using master..."
		tag="master"
	fi

	local cur
	cur="$(current_version)"

	echo "Current tmux : $cur"
	echo "Target       : $tag"
	echo "Prefix       : $TARGET"
	echo

	cd "$TARGET"
	git checkout -q "$tag"

	echo "==> Running autogen.sh..."
	sh autogen.sh

	echo "==> Running ./configure --prefix=$TARGET"
	./configure --prefix="$TARGET"

	local ncpu
	ncpu="$(nproc 2>/dev/null || echo 4)"
	echo "==> Running make -j$ncpu"
	make -j"$ncpu"

	echo "==> Running make install"
	make install

	ok "Done — $("$TARGET/bin/tmux" -V 2>&1) installed to $TARGET/bin"
}

# ── path check ────────────────────────────────────────────────────

check_path() {
	local first_tmux
	first_tmux="$(command -v tmux 2>/dev/null || true)"
	if [ "$first_tmux" != "$TARGET/bin/tmux" ]; then
		echo
		info "NOTE: $TARGET/bin is not first in PATH."
		info "Add this to your shell rc:  export PATH=\"\$HOME/.local/tmux/bin:\$PATH\""
		info "Then restart tmux."
	fi
}

# ── main ──────────────────────────────────────────────────────────

echo "=== tmux updater ==="
echo

# turn off early-exit so the popup always stays open for review
set +e
check_deps  && \
update_source && \
build_install "$@" && \
check_path
rc=$?
set -e

if [ $rc -ne 0 ]; then
	echo
	err "Build failed (exit code $rc). See output above."
fi
