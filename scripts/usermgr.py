#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
usermgr.py - one entry point for local Linux account CRUD on lab / shared hosts.

It is a thin, auditable wrapper around the standard shadow-utils tools
(useradd / usermod / userdel / chpasswd / chage / gpasswd / groupadd /
groupmod / groupdel / visudo / systemctl), plus the site
conventions this repo used to spread across several shell scripts:

  create-user.sh       -> usermgr.py create
  lock-user.sh         -> usermgr.py lock
  unlock-user.sh       -> usermgr.py unlock
  change-user-home.sh  -> usermgr.py move-home
  grant-temp-root.py   -> usermgr.py sudo grant|revoke|list   (merged in)

Usage:
  sudo ./usermgr.py create alice                     # random password, printed once
  sudo ./usermgr.py create bob -G docker,video --password-stdin < pass.txt
  sudo ./usermgr.py create dave -p 'S3cret-Initial'   # explicit (visible in ps/history)
  sudo ./usermgr.py create carol --no-password       # key-only login
  ./usermgr.py list                                  # human accounts (UID_MIN..UID_MAX)
  ./usermgr.py show alice
  sudo ./usermgr.py modify alice --shell /bin/zsh --add-groups docker
  sudo ./usermgr.py modify alice --primary-group lab --set-groups docker,video
  sudo ./usermgr.py group create lab [--gid 2000]
  ./usermgr.py group list [--all]                    # groups in GID_MIN..GID_MAX + members
  ./usermgr.py group show docker
  sudo ./usermgr.py group add-member docker alice bob
  sudo ./usermgr.py group remove-member docker bob
  sudo ./usermgr.py group rename lab lab2
  sudo ./usermgr.py group delete lab2
  sudo ./usermgr.py passwd alice                     # new random password
  sudo ./usermgr.py lock alice                       # also kills sessions, blocks SSH keys
  sudo ./usermgr.py unlock alice                     # restores shell / expiry saved by lock
  sudo ./usermgr.py move-home alice                  # -> /mnt/data1/users/alice, /home/alice symlink
  sudo ./usermgr.py move-home alice --to /data/alice --no-link
  sudo ./usermgr.py delete alice --remove-home --kill
  sudo ./usermgr.py sudo grant alice 2h [--nopasswd] [--force]   # auto-revoked by a systemd timer
  sudo ./usermgr.py sudo grant alice "1 week 2 days"
  sudo ./usermgr.py sudo revoke alice
  sudo ./usermgr.py sudo list

Every mutating command accepts --dry-run (global flag, before the subcommand)
and then only prints the commands it would run; --dry-run does not need root.
"""

import argparse
import fcntl
import json
import math
import os
import pwd
import grp
import re
import random
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import warnings
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    import secrets
except ImportError:  # Python < 3.6
    secrets = None

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_DIR = Path("/var/lib/usermgr/locked")
SUDOERS_DIR = Path("/etc/sudoers.d")
LOGIN_DEFS = Path("/etc/login.defs")

DEFAULT_SHELL = "/bin/bash"
DEFAULT_HOME_BASE = "/mnt/data1/users"  # site convention from change-user-home.sh
LINK_ROOT = Path("/home")

# Conservative name rule: no leading '-' (could be mistaken for an option),
# no whitespace, quotes, newlines, etc.
_USER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,31}")


# ---------------------------------------------------------------- output helpers

def info(msg):
    print(msg, flush=True)


def warn(msg):
    print(f"WARNING: {msg}", file=sys.stderr, flush=True)


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr, flush=True)
    raise SystemExit(code)


# ---------------------------------------------------------------- command runner

class Runner:
    """Runs argv lists; in dry-run mode only prints them. stdin is never echoed."""

    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.history = []  # argv lists, for tests

    def run(self, argv, *, stdin=None, check=True, quiet=False, secret=None):
        """`secret` is an argv index whose value is masked in all output."""
        argv = [str(a) for a in argv]
        self.history.append(argv)
        display = list(argv)
        if secret is not None:
            display[secret] = "[redacted]"
        shown = shlex.join(display) + (" <<< [redacted]" if stdin is not None else "")
        if self.dry_run:
            info(f"[dry-run] {shown}")
            return subprocess.CompletedProcess(argv, 0, "", "")
        if not quiet:
            info(f"+ {shown}")
        r = subprocess.run(argv, input=stdin, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, universal_newlines=True)
        if check and r.returncode != 0:
            die(f"command failed ({r.returncode}): {shown}\n{r.stderr.strip()}")
        return r

    # filesystem side effects go through here too so --dry-run stays honest
    def symlink(self, target, link):
        self.history.append(["ln", "-s", str(target), str(link)])
        if self.dry_run:
            info(f"[dry-run] ln -s {shlex.quote(str(target))} {shlex.quote(str(link))}")
            return
        info(f"+ ln -s {target} {link}")
        os.symlink(str(target), str(link))

    def unlink(self, path):
        self.history.append(["unlink", str(path)])
        if self.dry_run:
            info(f"[dry-run] unlink {shlex.quote(str(path))}")
            return
        info(f"+ unlink {path}")
        os.unlink(str(path))

    def mkdir(self, path):
        self.history.append(["mkdir", "-p", str(path)])
        if self.dry_run:
            info(f"[dry-run] mkdir -p {shlex.quote(str(path))}")
            return
        Path(path).mkdir(parents=True, exist_ok=True)

    def write_state(self, path, data):
        self.history.append(["write", str(path)])
        if self.dry_run:
            info(f"[dry-run] save state -> {path}: {json.dumps(data)}")
            return
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n")
        os.chmod(str(tmp), 0o600)
        os.replace(str(tmp), str(path))

    def remove_state(self, path):
        if not path.exists():
            return
        self.history.append(["rm", str(path)])
        if self.dry_run:
            info(f"[dry-run] rm {path}")
            return
        path.unlink()


# ---------------------------------------------------------------- lookups

def username_type(value):
    if not _USER_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            f"invalid user name '{value}' (letters, digits, _ . -; "
            "must not start with '-'; max 32 characters)")
    return value


def groups_type(value):
    groups = [g for g in (s.strip() for s in value.split(",")) if g]
    for g in groups:
        if not _USER_RE.fullmatch(g):
            raise argparse.ArgumentTypeError(f"invalid group name '{g}'")
    return groups


def get_user(name):
    try:
        return pwd.getpwnam(name)
    except KeyError:
        die(f"user '{name}' does not exist.")


def login_defs():
    vals = {"UID_MIN": 1000, "UID_MAX": 60000, "GID_MIN": 1000, "GID_MAX": 60000}
    try:
        for line in LOGIN_DEFS.read_text().splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] in vals and parts[1].isdigit():
                vals[parts[0]] = int(parts[1])
    except OSError:
        pass
    return vals


def is_regular_user(pw):
    d = login_defs()
    return d["UID_MIN"] <= pw.pw_uid <= d["UID_MAX"]


def guard_regular(pw, force):
    if pw.pw_uid == 0:
        die("refusing to operate on a UID 0 account.")
    if not is_regular_user(pw) and not force:
        die(f"'{pw.pw_name}' (uid {pw.pw_uid}) looks like a system account; "
            "pass --force if you really mean it.")


def user_groups(name, primary_gid):
    names = {g.gr_name for g in grp.getgrall() if name in g.gr_mem}
    try:
        names.add(grp.getgrgid(primary_gid).gr_name)
    except KeyError:
        pass
    return sorted(names)


def get_group(name):
    try:
        return grp.getgrnam(name)
    except KeyError:
        die(f"group '{name}' does not exist.")


def is_regular_group(gr):
    d = login_defs()
    return d["GID_MIN"] <= gr.gr_gid <= d["GID_MAX"]


def guard_regular_group(gr, force):
    if gr.gr_gid == 0:
        die("refusing to operate on the GID 0 group.")
    if not is_regular_group(gr) and not force:
        die(f"'{gr.gr_name}' (gid {gr.gr_gid}) looks like a system group; "
            "pass --force if you really mean it.")


def primary_users(gid):
    """Users whose primary group is gid (these are not listed in gr_mem)."""
    return sorted(pw.pw_name for pw in pwd.getpwall() if pw.pw_gid == gid)


def group_members(gr):
    """(supplementary members, primary-group users) of a group."""
    return sorted(gr.gr_mem), primary_users(gr.gr_gid)


PRIVILEGED_GROUPS = {"root", "sudo", "wheel", "admin"}
# Membership in these is effectively root; warn so it is a conscious choice.
ROOT_EQUIVALENT_GROUPS = PRIVILEGED_GROUPS | {"docker", "lxd", "libvirt", "disk"}


def warn_privileged(groups):
    hit = sorted(set(groups) & ROOT_EQUIVALENT_GROUPS)
    if hit:
        warn(f"group(s) {', '.join(hit)} grant root-equivalent access permanently; "
             "for time-boxed admin rights use `usermgr.py sudo grant`.")


def shadow_entry(name):
    """Return the /etc/shadow fields for name, or None if unreadable."""
    try:
        with open("/etc/shadow") as f:
            for line in f:
                fields = line.rstrip("\n").split(":")
                if fields and fields[0] == name:
                    return fields
    except OSError:
        return None
    return None


def is_locked(name):
    sh = shadow_entry(name)
    if sh is None or len(sh) < 2:
        return None
    return sh[1].startswith("!")


def state_path(name):
    return STATE_DIR / f"{name}.json"


PASSWORD_LENGTH = 20
MIN_PASSWORD_LENGTH = 12
# No look-alike characters (0/O, 1/l/I) and no shell-hostile symbols, so the
# printed password can be read aloud or retyped without mistakes.
_PW_CLASSES = ("abcdefghijkmnopqrstuvwxyz", "ABCDEFGHJKLMNPQRSTUVWXYZ",
               "23456789", "%+-=@_")


def _csprng():
    """Return a random.Random-like object backed by the OS CSPRNG.

    Prefer the `secrets` module; fall back to random.SystemRandom (os.urandom).
    Never fall back to the default Mersenne Twister, which is not secure.
    """
    if secrets is not None:
        return secrets.SystemRandom()
    try:
        return random.SystemRandom()
    except NotImplementedError:
        die("no secure random source available (os.urandom is not implemented).")


def gen_password(length=PASSWORD_LENGTH):
    """Generate a random password containing at least one char of every class,
    so it satisfies common pam_pwquality rules (minclass / dcredit / ...)."""
    rng = _csprng()
    alphabet = "".join(_PW_CLASSES)
    chars = [rng.choice(c) for c in _PW_CLASSES]
    chars += [rng.choice(alphabet) for _ in range(length - len(chars))]
    rng.shuffle(chars)
    return "".join(chars)


def password_length_type(value):
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid length '{value}'")
    if not MIN_PASSWORD_LENGTH <= n <= 128:
        raise argparse.ArgumentTypeError(
            f"length must be between {MIN_PASSWORD_LENGTH} and 128")
    return n


def check_password(password):
    if not password:
        die("password must not be empty.")
    if "\n" in password or "\r" in password or "\0" in password:
        die("password must not contain newlines or NUL bytes.")
    return password


def has_processes(r, name):
    if r.dry_run:
        return False
    res = subprocess.run(["pgrep", "-u", name], stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL)
    return res.returncode == 0


def kill_user(r, name):
    # -u matches the effective UID exactly (the old `ps | grep $user` matched substrings)
    if shutil.which("loginctl"):
        r.run(["loginctl", "terminate-user", name], check=False, quiet=True)
    r.run(["pkill", "-KILL", "-u", name], check=False)


def _hash_password(r, password):
    """Return a SHA-512 crypt(3) hash, or None if no hashing backend exists.

    Backends in order: `openssl passwd -6` (password via stdin, never argv),
    then Python's `crypt` module (removed in Python 3.13).
    """
    if shutil.which("openssl"):
        res = r.run(["openssl", "passwd", "-6", "-stdin"], stdin=password + "\n",
                    check=False, quiet=True)
        if r.dry_run:
            return "<sha512-hash>"
        if res.returncode == 0 and res.stdout.startswith("$6$"):
            return res.stdout.strip()
        warn("openssl passwd -6 failed; trying the next backend.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            import crypt  # deprecated in 3.11, removed in 3.13
    except ImportError:
        return None
    return crypt.crypt(password, crypt.mksalt(crypt.METHOD_SHA512))


def apply_password(r, name, password):
    """Set name's password, picking the first available backend.

    1. chpasswd                (reads "user:pass" from stdin; nothing in `ps`)
    2. openssl / crypt + usermod -p   (the hash is briefly visible in `ps`)
    """
    if shutil.which("chpasswd"):
        r.run(["chpasswd"], stdin=f"{name}:{password}\n")
        return
    warn("chpasswd not found; falling back to usermod -p with a local hash.")
    hashed = _hash_password(r, password)
    if hashed is None:
        die("cannot set a password: none of chpasswd, openssl or Python crypt is available.")
    r.run(["usermod", "-p", hashed, name], secret=2)


def resolve_password(args):
    """Return (password, source) where source is 'given' | 'random' | 'none'."""
    if getattr(args, "no_password", False):
        return None, "none"
    if getattr(args, "password", None) is not None:
        warn("a password given on the command line is visible in `ps` and shell "
             "history; prefer --password-stdin.")
        return check_password(args.password), "given"
    if getattr(args, "password_stdin", False):
        if sys.stdin.isatty():
            import getpass
            pw1 = getpass.getpass("New password: ")
            if getpass.getpass("Retype new password: ") != pw1:
                die("passwords do not match.")
        else:
            pw1 = sys.stdin.readline().rstrip("\r\n")
        return check_password(pw1), "given"
    return gen_password(args.password_length), "random"


def set_password(r, name, resolved, force_change=True):
    """Apply a (password, source) pair returned by resolve_password()."""
    password, source = resolved
    if source == "none":
        r.run(["usermod", "-p", "!", name])  # no usable password, key-only login
        return
    apply_password(r, name, password)
    if force_change:
        r.run(["chage", "-d", "0", name])
    when = "must be changed at next login" if force_change else "no forced change"
    if source == "random" and r.dry_run:
        info(f"Password for {name}: <generated at run time>  ({when})")
    elif source == "random":
        # Printed exactly once; it is not stored anywhere.
        info(f"Password for {name}: {password}  ({when})")
    else:
        info(f"Password for {name} set as given ({when}).")


# ================================================================ temporary sudo
#
# Merged from the former scripts/grant-temp-root.py; behaviour and on-disk
# layout are unchanged, so grants created by the old script are still seen.
#
#  * All state is named by UID: /etc/sudoers.d/temp_sudo_u<UID>
#                               /etc/systemd/system/temp-sudo-u<UID>.{timer,service}
#    This avoids sudo's includedir silently ignoring file names that contain '.'
#    (e.g. user "john.doe") and removes any need to escape unit names.
#  * The revoke timer is installed and started BEFORE the sudoers rule is
#    atomically moved into place (fail-closed): if any step fails or is
#    interrupted, we never end up with a privilege that nothing will revoke.
#  * The timer uses both OnCalendar (wall clock, Persistent) and OnActiveSec
#    (monotonic clock); whichever fires first wins. An expiry missed while the
#    machine was off fires right after boot; a clock set backwards is covered
#    by the monotonic trigger.

UNIT_DIR = Path("/etc/systemd/system")
# Lock path and tag keep their historical names so existing grants are still
# recognised and a leftover copy of the old script cannot race with us.
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
SYSTEMCTL = VISUDO = RM = ""  # resolved to absolute paths in check_env()


# ------------------------------------------------ temp sudo: duration parsing

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


# ------------------------------------------------ temp sudo: system helpers

def _sys(cmd, check=True):
    """Run a command quietly, capturing output (temp-sudo internals)."""
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


def resolve_sudo_tools():
    """Resolve systemctl / visudo / rm to absolute paths; return the missing names."""
    global SYSTEMCTL, VISUDO, RM
    tools = {name: shutil.which(name) for name in ("systemctl", "visudo", "rm")}
    SYSTEMCTL, VISUDO, RM = (tools[n] or n for n in ("systemctl", "visudo", "rm"))
    return [n for n, path in tools.items() if not path]


def check_env():
    if os.geteuid() != 0:
        die("must be run as root.")
    if not Path("/run/systemd/system").is_dir():
        die("this system was not booted with systemd; systemd timers are unavailable.")
    missing = resolve_sudo_tools()
    if missing:
        die(f"command '{missing[0]}' not found.")

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


# ------------------------------------------------ temp sudo: grant object

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
    r = _sys([SYSTEMCTL, "show", "-p", "InactiveExitTimestampMonotonic", "--value",
             g.service_name], check=False)
    return r.stdout.strip() not in ("", "0")


# ------------------------------------------------ temp sudo: unit files

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


# ------------------------------------------------ temp sudo: actions

def revoke(g):
    """Idempotent revoke: remove the rule first, then clean up the timer.
    Never raises on individual step failures."""
    removed_rule = silent_unlink(g.sudoers)
    _sys([SYSTEMCTL, "disable", "--now", g.timer_name], check=False)
    removed_units = [silent_unlink(p) for p in (g.timer_path, g.service_path)]
    _sys([SYSTEMCTL, "daemon-reload"], check=False)
    _sys([SYSTEMCTL, "reset-failed", g.timer_name, g.service_name], check=False)
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
                "Use `sudo grant ... --force` to replace/extend it, or `sudo revoke` to remove it.")
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
        r = _sys([VISUDO, "-cf", tmp_sudoers], check=False)
        if r.returncode != 0:
            die(f"sudoers syntax check failed:\n{r.stdout}{r.stderr}")

        # 2. Install and start the revoke timer first - no privilege granted yet
        atomic_write(g.service_path, render_service(g), 0o644)
        atomic_write(g.timer_path, render_timer(g, exp_utc, seconds), 0o644)
        _sys([SYSTEMCTL, "daemon-reload"])
        _sys([SYSTEMCTL, "enable", "--now", g.timer_name])

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
        state = _sys([SYSTEMCTL, "is-active", g.timer_name], check=False).stdout.strip()
        if meta.get("orphan"):
            info(f"* uid {uid}: timer only, no rule file (timer: {state}); "
                 "clean up with `usermgr.py sudo revoke`")
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


# ---------------------------------------------------------------- commands

def cmd_create(args, r):
    name = args.user
    try:
        pwd.getpwnam(name)
        die(f"user '{name}' already exists.")
    except KeyError:
        pass

    # Resolve / validate the password before touching the system, so a bad
    # value does not leave a half-created account behind.
    resolved = resolve_password(args)

    argv = ["useradd", "-m", "-s", args.shell]
    home = None
    if args.home:
        home = Path(args.home)
    elif args.home_base:
        home = Path(args.home_base) / name
    if home is not None:
        r.mkdir(home.parent)
        argv += ["-d", str(home)]
    if args.groups:
        for g in args.groups:
            get_group(g)
        warn_privileged(args.groups)
        argv += ["-G", ",".join(args.groups)]
    if args.comment:
        argv += ["-c", args.comment]
    if args.uid is not None:
        argv += ["-u", str(args.uid)]
    if args.expire:
        argv += ["-e", args.expire]
    argv.append(name)
    r.run(argv)

    link = LINK_ROOT / name
    if home is not None and args.link and home != link and not os.path.lexists(str(link)):
        r.symlink(home, link)

    set_password(r, name, resolved, force_change=not args.no_expire)
    info(f"Created user {name}.")


def cmd_list(args, r):
    rows = []
    for pw in sorted(pwd.getpwall(), key=lambda p: p.pw_uid):
        if not args.all and not is_regular_user(pw):
            continue
        locked = is_locked(pw.pw_name)
        lock_s = "?" if locked is None else ("locked" if locked else "")
        rows.append((pw.pw_name, str(pw.pw_uid), pw.pw_dir, pw.pw_shell, lock_s))
    if args.json:
        print(json.dumps([dict(zip(("user", "uid", "home", "shell", "status"), x)) for x in rows],
                         indent=2))
        return
    if not rows:
        info("No matching users.")
        return
    header = ("USER", "UID", "HOME", "SHELL", "STATUS")
    widths = [max(len(h), *(len(row[i]) for row in rows)) for i, h in enumerate(header)]
    for row in (header, *rows):
        print("  ".join(c.ljust(w) for c, w in zip(row, widths)).rstrip())


def cmd_show(args, r):
    pw = get_user(args.user)
    name = pw.pw_name
    link = LINK_ROOT / name
    data = {
        "user": name,
        "uid": pw.pw_uid,
        "gid": pw.pw_gid,
        "comment": pw.pw_gecos,
        "home": pw.pw_dir,
        "home_exists": os.path.isdir(pw.pw_dir),
        "shell": pw.pw_shell,
        "groups": user_groups(name, pw.pw_gid),
        "locked": is_locked(name),
        "home_link": os.readlink(str(link)) if link.is_symlink() else None,
        "lock_state_saved": state_path(name).exists(),
        "temp_sudo": Grant(pw.pw_uid, name).exists(),
    }
    sh = shadow_entry(name)
    if sh and len(sh) >= 8:
        data["account_expire_days"] = sh[7] or None
    if args.json:
        print(json.dumps(data, indent=2))
        return
    for k, v in data.items():
        print(f"{k:18} {v}")
    if os.geteuid() == 0 and shutil.which("chage"):
        print()
        print(subprocess.run(["chage", "-l", name], stdout=subprocess.PIPE,
                             universal_newlines=True).stdout.rstrip())


def cmd_modify(args, r):
    pw = get_user(args.user)
    guard_regular(pw, args.force)
    name = pw.pw_name
    argv = ["usermod"]
    if args.shell:
        argv += ["-s", args.shell]
    if args.comment is not None:
        argv += ["-c", args.comment]
    if args.expire is not None:
        argv += ["-e", args.expire]
    if args.primary_group:
        get_group(args.primary_group)
        argv += ["-g", args.primary_group]
    if args.set_groups is not None:
        # Replace the whole supplementary list ('' clears it)
        for g in args.set_groups:
            get_group(g)
        warn_privileged(args.set_groups)
        argv += ["-G", ",".join(args.set_groups)]
    if args.add_groups:
        for g in args.add_groups:
            get_group(g)
        warn_privileged(args.add_groups)
        argv += ["-a", "-G", ",".join(args.add_groups)]
    if args.rename:
        argv += ["-l", args.rename]
    changed = False
    if len(argv) > 1:
        argv.append(name)
        r.run(argv)
        changed = True
    for g in args.remove_groups or []:
        gr = get_group(g)
        if gr.gr_gid == pw.pw_gid:
            die(f"'{g}' is {name}'s primary group; change it with --primary-group first.")
        if name not in gr.gr_mem:
            warn(f"{name} is not a member of '{g}'; skipping.")
            continue
        r.run(["gpasswd", "-d", name, g])
        changed = True
    if args.rename:
        old = state_path(name)
        if old.exists():
            r.run(["mv", "-n", str(old), str(state_path(args.rename))])
        warn("home directory and /home symlink keep their old names; "
             "use move-home to rename them.")
    if not changed:
        die("nothing to modify; see `usermgr.py modify -h`.")
    info(f"Modified user {name}.")


def cmd_passwd(args, r):
    pw = get_user(args.user)
    guard_regular(pw, args.force)
    set_password(r, pw.pw_name, resolve_password(args), force_change=not args.no_expire)


def cmd_lock(args, r):
    pw = get_user(args.user)
    guard_regular(pw, args.force)
    name = pw.pw_name
    sp = state_path(name)
    if sp.exists():
        warn(f"state file {sp} already exists (already locked?); keeping it.")
    else:
        sh = shadow_entry(name)
        r.write_state(sp, {
            "shell": pw.pw_shell,
            "expire": (sh[7] if sh and len(sh) >= 8 else ""),
        })
    # -L: lock the password; -e 1: expire the account so SSH keys stop working too;
    # nologin shell: belt and braces for anything that ignores account expiry.
    nologin = shutil.which("nologin") or "/sbin/nologin"
    r.run(["usermod", "-L", "-e", "1", "-s", nologin, name])
    if not args.no_kill:
        kill_user(r, name)
    info(f"Locked user {name}.")


def cmd_unlock(args, r):
    pw = get_user(args.user)
    guard_regular(pw, args.force)
    name = pw.pw_name
    sp = state_path(name)
    saved = {}
    if sp.exists():
        try:
            saved = json.loads(sp.read_text())
        except (OSError, ValueError):
            warn(f"could not read {sp}; falling back to defaults.")
    shell = args.shell or saved.get("shell") or DEFAULT_SHELL
    if "nologin" in shell or shell.endswith("/false"):
        shell = DEFAULT_SHELL
    expire = saved.get("expire", "")
    if expire and expire.isdigit():
        # shadow stores days since epoch; usermod -e wants a date
        expire = (date(1970, 1, 1) + timedelta(days=int(expire))).isoformat()
    # usermod -U fails with "unlocking would result in passwordless account"
    # if the password was never set; that is surfaced as-is.
    r.run(["usermod", "-U", "-e", expire, "-s", shell, name])
    r.remove_state(sp)
    info(f"Unlocked user {name} (shell {shell}).")


def cmd_move_home(args, r):
    pw = get_user(args.user)
    guard_regular(pw, args.force)
    name = pw.pw_name
    old = Path(pw.pw_dir)
    new = Path(args.to) if args.to else Path(args.base) / name
    if os.path.abspath(str(old)) == os.path.abspath(str(new)):
        die(f"{name}'s home is already {new}.")
    if os.path.lexists(str(new)):
        die(f"target {new} already exists; refusing to overwrite.")
    link = LINK_ROOT / name

    if has_processes(r, name):
        if not args.kill:
            die(f"{name} has running processes; usermod -m would fail. "
                "Re-run with --kill to terminate them.")
        kill_user(r, name)
    elif args.kill:
        kill_user(r, name)

    r.mkdir(new.parent)
    r.run(["usermod", "-d", str(new), "-m", name])

    if args.link and new != link:
        if link.is_symlink():
            r.unlink(link)
            r.symlink(new, link)
        elif link == old or not os.path.lexists(str(link)):
            # usermod -m just moved the real /home/USER away, so the slot is free
            r.symlink(new, link)
        else:
            warn(f"{link} exists and is not a symlink; not creating a link.")
    info(f"Moved {name}'s home: {old} -> {new}")


def cmd_delete(args, r):
    pw = get_user(args.user)
    guard_regular(pw, args.force)
    name = pw.pw_name
    if not args.yes and sys.stdin.isatty() and not r.dry_run:
        extra = " and its home directory" if args.remove_home else ""
        ans = input(f"Delete user {name}{extra}? Type the user name to confirm: ")
        if ans.strip() != name:
            die("aborted.")

    if has_processes(r, name):
        if not args.kill:
            die(f"{name} has running processes; re-run with --kill to terminate them.")
        kill_user(r, name)

    g = Grant(pw.pw_uid, name)
    if g.exists():
        if r.dry_run:
            info(f"[dry-run] revoke temporary sudo for {name} "
                 f"({g.sudoers}, {g.timer_name})")
        else:
            resolve_sudo_tools()
            revoke(g)
            info(f"Revoked temporary sudo for {name}.")

    home = Path(pw.pw_dir)
    link = LINK_ROOT / name
    argv = ["userdel"]
    if args.remove_home:
        argv.append("-r")
    argv.append(name)
    r.run(argv)
    if link.is_symlink() and link != home:
        r.unlink(link)
    r.remove_state(state_path(name))
    info(f"Deleted user {name}" + (f" and {home}." if args.remove_home else
                                  f"; home {home} kept."))


def _group_row(gr):
    members, primary = group_members(gr)
    return {"group": gr.gr_name, "gid": gr.gr_gid,
            "members": members, "primary_of": primary}


def cmd_group(args, r):
    a = args.action
    if a == "list":
        rows = [_group_row(gr) for gr in sorted(grp.getgrall(), key=lambda g: g.gr_gid)
                if args.all or is_regular_group(gr)]
        if args.json:
            print(json.dumps(rows, indent=2))
            return
        if not rows:
            info("No matching groups.")
            return
        table = [(x["group"], str(x["gid"]), ",".join(x["members"]) or "-",
                  ",".join(x["primary_of"]) or "-") for x in rows]
        header = ("GROUP", "GID", "MEMBERS", "PRIMARY_OF")
        widths = [max(len(h), *(len(t[i]) for t in table)) for i, h in enumerate(header)]
        for row in (header, *table):
            print("  ".join(c.ljust(w) for c, w in zip(row, widths)).rstrip())
        return

    if a == "create":
        try:
            grp.getgrnam(args.group)
            die(f"group '{args.group}' already exists.")
        except KeyError:
            pass
        argv = ["groupadd"]
        if args.gid is not None:
            argv += ["-g", str(args.gid)]
        if args.system:
            argv.append("-r")
        argv.append(args.group)
        r.run(argv)
        info(f"Created group {args.group}.")
        return

    gr = get_group(args.group)

    if a == "show":
        row = _group_row(gr)
        row["system"] = not is_regular_group(gr)
        if args.json:
            print(json.dumps(row, indent=2))
        else:
            for k, v in row.items():
                print(f"{k:12} {(', '.join(v) or '-') if isinstance(v, list) else v}")
        return

    if a == "rename":
        guard_regular_group(gr, args.force)
        try:
            grp.getgrnam(args.new_name)
            die(f"group '{args.new_name}' already exists.")
        except KeyError:
            pass
        r.run(["groupmod", "-n", args.new_name, gr.gr_name])
        info(f"Renamed group {gr.gr_name} -> {args.new_name}.")
        return

    if a == "delete":
        guard_regular_group(gr, args.force)
        primary = primary_users(gr.gr_gid)
        if primary:
            die(f"'{gr.gr_name}' is the primary group of: {', '.join(primary)}; "
                "change their primary group first (modify USER --primary-group G).")
        if gr.gr_mem:
            info(f"Note: removing supplementary members {', '.join(sorted(gr.gr_mem))}.")
        r.run(["groupdel", gr.gr_name])
        info(f"Deleted group {gr.gr_name}.")
        return

    if a == "add-member":
        users = [get_user(u).pw_name for u in args.users]
        warn_privileged([gr.gr_name])
        for u in users:
            if u in gr.gr_mem:
                info(f"{u} is already a member of {gr.gr_name}; skipping.")
                continue
            r.run(["gpasswd", "-a", u, gr.gr_name])
        return

    if a == "remove-member":
        for u in args.users:
            pw = get_user(u)
            if pw.pw_gid == gr.gr_gid:
                die(f"'{gr.gr_name}' is {u}'s primary group; change it first.")
        for u in args.users:
            if u not in gr.gr_mem:
                warn(f"{u} is not a member of {gr.gr_name}; skipping.")
                continue
            r.run(["gpasswd", "-d", u, gr.gr_name])
        return


def _sudo_dry_run(args):
    resolve_sudo_tools()
    if args.action == "list":
        info(f"[dry-run] list grants in {SUDOERS_DIR}/temp_sudo_u* and "
             f"{UNIT_DIR}/temp-sudo-u*.timer")
        return
    try:
        uid = pwd.getpwnam(args.user).pw_uid
    except KeyError:
        uid = "<UID>"
    g = Grant(uid, args.user)
    if args.action == "revoke":
        info(f"[dry-run] rm -f {g.sudoers}; systemctl disable --now {g.timer_name}; "
             f"rm -f {g.timer_path} {g.service_path}; systemctl daemon-reload")
        return
    exp = datetime.now(timezone.utc) + timedelta(seconds=args.duration)
    tag = "NOPASSWD: " if args.nopasswd else ""
    info(f"[dry-run] grant {args.user} sudo for {format_duration(args.duration)} "
         f"(until {exp.astimezone():%Y-%m-%d %H:%M:%S %Z})")
    info(f"[dry-run]   write {g.service_path} and {g.timer_path}; "
         f"systemctl enable --now {g.timer_name}")
    info(f"[dry-run]   visudo -cf, then move rule into {g.sudoers}: "
         f"{args.user} ALL=(ALL:ALL) {tag}ALL")


def cmd_sudo(args, r):
    if r.dry_run:
        _sudo_dry_run(args)
        return
    check_env()
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, _on_signal)
    lock_fd = acquire_lock()
    try:
        if args.action == "list":
            list_grants()
        elif args.action == "revoke":
            g = resolve_grant(args.user)
            if revoke(g):
                info(f"Revoked temporary sudo for [{args.user}].")
            else:
                info(f"[{args.user}] has no temporary grant; nothing to revoke.")
        else:
            grant(args.user, args.duration, args.nopasswd, args.force)
    except subprocess.CalledProcessError as e:
        die(f"command failed: {' '.join(e.cmd)}\n{e.stderr or ''}")
    finally:
        lock_fd.close()


# ---------------------------------------------------------------- parser

READ_ONLY = {"list", "show"}


def build_parser():
    p = argparse.ArgumentParser(
        prog="usermgr.py",
        description="Local account CRUD: create / list / show / modify / passwd / "
                    "lock / unlock / move-home / delete / group / sudo.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage:", 1)[1].split("Every mutating", 1)[0].rstrip(),
        allow_abbrev=False,
    )
    p.add_argument("-n", "--dry-run", action="store_true",
                   help="print the commands instead of running them")
    sub = p.add_subparsers(dest="cmd", metavar="COMMAND")
    sub.required = True

    def user_cmd(name, help_, force=True):
        sp = sub.add_parser(name, help=help_, allow_abbrev=False)
        sp.add_argument("user", type=username_type)
        if force:
            sp.add_argument("--force", action="store_true",
                            help="allow operating on accounts outside UID_MIN..UID_MAX")
        return sp

    def pw_opts(sp, what):
        g = sp.add_mutually_exclusive_group()
        g.add_argument("-p", "--password", metavar="PASS",
                       help="use this password (visible in ps/history; "
                            "prefer --password-stdin)")
        g.add_argument("--password-stdin", action="store_true",
                       help="read the password from stdin (prompts twice on a TTY)")
        g.add_argument("--no-password", action="store_true",
                       help="no usable password (SSH-key-only login)")
        sp.add_argument("--password-length", type=password_length_type,
                        default=PASSWORD_LENGTH, metavar="N",
                        help=f"length of the generated password (default {PASSWORD_LENGTH})")
        sp.add_argument("--no-expire", action="store_true",
                        help=f"do not force a password change at {what}")

    c = user_cmd("create", "create a user (default: random password, printed once, "
                           "must change on first login)", force=False)
    c.add_argument("-s", "--shell", default=DEFAULT_SHELL)
    hg = c.add_mutually_exclusive_group()
    hg.add_argument("-d", "--home", help="explicit home directory")
    hg.add_argument("--home-base", metavar="DIR",
                    help=f"put the home at DIR/USER (e.g. {DEFAULT_HOME_BASE})")
    c.add_argument("--no-link", dest="link", action="store_false",
                   help="with --home/--home-base, do not symlink /home/USER to it")
    c.add_argument("-G", "--groups", type=groups_type, help="comma-separated supplementary groups")
    c.add_argument("-c", "--comment", help="GECOS / full name")
    c.add_argument("-u", "--uid", type=int)
    c.add_argument("-e", "--expire", metavar="YYYY-MM-DD", help="account expiry date")
    pw_opts(c, "first login")
    c.set_defaults(func=cmd_create)

    ls = sub.add_parser("list", help="list human accounts")
    ls.add_argument("-a", "--all", action="store_true", help="include system accounts")
    ls.add_argument("--json", action="store_true")
    ls.set_defaults(func=cmd_list)

    s = user_cmd("show", "show one account", force=False)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_show)

    m = user_cmd("modify", "change shell / comment / groups / expiry / name")
    m.add_argument("-s", "--shell")
    m.add_argument("-c", "--comment")
    m.add_argument("-e", "--expire", metavar="YYYY-MM-DD", help="'' clears the expiry")
    m.add_argument("-g", "--primary-group", type=username_type, metavar="GROUP",
                   help="set the primary group")
    sg_ = m.add_mutually_exclusive_group()
    sg_.add_argument("--set-groups", type=groups_type, metavar="G1,G2",
                     help="replace ALL supplementary groups ('' clears them)")
    sg_.add_argument("--add-groups", type=groups_type, metavar="G1,G2",
                     help="append supplementary groups")
    m.add_argument("--remove-groups", type=groups_type, metavar="G1,G2",
                   help="leave supplementary groups")
    m.add_argument("--rename", type=username_type, metavar="NEW_NAME")
    m.set_defaults(func=cmd_modify)

    pwp = user_cmd("passwd", "reset password (default: random, printed once, "
                             "must change on next login)")
    pw_opts(pwp, "next login")
    pwp.set_defaults(func=cmd_passwd)

    lk = user_cmd("lock", "lock account, expire it (blocks SSH keys), set nologin, kill sessions")
    lk.add_argument("--no-kill", action="store_true", help="leave running processes alone")
    lk.set_defaults(func=cmd_lock)

    ul = user_cmd("unlock", "undo lock, restoring the saved shell and expiry")
    ul.add_argument("-s", "--shell", help="override the shell to restore")
    ul.set_defaults(func=cmd_unlock)

    mh = user_cmd("move-home", "move the home directory (usermod -d -m) and symlink /home/USER")
    tg = mh.add_mutually_exclusive_group()
    tg.add_argument("--to", metavar="PATH", help="new home path")
    tg.add_argument("--base", metavar="DIR", default=DEFAULT_HOME_BASE,
                    help=f"new home = DIR/USER (default {DEFAULT_HOME_BASE})")
    mh.add_argument("--no-link", dest="link", action="store_false",
                    help="do not (re)create the /home/USER symlink")
    mh.add_argument("--kill", action="store_true", help="kill the user's processes first")
    mh.set_defaults(func=cmd_move_home)

    d = user_cmd("delete", "delete a user (revokes temp sudo, removes /home symlink)")
    d.add_argument("-r", "--remove-home", action="store_true", help="also delete home + mail spool")
    d.add_argument("--kill", action="store_true", help="kill the user's processes first")
    d.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")
    d.set_defaults(func=cmd_delete)

    gp = sub.add_parser("group", help="group CRUD and membership")
    gsub = gp.add_subparsers(dest="action", metavar="ACTION")
    gsub.required = True
    g_list = gsub.add_parser("list", help="list groups (GID_MIN..GID_MAX) with members")
    g_list.add_argument("-a", "--all", action="store_true", help="include system groups")
    g_list.add_argument("--json", action="store_true")
    g_show = gsub.add_parser("show", help="show one group")
    g_show.add_argument("group", type=username_type)
    g_show.add_argument("--json", action="store_true")
    g_new = gsub.add_parser("create", help="create a group (groupadd)")
    g_new.add_argument("group", type=username_type)
    g_new.add_argument("--gid", type=int)
    g_new.add_argument("--system", action="store_true", help="allocate a system GID")
    g_ren = gsub.add_parser("rename", help="rename a group (groupmod -n)")
    g_ren.add_argument("group", type=username_type)
    g_ren.add_argument("new_name", type=username_type)
    g_ren.add_argument("--force", action="store_true", help="allow system groups")
    g_del = gsub.add_parser("delete", help="delete a group (refused if it is a primary group)")
    g_del.add_argument("group", type=username_type)
    g_del.add_argument("--force", action="store_true", help="allow system groups")
    g_add = gsub.add_parser("add-member", help="add users to a group (gpasswd -a)")
    g_add.add_argument("group", type=username_type)
    g_add.add_argument("users", nargs="+", type=username_type, metavar="USER")
    g_rm = gsub.add_parser("remove-member", help="remove users from a group (gpasswd -d)")
    g_rm.add_argument("group", type=username_type)
    g_rm.add_argument("users", nargs="+", type=username_type, metavar="USER")
    gp.set_defaults(func=cmd_group)

    su = sub.add_parser("sudo", help="temporary sudo, auto-revoked by a systemd timer")
    ssub = su.add_subparsers(dest="action", metavar="ACTION")
    ssub.required = True
    sg = ssub.add_parser("grant", help="grant temporary sudo")
    sg.add_argument("user", type=username_type)
    sg.add_argument("duration", type=duration_type,
                    help='e.g. 30s, 5m, 2h, 1d, 1w, 1w2d, "1 week 2 days" (max 52 weeks)')
    sg.add_argument("--nopasswd", action="store_true")
    sg.add_argument("--force", action="store_true", help="replace / extend an existing grant")
    sr = ssub.add_parser("revoke", help="revoke now")
    sr.add_argument("user", type=username_type)
    ssub.add_parser("list", help="list temporary grants")
    su.set_defaults(func=cmd_sudo)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    read_only = args.cmd in READ_ONLY or (
        args.cmd == "group" and args.action in READ_ONLY)
    if not read_only and not args.dry_run and os.geteuid() != 0:
        die("must be run as root (or use --dry-run).")
    r = Runner(dry_run=args.dry_run)
    args.func(args, r)


if __name__ == "__main__":
    main()
