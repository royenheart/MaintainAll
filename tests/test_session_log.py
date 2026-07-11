from __future__ import annotations

import json
from pathlib import Path

from MaintainAll.memory.session_log import SessionLog


def _read_events(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_session_log_coalesces_thinking_deltas(tmp_path: Path):
    log = SessionLog(tmp_path, session_id="test-coalesce", data_dir=tmp_path)
    log.write({"type": "thinking_start", "phase": "assess", "id": "t1"})
    for ch in ("你", "好", "世界"):
        log.write(
            {
                "type": "thinking_delta",
                "phase": "assess",
                "id": "t1",
                "text": ch,
                "kind": "content",
            }
        )
    log.write(
        {
            "type": "thinking_delta",
            "phase": "assess",
            "id": "t1",
            "text": "reason",
            "kind": "reasoning",
        }
    )
    log.write({"type": "thinking_end", "phase": "assess", "id": "t1"})
    log.write({"type": "assess", "feasible": True, "reason": "ok"})

    events = _read_events(log.path)
    types = [e["type"] for e in events]
    assert types == ["thinking_start", "thinking", "thinking_end", "assess"]
    thinking = next(e for e in events if e["type"] == "thinking")
    assert thinking["content"] == "你好世界"
    assert thinking["reasoning"] == "reason"
    assert thinking["id"] == "t1"
    assert thinking["phase"] == "assess"
    # No per-token lines on disk
    assert not any(e["type"] == "thinking_delta" for e in events)


def test_session_log_flush_on_non_stream_event(tmp_path: Path):
    log = SessionLog(tmp_path, session_id="test-flush", data_dir=tmp_path)
    log.write({"type": "thinking_start", "phase": "board", "id": "t2"})
    log.write(
        {
            "type": "thinking_delta",
            "phase": "board",
            "id": "t2",
            "text": "partial",
            "kind": "content",
        }
    )
    # Missing thinking_end — next event should still flush buffer
    log.write({"type": "board", "id": "m1"})
    events = _read_events(log.path)
    assert any(e["type"] == "thinking" and e.get("content") == "partial" for e in events)
    assert events[-1]["type"] == "board"
