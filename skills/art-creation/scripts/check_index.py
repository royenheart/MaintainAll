#!/usr/bin/env python3
"""Validate Art Creation routing tables, local links, and resource coverage."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

HEADERS = ("ID", "Read when", "Resource", "Type")
TYPES = {"skill", "reference", "script", "template"}
LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
ROUTING_TABLES = {
    "SKILL.md": ("User need", "Capability", "Read"),
    "references/iterative-creation.md": (
        "Next question / representation", "Detailed skill", "Concrete support"
    ),
    "references/fashion-design.md": ("Current question", "Useful representation or route"),
    "references/tool-capabilities.md": ("Selected backend", "Read when useful"),
    "references/feedback-setup.md": ("Current need", "Read", "Verify"),
    "methods/game-engine/references/remote-preview.md": ("Option", "Read", "Role"),
    "methods/remotion-video/SKILL.md": ("Need", "Read"),
}
INDEX = "references/resource-index.md"


def prose(text: str) -> str:
    """Remove fenced and indented code before checking documentation links."""
    result = []
    fence = None
    for line in text.splitlines():
        stripped = line.lstrip()
        if fence:
            if stripped.startswith(fence):
                fence = None
            result.append("")
        elif stripped.startswith((chr(96) * 3, "~" * 3)):
            fence = stripped[:3]
            result.append("")
        else:
            result.append("" if line.startswith(("    ", "\t")) else line)
    return "\n".join(result)


def cells(line: str) -> list[str] | None:
    line = line.strip()
    if not line.startswith("|") or not line.endswith("|"):
        return None
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", line[1:-1])]


def table(text: str, header: tuple[str, ...]) -> tuple[list[list[str]], list[str]]:
    lines = prose(text).splitlines()
    matches = [i for i, line in enumerate(lines) if cells(line) == list(header)]
    if len(matches) != 1:
        return [], [f"expected exactly one table with columns: {' | '.join(header)}"]
    pos = matches[0]
    separator = cells(lines[pos + 1]) if pos + 1 < len(lines) else None
    if not separator or len(separator) != len(header) or not all(
        re.fullmatch(r":?-{3,}:?", cell) for cell in separator
    ):
        return [], ["missing or invalid Markdown table separator"]
    rows = []
    errors = []
    for line in lines[pos + 2:]:
        if not line.strip():
            break
        row = cells(line)
        if row is None:
            errors.append("table row must start and end with a pipe")
            break
        if len(row) != len(header) or not all(row):
            errors.append("table row has an incorrect column count or empty cell")
        else:
            rows.append(row)
    if not rows:
        errors.append("routing table has no data rows")
    return rows, errors


def anchors(path: Path) -> set[str]:
    """Recognize ordinary GitHub heading anchors, including duplicate suffixes."""
    found = set()
    counts: dict[str, int] = {}
    for line in prose(path.read_text(encoding="utf-8")).splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)(?:\s+#+)?$", line)
        if not match:
            continue
        title = re.sub(r"[^\w\s-]", "", match.group(1).lower())
        slug = re.sub(r"\s", "-", title)
        count = counts.get(slug, 0)
        found.add(f"{slug}-{count}" if count else slug)
        counts[slug] = count + 1
    return found


def target(root: Path, source: Path, href: str) -> tuple[Path | None, str | None]:
    href = href.strip("<>")
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc:
        return None, None
    path = (source.parent / unquote(parsed.path)).resolve() if parsed.path else source
    if not path.is_relative_to(root):
        return None, f"link escapes bundle: {href}"
    if not path.exists():
        return None, f"missing link target: {href}"
    if parsed.fragment:
        if not path.is_file() or path.suffix.lower() != ".md":
            return None, f"anchor target is not Markdown: {href}"
        if unquote(parsed.fragment) not in anchors(path):
            return None, f"missing heading anchor: {href}"
    return path, None


def inventory(root: Path) -> set[Path]:
    resources = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if path.name == "SKILL.md" or any(
            part in relative.parts for part in ("references", "scripts", "templates")
        ):
            if path.suffix in {".md", ".py", ".js", ".jsx", ".html", ".svg", ".godot", ".tscn", ".gd", ".cfg"}:
                resources.add(path.resolve())
    resources.discard((root / INDEX).resolve())
    return resources


def expected_type(root: Path, path: Path) -> str | None:
    relative = path.relative_to(root)
    if path.name == "SKILL.md":
        return "skill"
    if "scripts" in relative.parts:
        return "script"
    if "templates" in relative.parts:
        return "template"
    if "references" in relative.parts and path.suffix == ".md":
        return "reference"
    return None


def check(root: Path) -> dict:
    root = root.resolve()
    errors = []
    local_links = 0

    def issue(source: str, message: str) -> None:
        errors.append({"source": source, "message": message})

    if not (root / "SKILL.md").is_file():
        issue("SKILL.md", "skill root is missing")
        return {"passed": False, "resources": 0, "local_links": 0, "errors": errors}

    for source in sorted(root.rglob("*.md")):
        relative = source.relative_to(root).as_posix()
        if not source.resolve().is_relative_to(root):
            issue(relative, "document symlink escapes bundle")
            continue
        for _, href in LINK.findall(prose(source.read_text(encoding="utf-8"))):
            parsed = urlsplit(href.strip("<>"))
            if not parsed.scheme and not parsed.netloc:
                local_links += 1
            _, error = target(root, source, href)
            if error:
                issue(relative, error)

    for relative, header in ROUTING_TABLES.items():
        source = root / relative
        if not source.is_file():
            issue(relative, "routing document is missing")
            continue
        rows, table_errors = table(source.read_text(encoding="utf-8"), header)
        for error in table_errors:
            issue(relative, error)
        for row in rows:
            count = len(LINK.findall(row[2] if relative == "SKILL.md" else row[1]))
            if count < 1 or (relative != "references/fashion-design.md" and count != 1):
                issue(relative, "routing row has an invalid number of destination links")

    index = root / INDEX
    seen_ids = set()
    indexed = set()
    if not index.is_file():
        issue(INDEX, "resource index is missing")
        rows = []
    else:
        rows, table_errors = table(index.read_text(encoding="utf-8"), HEADERS)
        for error in table_errors:
            issue(INDEX, error)
    for row in rows:
        ident, _, resource, kind = row
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", ident):
            issue(INDEX, f"invalid resource ID: {ident}")
        if ident in seen_ids:
            issue(INDEX, f"duplicate resource ID: {ident}")
        seen_ids.add(ident)
        if kind not in TYPES:
            issue(INDEX, f"unknown resource type: {kind}")
        links = LINK.findall(resource)
        if len(links) != 1:
            issue(INDEX, f"{ident}: resource cell must contain one local link")
            continue
        path, error = target(root, index, links[0][1])
        if error or path is None or not path.is_file():
            issue(INDEX, f"{ident}: invalid local resource: {error or links[0][1]}")
            continue
        if path in indexed:
            issue(INDEX, f"duplicate resource target: {links[0][1]}")
        indexed.add(path)
        if expected_type(root, path) != kind:
            issue(INDEX, f"{ident}: resource type does not match its path")

    resources = inventory(root)
    for path in sorted(resources - indexed):
        # Label escaped paths directly, keeping inspection inside the bundle.
        label = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
        issue(INDEX, f"unindexed resource: {label}")
    for path in sorted(indexed - resources):
        issue(INDEX, f"unexpected index target: {path.relative_to(root).as_posix()}")
    return {
        "passed": not errors,
        "resources": len(resources),
        "local_links": local_links,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Examples: python check_index.py; python check_index.py --root /path/to/art-creation --json\n"
            "Checks routing tables, local paths, heading anchors, and resource coverage. "
            "Paths resolve relative to their containing file. "
            "Exit 0: checks pass; exit 1: invalid resources."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1],
        help="Skill bundle root; defaults to this script's bundle, independently of the working directory.",
    )
    parser.add_argument("--json", action="store_true", help="Print a machine-readable check summary.")
    args = parser.parse_args()
    try:
        result = check(args.root)
    except (OSError, UnicodeError, ValueError) as exc:
        result = {"passed": False, "resources": 0, "local_links": 0,
                  "errors": [{"source": str(args.root), "message": str(exc)}]}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{'PASS' if result['passed'] else 'FAIL'}: {result['resources']} resources, "
              f"{result['local_links']} local links")
        for error in result["errors"]:
            print(f"{error['source']}: {error['message']}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
