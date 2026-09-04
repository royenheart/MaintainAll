from __future__ import annotations

import os

import pytest


def test_non_windows_is_unimplemented(monkeypatch, capsys):
    import sys

    import tray

    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(sys, "argv", ["tray.py"])
    with pytest.raises(SystemExit) as ei:
        tray.main()
    assert ei.value.code == 2
    err = capsys.readouterr().err
    assert "unimplemented" in err
