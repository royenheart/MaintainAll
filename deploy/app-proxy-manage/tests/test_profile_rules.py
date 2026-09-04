from __future__ import annotations

from profile_rules import (
    is_process_rule,
    normalize_exe,
    process_names_from_rules,
    replace_process_rules,
    unique_exes,
)


def test_normalize_exe_basename_and_suffix():
    assert normalize_exe(r"C:\Program Files\Telegram\Telegram.exe") == "Telegram.exe"
    assert normalize_exe("chrome") == "chrome.exe"
    assert unique_exes(["Chrome.exe", "chrome", "firefox.exe"]) == ["Chrome.exe", "firefox.exe"]


def test_replace_inserts_before_match():
    data = {
        "rules": [
            "IP-CIDR,10.0.0.0/8,DIRECT,no-resolve",
            "PROCESS-NAME,old.exe,proxy",
            "MATCH,DIRECT",
        ]
    }
    replace_process_rules(data, ["Telegram.exe", "Cursor.exe"])
    assert data["rules"][0] == "IP-CIDR,10.0.0.0/8,DIRECT,no-resolve"
    assert data["rules"][1] == "PROCESS-NAME,Telegram.exe,proxy"
    assert data["rules"][2] == "PROCESS-NAME,Cursor.exe,proxy"
    assert data["rules"][-1] == "MATCH,DIRECT"
    assert process_names_from_rules(data) == ["Telegram.exe", "Cursor.exe"]


def test_replace_clears_process_rules_when_empty():
    data = {
        "rules": [
            "PROCESS-NAME,a.exe,proxy",
            "# （未选择进程：全部 MATCH,DIRECT）",
            "MATCH,DIRECT",
        ]
    }
    replace_process_rules(data, [])
    assert [r for r in data["rules"] if is_process_rule(r)] == []
    assert data["rules"][-1] == "MATCH,DIRECT"


def test_keeps_existing_match_policy():
    data = {"rules": ["GEOIP,CN,DIRECT", "MATCH,proxy"]}
    replace_process_rules(data, ["ssh.exe"])
    assert data["rules"][-1] == "MATCH,proxy"
    assert data["rules"][1] == "PROCESS-NAME,ssh.exe,proxy"
