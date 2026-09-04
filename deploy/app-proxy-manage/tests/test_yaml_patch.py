from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from profile_rules import process_names_from_rules, replace_process_rules


def test_patch_sample_runtime_yaml(tmp_path: Path):
    src = tmp_path / "clash-verge.yaml"
    src.write_text(
        """
mode: rule
mixed-port: 7897
proxies:
  - name: upstream-socks
    type: socks5
    server: 127.0.0.1
    port: 1080
rules:
  - IP-CIDR,127.0.0.0/8,DIRECT,no-resolve
  - MATCH,DIRECT
""".strip()
        + "\n",
        encoding="utf-8",
    )
    data = yaml.safe_load(src.read_text(encoding="utf-8"))
    replace_process_rules(data, ["Telegram.exe"])
    src.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    loaded = yaml.safe_load(src.read_text(encoding="utf-8"))
    assert process_names_from_rules(loaded) == ["Telegram.exe"]
    assert loaded["mixed-port"] == 7897
    assert loaded["rules"][-1] == "MATCH,DIRECT"
