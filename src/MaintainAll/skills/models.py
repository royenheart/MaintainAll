from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillMeta:
    name: str
    description: str
    path: Path
