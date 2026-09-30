#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
grant_temp_sudo.py - Grant a user temporary sudo privileges, automatically
revoked on expiry by a systemd timer.

Usage:
  sudo ./grant_temp_sudo.py -u alice -d 2h
  sudo ./grant_temp_sudo.py --user alice --duration "1 week 2 days"
  sudo ./grant_temp_sudo.py -u alice -d 1w --nopasswd
  sudo ./grant_temp_sudo.py -u alice -d 30m --force     # replace / extend an existing grant
  sudo ./grant_temp_sudo.py -r -u alice                 # revoke immediately
  sudo ./grant_temp_sudo.py -l                          # list all temporary grants

Design notes:
  * All state is named by UID: /etc/sudoers.d/temp_sudo_u<UID>
                               /etc/systemd/system/temp-sudo-u<UID>.{timer,service}
    This avoids sudo's includedir silently ignoring file names that contain '.'
    (e.g. user "john.doe") and removes any need to escape unit names.
  * The revoke timer is installed and started BEFORE the sudoers rule is
    atomically moved into place (fail-closed): if any step fails or is
    interrupted, we never end up with a privilege that nothing will revoke.
  * The timer uses both OnCalendar (wall clock, Persistent) and OnActiveSec
    (monotonic clock); whichever fires first wins. An expiry missed while the
    machine was off fires right after boot; a clock set backwards is covered
    by the monotonic trigger.
"""

import argparse
import fcntl
import grp
import math
import os
import pwd
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

SUDOERS_DIR = Path("/etc/sudoers.d")
UNIT_DIR = Path("/etc/systemd/system")
LOCK_FILE = Path("/run/lock/grant_temp_sudo.lock")
MANAGED_TAG = "managed-by: grant_temp_sudo.py"

MIN_SECONDS = 1
MAX_SECONDS = 52 * 7 * 86400  # 52-week cap, so a typo can't create an effectively permanent grant

UNIT_SECONDS = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}
UNIT_ALIASES = {
    alias: canon
    for canon, aliases in {
        "s": ("s", "sec", "secs", "second", "seconds"),
        "m": ("m", "min", "mins", "minute", "minutes"),
        "h": ("h", "hr", "hrs", "hour", "hours"),
        "d": ("d", "day", "days"),
        "w": ("w", "wk", "wks", "week", "weeks"),
    }.items()
    for alias in aliases
}
UNIT_LABELS = (("w", "week"), ("d", "day"), ("h", "hour"), ("m", "minute"), ("s", "second"))

# One segment: number + optional whitespace + unit word + optional comma
_TOKEN_RE = re.compile(r"\s*(\d+)\s*([a-z]+)\s*,?")
# Conservative user name rule: no leading '-' (could be mistaken for an option),
# no whitespace, quotes, newlines, etc.
_USER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,31}")

SYSTEMCTL = VISUDO = RM = ""  # resolved to absolute paths in check_env()


# ---------------------------------------------------------------- output helpers

def info(msg):
    print(msg, flush=True)


def warn(msg):
    print(f"WARNING: {msg}", file=sys.stderr, flush=True)


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr, flush=True)
    raise SystemExit(code)


# ---------------------------------------------------------------- duration parsing

def parse_duration(text):
    """Parse a duration into seconds. Combined forms are supported,
    e.g. '1w2d', '1h30m', "1 week, 2 days"."""
    s = text.strip().lower()
    if not s:
        raise ValueError("duration must not be empty")

    total, pos, seen = 0, 0, set()
    while pos < len(s):
        m = _TOKEN_RE.match(s, pos)
        if not m:
            raise ValueError(
                f"cannot parse duration '{text}' (near character {pos + 1}). "
                "Examples: 30s, 5m, 2h, 1d, 1w, 1w2d, \"1 week 2 days\""
            )
        n, word = int(m.group(1)), m.group(2)
        canon = UNIT_ALIASES.get(word)
        if canon is None:
            raise ValueError(f"unknown time unit '{word}'")
        if canon in seen:
            raise ValueError(f"duplicate time unit '{word}'")
        seen.add(canon)
        total += n * UNIT_SECONDS[canon]
        pos = m.end()

    if total < MIN_SECONDS:
        raise ValueError("duration must be greater than 0")
    if total > MAX_SECONDS:
        raise ValueError(f"duration exceeds the maximum of {format_duration(MAX_SECONDS)}")
    return total


def format_duration(sec):
    parts = []
    for unit, label in UNIT_LABELS:
        q, sec = divmod(sec, UNIT_SECONDS[unit])
        if q:
            parts.append(f"{q} {label}{'s' if q != 1 else ''}")
    return ", ".join(parts) or "0 seconds"


def duration_type(value):
    try:
        return parse_duration(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))


def username_type(value):
    if not _USER_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            f"invalid user name '{value}' (allowed: letters, digits, _ . -; "
            "must not start with '-'; max 32 characters)"
        )
    return value


# ---------------------------------------------------------------- system helpers

def run(cmd, check=True):
    return subprocess.run(
        cmd, check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        universal_newlines=True,
    )


def silent_unlink(path):
    try:
        os.unlink(str(path))
        return True
    except FileNotFoundError:
        return False


def fsync_dir(path):
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_temp(directory, name, content, mode):
    """Write a temp file in the target directory, fsync it, and return its path.
    The name starts with '.' and contains '.', so both sudo's includedir and
    systemd ignore it."""
    fd, tmp = tempfile.mkstemp(dir=str(directory), prefix=f".{name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
            f.flush()
            os.fchmod(f.fileno(), mode)
            os.fsync(f.fileno())
    except BaseException:
        silent_unlink(tmp)
        raise
    return tmp


def atomic_write(path, content, mode):
    tmp = write_temp(path.parent, path.name, content, mode)
    try:
        os.replace(tmp, str(path))
    except BaseException:
        silent_unlink(tmp)
        raise
    fsync_dir(path.parent)


def check_env():
    global SYSTEMCTL, VISUDO, RM
    if os.geteuid() != 0:
        die("must be run as root.")
    if not Path("/run/systemd/system").is_dir():
        die("this system was not booted with systemd; systemd timers are unavailable.")
    tools = {}
    for name in ("systemctl", "visudo", "rm"):
        tools[name] = shutil.which(name)
        if not tools[name]:
            die(f"command '{name}' not found.")
    SYSTEMCTL, VISUDO, RM = tools["systemctl"], tools["visudo"], tools["rm"]

    if not SUDOERS_DIR.is_dir():
        die(f"directory {SUDOERS_DIR} does not exist.")
    try:
        sudoers = Path("/etc/sudoers").read_text()
        if not re.search(r"^\s*[@#]includedir\s+/etc/sudoers\.d\s*$", sudoers, re.M):
            warn("no 'includedir /etc/sudoers.d' found in /etc/sudoers; the grant may not take effect.")
    except OSError:
        pass


def acquire_lock():
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    f = open(str(LOCK_FILE), "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        die("another instance is already running; please retry later.")
    return f  # keep a reference; the lock is released when the process exits


def _on_signal(signum, _frame):
    # Turn SIGTERM / SIGHUP into SystemExit so grant()'s rollback runs
    raise SystemExit(128 + signum)


# ---------------------------------------------------------------- grant object

class Grant:
    def __init__(self, uid, user):
        self.uid = uid
        self.user = user
        base = f"temp-sudo-u{uid}"
        self.sudoers = SUDOERS_DIR / f"temp_sudo_u{uid}"
        self.timer_name = f"{base}.timer"
        self.service_name = f"{base}.service"
        self.timer_path = UNIT_DIR / self.timer_name
        self.service_path = UNIT_DIR / self.service_name

    def exists(self):
        return any(p.exists() for p in (self.sudoers, self.timer_path, self.service_path))


def read_meta(path):
    meta = {}
    try:
        for line in path.read_text().splitlines():
            m = re.match(r"#\s*(\w+):\s*(.*)$", line)
            if m:
                meta[m.group(1)] = m.group(2).strip()
    except OSError:
        pass
    return meta


def scan_grants():
    """Return {uid: meta}, including orphaned records where only unit files remain."""
    found = {}
    for p in SUDOERS_DIR.glob("temp_sudo_u*"):
        m = re.fullmatch(r"temp_sudo_u(\d+)", p.name)
        if m:
            found[int(m.group(1))] = read_meta(p)
    for p in UNIT_DIR.glob("temp-sudo-u*.timer"):
        m = re.fullmatch(r"temp-sudo-u(\d+)\.timer", p.name)
        if m:
            found.setdefault(int(m.group(1)), {"orphan": "yes"})
    return found


def resolve_grant(user):
    try:
        return Grant(pwd.getpwnam(user).pw_uid, user)
    except KeyError:
        # The account may have been deleted; look it up by the recorded user name
        for uid, meta in scan_grants().items():
            if meta.get("user") == user:
                return Grant(uid, user)
    die(f"user '{user}' does not exist and no matching temporary grant was found.")


def service_triggered(g):
    """Has the revoke service already run (or started running)?"""
    if not g.service_path.exists():
        return True
    r = run([SYSTEMCTL, "show", "-p", "InactiveExitTimestampMonotonic", "--value",
             g.service_name], check=False)
    return r.stdout.strip() not in ("", "0")


# ---------------------------------------------------------------- unit files

def render_service(g):
    return f"""\
# {MANAGED_TAG}
[Unit]
Description=Revoke temporary sudo for {g.user} (uid {g.uid})

[Service]
Type=oneshot
# Removing the rule always comes first; failures in the cleanup steps below
# ('-' prefix) do not affect the revocation itself
ExecStart={RM} -f {g.sudoers}
ExecStartPost=-{SYSTEMCTL} disable --no-reload {g.timer_name}
ExecStartPost=-{RM} -f {g.timer_path} {g.service_path}
ExecStartPost=-{SYSTEMCTL} daemon-reload
"""


def render_timer(g, exp_utc, seconds):
    return f"""\
# {MANAGED_TAG}
[Unit]
Description=Expire temporary sudo for {g.user} (uid {g.uid})

[Timer]
# Wall clock: absolute expiry. Persistent=true makes an expiry missed while
# the machine was off fire immediately after the next boot
OnCalendar={exp_utc:%Y-%m-%d %H:%M:%S} UTC
Persistent=true
# Monotonic fallback: even if the system clock is set backwards, revoke no
# later than {seconds}s after the timer was started
OnActiveSec={seconds}s
AccuracySec=1s
Unit={g.service_name}

[Install]
WantedBy=timers.target
"""


def render_sudoers(g, nopasswd, now, exp_epoch):
    iso = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tag = "NOPASSWD: " if nopasswd else ""
    return (
        f"# {MANAGED_TAG}\n"
        f"# user: {g.user}\n"
        f"# uid: {g.uid}\n"
        f"# granted: {iso(now)}\n"
        f"# expires: {iso(exp_epoch)}\n"
        f"# expires_epoch: {exp_epoch}\n"
        f"# nopasswd: {'yes' if nopasswd else 'no'}\n"
        f"{g.user} ALL=(ALL:ALL) {tag}ALL\n"
    )


# ---------------------------------------------------------------- actions

def revoke(g):
    """Idempotent revoke: remove the rule first, then clean up the timer.
    Never raises on individual step failures."""
    removed_rule = silent_unlink(g.sudoers)
    run([SYSTEMCTL, "disable", "--now", g.timer_name], check=False)
    removed_units = [silent_unlink(p) for p in (g.timer_path, g.service_path)]
    run([SYSTEMCTL, "daemon-reload"], check=False)
    run([SYSTEMCTL, "reset-failed", g.timer_name, g.service_name], check=False)
    return removed_rule or any(removed_units)


def warn_permanent_sudo(user, pw):
    groups = {gr.gr_name for gr in grp.getgrall() if user in gr.gr_mem}
    try:
        groups.add(grp.getgrgid(pw.pw_gid).gr_name)
    except KeyError:
        pass
    hit = groups & {"sudo", "wheel", "admin"}
    if hit:
        warn(f"user is already in group(s) {', '.join(sorted(hit))}; "
             "they will keep sudo access after this temporary grant expires.")


def grant(user, seconds, nopasswd, force):
    try:
        pw = pwd.getpwnam(user)
    except KeyError:
        die(f"user '{user}' does not exist.")
    if pw.pw_uid == 0:
        die("UID 0 does not need a sudo grant.")

    g = Grant(pw.pw_uid, user)
    if g.exists():
        if not force:
            die(f"'{user}' already has a temporary grant. "
                "Use --force to replace/extend it, or --revoke to remove it.")
        info("--force: revoking the existing grant first...")
        revoke(g)

    warn_permanent_sudo(user, pw)

    now = time.time()
    exp_epoch = math.ceil(now + seconds)
    exp_utc = datetime.fromtimestamp(exp_epoch, timezone.utc)

    info("------------------------------------------------")
    info(f"Configuring temporary sudo for [{user}] (uid {g.uid})...")
    info(f"Duration: {format_duration(seconds)}")

    tmp_sudoers = None
    try:
        # 1. Write the rule to a temp file (ignored by sudo) and validate it
        tmp_sudoers = write_temp(SUDOERS_DIR, "temp_sudo",
                                 render_sudoers(g, nopasswd, now, exp_epoch), 0o440)
        r = run([VISUDO, "-cf", tmp_sudoers], check=False)
        if r.returncode != 0:
            die(f"sudoers syntax check failed:\n{r.stdout}{r.stderr}")

        # 2. Install and start the revoke timer first - no privilege granted yet
        atomic_write(g.service_path, render_service(g), 0o644)
        atomic_write(g.timer_path, render_timer(g, exp_utc, seconds), 0o644)
        run([SYSTEMCTL, "daemon-reload"])
        run([SYSTEMCTL, "enable", "--now", g.timer_name])

        # 3. Atomically move the rule into place; the privilege takes effect now
        os.replace(tmp_sudoers, str(g.sudoers))
        tmp_sudoers = None
        fsync_dir(SUDOERS_DIR)

        # 4. Race check: with very short durations the timer may have fired
        #    before the rule was in place
        if time.time() >= exp_epoch or service_triggered(g):
            die("expiry already reached or revoke job already fired; "
                "rolled back, no privilege was granted.")
    except BaseException:
        if tmp_sudoers:
            silent_unlink(tmp_sudoers)
        revoke(g)
        raise

    local_exp = datetime.fromtimestamp(exp_epoch).astimezone()
    info(f"Success! Privilege will be revoked automatically at {local_exp:%Y-%m-%d %H:%M:%S %Z}.")
    info(f"Rule file: {g.sudoers}")
    info(f"Timer:     {g.timer_name} (systemctl list-timers {g.timer_name})")
    info("------------------------------------------------")


def list_grants():
    grants = scan_grants()
    if not grants:
        info("No temporary sudo grants.")
        return
    now = time.time()
    for uid, meta in sorted(grants.items()):
        g = Grant(uid, meta.get("user", "?"))
        state = run([SYSTEMCTL, "is-active", g.timer_name], check=False).stdout.strip()
        if meta.get("orphan"):
            info(f"* uid {uid}: timer only, no rule file (timer: {state}); "
                 "clean up with --revoke")
            continue
        try:
            exp = int(meta["expires_epoch"])
            left = format_duration(max(0, exp - int(now)))
            when = f"{datetime.fromtimestamp(exp).astimezone():%Y-%m-%d %H:%M:%S %Z} ({left} left)"
        except (KeyError, ValueError):
            when = "unknown"
        flag = "" if state == "active" else "  WARNING: timer not running!"
        pw_flag = ", NOPASSWD" if meta.get("nopasswd") == "yes" else ""
        info(f"* {g.user} (uid {uid}{pw_flag}): expires {when}, timer: {state}{flag}")


# ---------------------------------------------------------------- entry point

def build_parser():
    p = argparse.ArgumentParser(
        description="Grant a user temporary sudo privileges, revoked automatically by a systemd timer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,  # reject prefix abbreviations like --dur to avoid ambiguity
        epilog=(
            "Duration formats (combinable, case-insensitive):\n"
            "  30s  5m  2h  1d  1w  5min  2hours  3weeks\n"
            "  1w2d  1h30m  \"1 week 2 days\"  \"1h, 30m\"\n\n"
            "Examples:\n"
            "  %(prog)s -u alice -d 2h\n"
            "  %(prog)s --user alice --duration \"1 week\" --nopasswd\n"
            "  %(prog)s -r -u alice\n"
            "  %(prog)s -l"
        ),
    )
    p.add_argument("-u", "--user", type=username_type, metavar="USER", help="target user name")
    p.add_argument("-d", "--duration", type=duration_type, metavar="DURATION",
                   help="grant duration, e.g. 2h / 1w / \"1 week 2 days\"")
    p.add_argument("-n", "--nopasswd", action="store_true",
                   help="grant passwordless sudo (default: password required)")
    p.add_argument("-f", "--force", action="store_true",
                   help="if a grant already exists, revoke it and grant again (extend)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("-r", "--revoke", action="store_true",
                      help="immediately revoke the user's temporary grant")
    mode.add_argument("-l", "--list", action="store_true", help="list all temporary grants")
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    # Validate argument combinations before touching the system
    if args.list:
        if args.user or args.duration is not None or args.nopasswd or args.force:
            parser.error("--list cannot be combined with other options")
    elif args.revoke:
        if not args.user:
            parser.error("--revoke requires --user")
        if args.duration is not None or args.nopasswd or args.force:
            parser.error("--revoke only accepts --user")
    else:
        if not args.user or args.duration is None:
            parser.error("granting requires both --user and --duration")

    check_env()
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, _on_signal)
    _lock = acquire_lock()  # noqa: F841

    try:
        if args.list:
            list_grants()
        elif args.revoke:
            g = resolve_grant(args.user)
            if revoke(g):
                info(f"Revoked temporary sudo for [{args.user}].")
            else:
                info(f"[{args.user}] has no temporary grant; nothing to revoke.")
        else:
            grant(args.user, args.duration, args.nopasswd, args.force)
    except subprocess.CalledProcessError as e:
        die(f"command failed: {' '.join(e.cmd)}\n{e.stderr or ''}")


if __name__ == "__main__":
    main()
