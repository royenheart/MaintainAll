"""Portable cases with requirements linked to observable, active evidence."""

import hashlib
import json
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator


SCHEMAS = Path(__file__).resolve().parent / "schemas"
if not SCHEMAS.is_dir():
    SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"


def content_hash(data):
    return hashlib.sha256(data).hexdigest()


def json_hash(value):
    return content_hash(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                   separators=(",", ":")).encode())


def validate_document(value, name):
    schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text())
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda e: str(e.path))
    if errors:
        error = errors[0]
        raise ValueError(f"{name} contract at {list(error.path)}: {error.message}")
    return value


def artifact_path(value):
    """Artifacts are workspace-relative POSIX names, never a host capability."""
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value or value in (".", ""):
        raise ValueError(f"Unsafe artifact path: {value!r}")
    return path


def checked_file(root, value, base=None):
    """Allow shared ../ assets only inside the suite, without symlink traversal."""
    root = Path(root).resolve()
    path = (Path(base) if base else root) / value
    if Path(value).is_absolute():
        raise ValueError("An asset path must be relative to the case")
    absolute = path.absolute()
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Asset path escapes the suite root")
    for ancestor in [absolute, *absolute.parents]:
        if ancestor.is_symlink():
            raise ValueError("Asset path traverses a symlink")
        if ancestor == root:
            break
    if not resolved.is_file():
        raise ValueError(f"Missing regular asset file: {value}")
    return resolved


def _unique(items, label):
    result = {}
    for item in items:
        if item["id"] in result:
            raise ValueError(f"Duplicate {label} id: {item['id']}")
        result[item["id"]] = item
    return result


def validate_case(case, suite_root, case_dir=None):
    """Validate schema, provenance, actual prompt requirements and atom timing."""
    validate_document(case, "case")
    turns = case["turns"]
    _unique(turns, "turn")
    assets = _unique(case["assets"], "asset")
    for asset in assets.values():
        path = checked_file(suite_root, asset["path"], case_dir)
        if content_hash(path.read_bytes()) != asset["sha256"]:
            raise ValueError(f"Asset hash mismatch: {asset['id']}")
    required = _unique(case["requirements"], "requirement")
    for requirement in required.values():
        turn = requirement["turn"]
        if turn > len(turns) or requirement["quote"] not in turns[turn - 1]["prompt"]:
            raise ValueError(f"Unaligned requirement: {requirement['id']}")
    artifacts = []
    for turn in turns:
        if not set(turn["attachments"]).issubset(assets):
            raise ValueError("A turn refers to an undeclared attachment")
        names = [a["path"] for a in turn["artifacts"]]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate artifact path in a turn")
        for name in names:
            artifact_path(name)
        artifacts.append(set(names))
    atoms = _unique(case["atoms"], "atom")
    for atom in atoms.values():
        if not set(atom["requirement_ids"]).issubset(required):
            raise ValueError("An atom refers to an unknown requirement")
        introduced = max(required[r]["turn"] for r in atom["requirement_ids"])
        for turn in atom["active_turns"]:
            if turn < introduced or turn > len(turns):
                raise ValueError(f"Invalid activation turn for atom {atom['id']}")
            if not set(atom["evidence"]["required_artifacts"]).issubset(artifacts[turn - 1]):
                raise ValueError(f"Undeclared evidence artifact for {atom['id']}")
        if not set(atom["depends_on"]).issubset(atoms):
            raise ValueError("An atom depends on an unknown atom")
    visiting, visited = set(), set()

    def walk(identifier):
        if identifier in visiting:
            raise ValueError("Atom dependency cycle")
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in atoms[identifier]["depends_on"]:
            walk(dependency)
            if min(atoms[dependency]["active_turns"]) > min(atoms[identifier]["active_turns"]):
                raise ValueError("Dependency evidence activates after its dependent atom")
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in atoms:
        walk(identifier)
    limits = case["limits"]
    if limits["max_file_bytes"] > limits["max_workspace_bytes"]:
        raise ValueError("File limit exceeds workspace limit")
    from .observation_plans import validate_plans
    validate_plans(case)
    return case


def load_suite(suite_path):
    """Load frozen task definitions; callers print identities, not holdout prompts."""
    suite_path = Path(suite_path).resolve()
    root = suite_path.parent
    suite = json.loads(suite_path.read_text())
    if suite.get("schema_version") != 2 or not isinstance(suite.get("cases"), list):
        raise ValueError("Unsupported suite contract")
    loaded, ids = [], set()
    for entry in suite["cases"]:
        path = checked_file(root, entry["path"])
        if content_hash(path.read_bytes()) != entry["sha256"]:
            raise ValueError("Case hash differs from the frozen suite")
        case = json.loads(path.read_text())
        validate_case(case, root, path.parent)
        if case["id"] in ids:
            raise ValueError("Duplicate case id in suite")
        ids.add(case["id"])
        loaded.append({**case, "_case_path": str(path), "_suite_root": str(root),
                       "_case_sha256": entry["sha256"]})
    return {**suite, "cases": loaded, "_suite_path": str(suite_path),
            "_suite_sha256": content_hash(suite_path.read_bytes())}
