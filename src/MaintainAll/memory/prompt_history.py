from __future__ import annotations

import json
from pathlib import Path


def load_prompt_history(path: Path, *, max_size: int = 100) -> list[str]:
    """Load newest-last prompt lines from a JSONL file."""
    if not path.is_file():
        return []
    entries: list[str] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                # Plain text fallback
                entries.append(line)
                continue
            if isinstance(data, str):
                text = data.strip()
            elif isinstance(data, dict):
                text = str(data.get("text") or "").strip()
            else:
                continue
            if text:
                entries.append(text)
    except OSError:
        return []
    if max_size > 0 and len(entries) > max_size:
        entries = entries[-max_size:]
    return entries


def append_prompt_history(path: Path, text: str, *, max_size: int = 100) -> None:
    """Append one prompt; rewrite file if over max_size to trim oldest."""
    text = (text or "").strip()
    if not text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = load_prompt_history(path, max_size=max_size)
        if existing and existing[-1] == text:
            return
        existing.append(text)
        if len(existing) > max_size:
            existing = existing[-max_size:]
            # Rewrite trimmed history
            with path.open("w", encoding="utf-8") as fh:
                for item in existing:
                    fh.write(json.dumps({"text": item}, ensure_ascii=False) + "\n")
            return
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")
    except OSError:
        return
