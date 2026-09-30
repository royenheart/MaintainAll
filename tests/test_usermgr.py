"""Dry-run tests for scripts/usermgr.py: they check the argv it would run, never touch the system."""

import importlib.util
import grp
import pwd
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "usermgr.py"
spec = importlib.util.spec_from_file_location("usermgr", SCRIPT)
usermgr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usermgr)


def dry(argv):
    parser = usermgr.build_parser()
    args = parser.parse_args(["--dry-run", *argv])
    r = usermgr.Runner(dry_run=True)
    args.func(args, r)
    return r.history


def fake_pw(name="alice", uid=1500, home="/home/alice", shell="/bin/bash"):
    return pwd.struct_passwd((name, "x", uid, uid, "", home, shell))


@pytest.fixture
def alice(monkeypatch, tmp_path):
    pw = fake_pw()
    monkeypatch.setattr(usermgr, "get_user", lambda name: pw)
    monkeypatch.setattr(usermgr, "is_regular_user", lambda p: p.pw_uid >= 1000)
    monkeypatch.setattr(usermgr, "shadow_entry", lambda n: None)
    monkeypatch.setattr(usermgr, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(usermgr, "LINK_ROOT", tmp_path / "home")
    return pw


@pytest.fixture
def no_user(monkeypatch):
    monkeypatch.setattr(usermgr.pwd, "getpwnam", lambda n: (_ for _ in ()).throw(KeyError(n)))


def test_create_default_random_password(no_user, capsys):
    h = dry(["create", "bob"])
    assert h[0] == ["useradd", "-m", "-s", "/bin/bash", "bob"]
    assert h[1] == ["chpasswd"]  # password goes over stdin, not argv
    assert h[2] == ["chage", "-d", "0", "bob"]
    assert "Password for bob:" in capsys.readouterr().out


def test_create_explicit_password_no_expire(no_user):
    h = dry(["create", "bob", "-p", "Given-Pass-1", "--no-expire"])
    assert ["chpasswd"] in h
    assert not any(c[0] == "chage" for c in h)
    assert all("Given-Pass-1" not in " ".join(c) for c in h)


def test_create_empty_password_fails_before_useradd(no_user):
    parser = usermgr.build_parser()
    args = parser.parse_args(["--dry-run", "create", "bob", "-p", ""])
    r = usermgr.Runner(dry_run=True)
    with pytest.raises(SystemExit):
        args.func(args, r)
    assert r.history == []


def test_create_no_password_is_key_only(no_user):
    h = dry(["create", "bob", "--no-password"])
    assert ["usermod", "-p", "!", "bob"] in h


def test_fallback_to_usermod_when_no_chpasswd(no_user, monkeypatch):
    real = usermgr.shutil.which
    monkeypatch.setattr(usermgr.shutil, "which",
                        lambda n: None if n == "chpasswd" else real(n))
    h = dry(["create", "bob", "-p", "Given-Pass-1"])
    assert any(c[:2] == ["usermod", "-p"] and c[-1] == "bob" for c in h)


def test_fail_when_no_backend(no_user, monkeypatch):
    monkeypatch.setattr(usermgr.shutil, "which", lambda n: None)
    monkeypatch.setattr(usermgr, "_hash_password", lambda r, p: None)
    with pytest.raises(SystemExit):
        dry(["create", "bob", "-p", "Given-Pass-1"])


def test_gen_password_has_every_class():
    for _ in range(200):
        pw = usermgr.gen_password(12)
        assert len(pw) == 12
        assert all(any(ch in cls for ch in pw) for cls in usermgr._PW_CLASSES)


def test_gen_password_falls_back_without_secrets(monkeypatch):
    monkeypatch.setattr(usermgr, "secrets", None)
    assert len(usermgr.gen_password()) == usermgr.PASSWORD_LENGTH


def test_password_length_bounds():
    with pytest.raises(SystemExit):
        usermgr.build_parser().parse_args(["create", "bob", "--password-length", "8"])


def test_create_with_home_base_links_home(no_user, monkeypatch, tmp_path):
    monkeypatch.setattr(usermgr, "LINK_ROOT", tmp_path)
    h = dry(["create", "bob", "--home-base", "/data/users", "-G", "docker,video"])
    assert ["useradd", "-m", "-s", "/bin/bash", "-d", "/data/users/bob",
            "-G", "docker,video", "bob"] in h
    assert ["ln", "-s", "/data/users/bob", str(tmp_path / "bob")] in h


def test_lock_blocks_keys_and_kills(alice):
    h = dry(["lock", "alice"])
    assert any(c[:5] == ["usermod", "-L", "-e", "1", "-s"] for c in h)
    assert ["pkill", "-KILL", "-u", "alice"] in h


def test_unlock_restores_default_shell(alice):
    h = dry(["unlock", "alice"])
    assert ["usermod", "-U", "-e", "", "-s", "/bin/bash", "alice"] in h


def test_move_home_default_base(alice):
    h = dry(["move-home", "alice"])
    assert ["usermod", "-d", "/mnt/data1/users/alice", "-m", "alice"] in h


def test_system_account_is_refused(monkeypatch):
    monkeypatch.setattr(usermgr, "get_user", lambda n: fake_pw("daemon", 1, "/", "/sbin/nologin"))
    monkeypatch.setattr(usermgr, "is_regular_user", lambda p: False)
    with pytest.raises(SystemExit):
        dry(["lock", "daemon"])


def test_bad_username_rejected():
    with pytest.raises(SystemExit):
        usermgr.build_parser().parse_args(["create", "a b"])


# ---------------------------------------------------------------- groups

def fake_gr(name, gid, mem=()):
    return grp.struct_group((name, "x", gid, list(mem)))


@pytest.fixture
def groups(monkeypatch, alice):
    table = {"lab": fake_gr("lab", 2000, ["alice"]), "docker": fake_gr("docker", 996),
             "alice": fake_gr("alice", 1500), "adm": fake_gr("adm", 4)}

    def getgrnam(n):
        if n not in table:
            raise KeyError(n)
        return table[n]
    monkeypatch.setattr(usermgr.grp, "getgrnam", getgrnam)
    monkeypatch.setattr(usermgr.grp, "getgrall", lambda: list(table.values()))
    monkeypatch.setattr(usermgr.pwd, "getpwall", lambda: [alice])
    monkeypatch.setattr(usermgr, "is_regular_group", lambda g: g.gr_gid >= 1000)
    return table


def test_group_create_with_gid(groups):
    assert dry(["group", "create", "newg", "--gid", "3000"]) == [["groupadd", "-g", "3000", "newg"]]


def test_group_add_member_skips_existing(groups):
    assert dry(["group", "add-member", "lab", "alice"]) == []
    assert dry(["group", "add-member", "docker", "alice"]) == [["gpasswd", "-a", "alice", "docker"]]


def test_group_delete_refuses_primary_group(groups):
    with pytest.raises(SystemExit):
        dry(["group", "delete", "alice"])  # alice's primary gid is 1500


def test_group_delete_refuses_system_group(groups):
    with pytest.raises(SystemExit):
        dry(["group", "delete", "adm"])
    assert dry(["group", "delete", "adm", "--force"]) == [["groupdel", "adm"]]


def test_group_rename(groups):
    assert dry(["group", "rename", "lab", "lab2"]) == [["groupmod", "-n", "lab2", "lab"]]


def test_modify_primary_and_set_groups(groups):
    h = dry(["modify", "alice", "--primary-group", "lab", "--set-groups", "docker"])
    assert h == [["usermod", "-g", "lab", "-G", "docker", "alice"]]


def test_modify_set_groups_empty_clears(groups):
    assert dry(["modify", "alice", "--set-groups", ""]) == [["usermod", "-G", "", "alice"]]


def test_modify_unknown_group_fails(groups):
    with pytest.raises(SystemExit):
        dry(["modify", "alice", "--add-groups", "nosuch"])


def test_set_and_add_groups_are_exclusive():
    with pytest.raises(SystemExit):
        usermgr.build_parser().parse_args(
            ["modify", "alice", "--set-groups", "a", "--add-groups", "b"])


# ---------------------------------------------------------------- temporary sudo

@pytest.mark.parametrize("text,seconds", [
    ("30s", 30), ("5m", 300), ("2h", 7200), ("1w2d", 777600),
    ("1 week, 2 days", 777600), ("1h30m", 5400), ("3WEEKS", 1814400),
])
def test_parse_duration(text, seconds):
    assert usermgr.parse_duration(text) == seconds


@pytest.mark.parametrize("text", ["", "0s", "2x", "1h1h", "53w", "abc"])
def test_parse_duration_rejects(text):
    with pytest.raises(ValueError):
        usermgr.parse_duration(text)


def test_sudo_grant_dry_run_touches_nothing(alice, capsys):
    h = dry(["sudo", "grant", "alice", "2h", "--nopasswd"])
    out = capsys.readouterr().out
    assert h == []
    assert "alice ALL=(ALL:ALL) NOPASSWD: ALL" in out
    assert "temp-sudo-u" in out


def test_render_sudoers_rule():
    g = usermgr.Grant(1500, "alice")
    text = usermgr.render_sudoers(g, False, 0, 3600)
    assert text.splitlines()[-1] == "alice ALL=(ALL:ALL) ALL"
    assert "expires_epoch: 3600" in text
    assert g.sudoers.name == "temp_sudo_u1500"  # no '.', so includedir reads it
