"""Frozen interventions and counterbalanced trial schedules."""

import copy
import hashlib
import json
from pathlib import Path
import random
import subprocess
import platform
import time

from .contracts import checked_file, content_hash, json_hash, load_suite, validate_document
from .store import encoded, private_directory, write_immutable


def trial_schedule(case_ids, arms, repeats, seed):
    """Balance arm positions across repeat blocks without a provider-seed claim."""
    if not case_ids or not arms or repeats < 1:
        raise ValueError("Cases, arms and positive repeats are required")
    if len(set(case_ids)) != len(case_ids) or len(set(arms)) != len(arms):
        raise ValueError("Duplicate case or arm")
    base = list(arms)
    random.Random(seed).shuffle(base)
    rows = []
    for repeat in range(repeats):
        for case_index, case_id in enumerate(case_ids):
            shift = (repeat + case_index) % len(base)
            for arm in base[shift:] + base[:shift]:
                rows.append({"trial_id": f"{case_id}--r{repeat + 1:03}--{arm}",
                             "case_id": case_id, "arm": arm, "repeat": repeat + 1})
    return rows


def backend(identifier):
    if identifier in ("local-codex", "local_codex"):
        from .backends.local_codex import LocalCodexBackend
        return LocalCodexBackend()
    if identifier == "harbor":
        from .backends.harbor import HarborBackend
        return HarborBackend()
    raise ValueError("Unknown backend")


def freeze_skill(source, destination, maximum=8 * 1024 * 1024):
    """Freeze logical bytes, excluding interpreter-generated caches only."""
    source = Path(source).resolve()
    if not (source / "SKILL.md").is_file():
        raise ValueError("A supplied skill must contain SKILL.md")
    hashes = {}
    for path in sorted(source.rglob("*")):
        rel = path.relative_to(source)
        if "__pycache__" in rel.parts or path.suffix in (".pyc", ".pyo"):
            continue
        if path.is_symlink():
            raise ValueError("A skill resource cannot be a symbolic link")
        if path.is_dir():
            continue
        if not path.is_file() or path.stat().st_nlink != 1:
            raise ValueError("A skill resource must be a regular, unlinked file")
        data = path.read_bytes()
        if len(data) > maximum:
            raise ValueError("A skill resource exceeds its file limit")
        target = Path(destination) / rel
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with target.open("xb") as handle:
            handle.write(data)
        target.chmod(0o600)
        hashes[rel.as_posix()] = content_hash(data)
    identity = content_hash(json.dumps(hashes, sort_keys=True).encode())
    return {"skill_hash": identity, "logical_files": len(hashes), "files": hashes}


def prepare_experiment(suite_path, output, *, selected=None, arms=None, repeats=1,
                       max_calls=12, wall_seconds=5400, timeout=600, seed=20261009,
                       backend_id="local-codex", renderer=None,
                       model="gpt-6.1-sol", effort="low", commit_provenance=None,
                       browser=None, blender=None):
    """Create a new private experiment; no model or generated program runs."""
    if model != "gpt-6.1-sol" or effort != "low":
        raise ValueError("This release verifies gpt-6.1-sol/low only")
    if not 1 <= repeats <= 3 or not 1 <= max_calls <= 54 or not 1 <= wall_seconds <= 10800 or not 1 <= timeout <= 600:
        raise ValueError("Experiment exceeds the first-release execution limits")
    arms = arms or {}
    if not arms or not set(arms).issubset({"none", "previous", "candidate"}):
        raise ValueError("Supply one to three declared intervention arms")
    if arms.get("none") is not None:
        raise ValueError("The without-skill arm cannot contain a skill")
    if any(source is None for identifier, source in arms.items() if identifier != "none"):
        raise ValueError("Previous and candidate arms require a supplied skill")
    suite = load_suite(suite_path)
    selected = selected or [c["id"] for c in suite["cases"] if c["split"] == "development"]
    cases = [c for c in suite["cases"] if c["id"] in selected]
    if not cases or len(cases) != len(selected):
        raise ValueError("Unknown or duplicate selected case")
    schedule = trial_schedule([c["id"] for c in cases], list(arms), repeats, seed)
    call_count = sum(len(c["turns"]) for c in cases) * len(arms) * repeats
    if call_count > max_calls:
        raise ValueError("The frozen schedule exceeds its invocation budget")
    execution = backend(backend_id)
    capability = execution.capabilities
    unsupported = {c["id"]: [v for v in c["capabilities"] if not capability.get(v)] for c in cases}
    unsupported = {k: v for k, v in unsupported.items() if v}
    if unsupported:
        raise ValueError(f"Unsupported case capabilities: {unsupported}")
    from .visual_runtime import discover, DEFAULT_BROWSER_SCENARIO
    tools = discover({'browser': browser, 'blender': blender},
                     {value for case in cases for value in case['capabilities']})
    root = private_directory(output, must_be_new=True)
    package = Path(__file__).parent
    framework = {}
    paths = [p for p in package.rglob('*') if p.is_file() and (p.suffix == '.py' or 'vendor' in p.relative_to(package).parts)]
    for path in sorted(paths):
        rel = path.relative_to(package)
        data = path.read_bytes()
        target = root / 'framework' / rel
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.write_bytes(data)
        target.chmod(0o600)
        framework[rel.as_posix()] = content_hash(data)
    frozen_arms = []
    for identifier, source in arms.items():
        identity = freeze_skill(source, root / "skills" / identifier) if source else {"skill_hash": None, "logical_files": 0, "files": {}}
        frozen_arms.append({"id": identifier, **identity,
                            "skill_snapshot": "skills/" + identifier if source else None})
    frozen_cases, case_hashes = [], {}
    for original in cases:
        case = copy.deepcopy({k: v for k, v in original.items() if not k.startswith("_")})
        if any(a['visibility'] == 'private' for a in case['assets']):
            case['visibility'] = 'private'
        for asset in case["assets"]:
            source = checked_file(original["_suite_root"], asset["path"], Path(original["_case_path"]).parent)
            relative = Path("assets") / case["id"] / (asset["id"] + source.suffix.lower())
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            target.write_bytes(source.read_bytes())
            target.chmod(0o600)
            asset["path"] = asset["snapshot"] = relative.as_posix()
        case["limits"]["turn_seconds"] = min(timeout, case["limits"]["turn_seconds"])
        frozen_cases.append(case)
        case_hashes[case["id"]] = {"source_sha256": original["_case_sha256"],
                                    "frozen_sha256": json_hash(case),
                                    "rubric_sha256": json_hash({"requirements": case["requirements"], "atoms": case["atoms"]})}
    renderer = Path(renderer or Path.home() / ".local/state/maintainall/art-creation-ab/runtime/cairo").resolve()
    runtime = {"backend": execution.id, "adapter_sha256": execution.fingerprint(),
               "renderer": str(renderer), "renderer_identity": renderer_identity(renderer),
               "platform": platform.platform(), "model": model, "effort": effort}
    if tools:
        runtime['visual_tools'] = tools
    backend_config = {'visual_tools': tools} if tools else {}
    if 'browser' in tools:
        backend_config['browser_capture_scenario'] = copy.deepcopy(DEFAULT_BROWSER_SCENARIO)
    manifest = {"schema_version": 1, "id": root.name, "created_epoch": time.time(),
                "mode": "explicit_skill_provision", "model": model, "effort": effort,
                "backend": execution.id, "backend_config": backend_config, "runtime": runtime,
                "fingerprint": json_hash(runtime), "suite_id": suite["id"],
                "framework_snapshot": {"path": "framework", "files": framework, "sha256": json_hash(framework)},
                "suite_sha256": suite["_suite_sha256"], "case_hashes": case_hashes,
                "cases": frozen_cases, "arms": frozen_arms, "schedule": schedule,
                "order_seed": seed, "provider_sampling_seed": None, "repeats": repeats,
                "limits": {"max_calls": max_calls, "planned_calls": call_count,
                           "wall_seconds": wall_seconds, "turn_seconds": timeout},
                "mechanical_verifier": {"sha256": json_hash({name: content_hash(Path(__file__).with_name(name).read_bytes()) for name in ('grading.py', 'runner.py')}),
                                        "reopen_sources": False, "source_verifier_sha256": None},
                "limitations": ["Model service revision, provider request count and monetary cost are unknown.",
                                "Explicit provision does not measure automatic skill discovery.",
                                "Repeated atom-turn ratings are not independent task samples."]}
    if commit_provenance is not None:
        # Commit identity is frozen with the generation inputs, never inferred
        # from a later report's checkout or from an experiment's display name.
        manifest["commit_provenance"] = dict(commit_provenance)
    validate_document(manifest, "experiment")
    seal = write_immutable(root / "manifest.json", manifest)
    write_immutable(root / "manifest-seal.json", {"sha256": seal})
    return manifest


def load_experiment(root):
    root = Path(root).resolve()
    raw = checked_file(root, "manifest.json").read_bytes()
    seal = json.loads(checked_file(root, "manifest-seal.json").read_text())
    if content_hash(raw) != seal["sha256"]:
        raise ValueError("Frozen manifest seal mismatch")
    manifest = json.loads(raw)
    validate_document(manifest, "experiment")
    snapshot = manifest.get('framework_snapshot')
    if snapshot:
        location = root / snapshot['path']
        if location.is_symlink() or not location.is_dir():
            raise ValueError('Frozen framework directory changed')
        entries = list(location.rglob('*'))
        if any(p.is_symlink() for p in entries):
            raise ValueError('Frozen framework contains a symbolic link')
        names = {p.relative_to(location).as_posix() for p in entries if not p.is_dir()}
        if names != set(snapshot['files']) or json_hash(snapshot['files']) != snapshot['sha256']:
            raise ValueError('Frozen framework inventory changed')
        for name, expected in snapshot['files'].items():
            if content_hash(checked_file(root, name, location).read_bytes()) != expected:
                raise ValueError('Frozen framework content changed')
    for case in manifest["cases"]:
        if json_hash(case) != manifest["case_hashes"][case["id"]]["frozen_sha256"]:
            raise ValueError("Frozen case content changed")
        for asset in case["assets"]:
            if content_hash(checked_file(root, asset["path"]).read_bytes()) != asset["sha256"]:
                raise ValueError("Frozen input changed")
    for arm in manifest["arms"]:
        if arm["skill_snapshot"]:
            location = root / arm["skill_snapshot"]
            actual = {p.relative_to(location).as_posix(): content_hash(p.read_bytes())
                      for p in location.rglob("*") if p.is_file()}
            if any(p.is_symlink() for p in location.rglob("*")) or actual != arm["files"]:
                raise ValueError("Frozen skill content changed")
    return manifest


def renderer_identity(renderer):
    """Fingerprint trusted renderer packages without executing solver programs."""
    executable = Path(renderer) / "bin/python"
    if not executable.is_file():
        return {"available": False}
    script = "import sys,json,importlib.metadata as m; print(json.dumps({'python':sys.version,'packages':{d.metadata['Name']:d.version for d in m.distributions()}},sort_keys=True))"
    value = subprocess.run([str(executable), "-I", "-c", script], capture_output=True,
                           text=True, timeout=20, check=True)
    return {"available": True, "sha256": content_hash(value.stdout.encode()),
            "python_executable_sha256": content_hash(executable.read_bytes())}
