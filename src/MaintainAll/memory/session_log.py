from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from MaintainAll.paths import logs_dir

# High-frequency stream chunks — coalesce before disk write.
_STREAM_DELTA = "thinking_delta"
_STREAM_END = "thinking_end"
_STREAM_START = "thinking_start"


class SessionLog:
    """Append-only JSONL session trace under .maintainall/logs/.

    Stream token events (``thinking_delta``) are buffered in memory and flushed
    as a single coalesced ``thinking`` record when the stream ends, so disk I/O
    stays proportional to LLM calls rather than tokens.
    """

    def __init__(self, repo: Path, session_id: str | None = None) -> None:
        self._repo = Path(repo)
        if session_id is None:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            short = secrets.token_hex(3)
            session_id = f"session-{ts}-{short}"
        self._session_id = session_id
        self._path = logs_dir(self._repo) / f"{session_id}.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # think_id -> {"phase": ..., "reasoning": [str], "content": [str]}
        self._stream_bufs: dict[str, dict[str, Any]] = {}

    @property
    def path(self) -> Path:
        return self._path

    def write(self, event: dict[str, Any]) -> None:
        etype = event.get("type")
        if etype == _STREAM_DELTA:
            self._buffer_delta(event)
            return
        if etype == _STREAM_START:
            tid = str(event.get("id") or "")
            if tid:
                self._stream_bufs[tid] = {
                    "phase": event.get("phase"),
                    "reasoning": [],
                    "content": [],
                }
            self._append(event)
            return
        if etype == _STREAM_END:
            self._flush_stream(str(event.get("id") or ""))
            self._append(event)
            return
        # Non-stream event: flush any pending streams first (safety net).
        self.flush_streams()
        self._append(event)

    def flush_streams(self) -> None:
        for tid in list(self._stream_bufs):
            self._flush_stream(tid)

    def _buffer_delta(self, event: dict[str, Any]) -> None:
        tid = str(event.get("id") or "")
        text = event.get("text")
        if not tid or text is None or text == "":
            return
        buf = self._stream_bufs.get(tid)
        if buf is None:
            buf = {
                "phase": event.get("phase"),
                "reasoning": [],
                "content": [],
            }
            self._stream_bufs[tid] = buf
        elif event.get("phase") is not None:
            buf["phase"] = event.get("phase")
        kind = str(event.get("kind") or "content")
        if kind == "reasoning":
            buf["reasoning"].append(str(text))
        else:
            buf["content"].append(str(text))

    def _flush_stream(self, tid: str) -> None:
        if not tid:
            return
        buf = self._stream_bufs.pop(tid, None)
        if not buf:
            return
        reasoning = "".join(buf.get("reasoning") or [])
        content = "".join(buf.get("content") or [])
        if not reasoning and not content:
            return
        record: dict[str, Any] = {
            "type": "thinking",
            "phase": buf.get("phase"),
            "id": tid,
        }
        if reasoning:
            record["reasoning"] = reasoning
        if content:
            record["content"] = content
        self._append(record)

    def _append(self, event: dict[str, Any]) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            **event,
        }
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
