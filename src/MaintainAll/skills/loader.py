from __future__ import annotations

import re
from pathlib import Path

from MaintainAll.skills.models import SkillMeta

FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    m = FRONTMATTER.match(text)
    if not m:
        return {}, text
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip("\"'")
    return meta, m.group(2)


def load_skills(root: Path) -> list[SkillMeta]:
    out: list[SkillMeta] = []
    if not root.exists():
        return out
    for skill_md in sorted(root.glob("*/SKILL.md")):
        meta, _ = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        name = meta.get("name") or skill_md.parent.name
        desc = meta.get("description") or ""
        out.append(SkillMeta(name=name, description=desc, path=skill_md.parent))
    return out


def load_skill_body(skill_dir: Path) -> str:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    _, body = _parse_frontmatter(text)
    return body
