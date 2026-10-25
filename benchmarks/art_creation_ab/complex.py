#!/usr/bin/env python3
"""Reference-based, real multi-turn art comparisons with private human rubrics."""

import argparse
import binascii
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import random
import re
import shutil
import struct
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET

SPEC = importlib.util.spec_from_file_location("art_complex_feedback", Path(__file__).with_name("feedback.py"))
feedback = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(feedback)
core = feedback.core
DEFAULT_RENDERER = feedback.DEFAULT_RENDERER
MAX_FILE = 8 * 1024 * 1024
MAX_WORKSPACE = 32 * 1024 * 1024
FORMATS = {"svg", "png", "html", "py", "json"}


def safe_path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("Artifact paths must be explicit relative POSIX paths.")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"..", ".", "skill", "inputs", ".codex", ".git"} for part in path.parts):
        raise ValueError("Artifact paths cannot escape or overwrite supplied inputs.")
    return path.as_posix()


def private_path(value):
    path = Path(value).resolve()
    if path.exists() or path.is_relative_to(core.ROOT) or any((parent / ".git").exists() for parent in path.parents):
        raise ValueError("Use a new private output directory outside all repositories.")
    return path


def png_info(data):
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("PNG signature is missing.")
    offset, dimensions, idat, ended = 8, None, False, False
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("Truncated PNG chunk.")
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(data):
            raise ValueError("Truncated PNG data.")
        payload = data[offset + 8:offset + 8 + length]
        crc = struct.unpack(">I", data[end - 4:end])[0]
        if crc != binascii.crc32(kind + payload) & 0xffffffff:
            raise ValueError("PNG chunk CRC is invalid.")
        if dimensions is None:
            if kind != b"IHDR" or length != 13:
                raise ValueError("PNG must start with IHDR.")
            dimensions = struct.unpack(">II", payload[:8])
            if not all(0 < value <= 16384 for value in dimensions):
                raise ValueError("PNG dimensions exceed this fixture limit.")
        elif kind == b"IHDR":
            raise ValueError("Duplicate PNG header.")
        if kind == b"IDAT":
            idat |= bool(length)
        if kind == b"IEND":
            ended = length == 0 and end == len(data)
            break
        offset = end
    if dimensions is None or not idat or not ended:
        raise ValueError("PNG requires image data and a complete terminal IEND.")
    return {"width": dimensions[0], "height": dimensions[1]}


def image_format(data, suffix):
    if suffix == ".png":
        png_info(data)
    elif suffix in {".jpg", ".jpeg"}:
        if not data.startswith(b"\xff\xd8\xff") or not data.endswith(b"\xff\xd9"):
            raise ValueError("JPEG input container is invalid.")
    elif suffix == ".webp":
        if not (data[:4] == b"RIFF" and data[8:12] == b"WEBP"):
            raise ValueError("WebP input container is invalid.")
    else:
        raise ValueError("Reference inputs must be PNG, JPEG or WebP.")


def load_card(path):
    path = Path(path).resolve()
    card = json.loads(path.read_text())
    if card.get("schema_version") != 1 or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", card.get("id", "")):
        raise ValueError("The task card identity or schema version is invalid.")
    limits = card.get("limits", {})
    for name, low, high in (("timeout_seconds", 30, 600), ("per_file_bytes", 1024, MAX_FILE), ("workspace_bytes", 1024, MAX_WORKSPACE)):
        if type(limits.get(name)) is not int or not low <= limits[name] <= high:
            raise ValueError("Invalid task limit: " + name)
    if limits["per_file_bytes"] > limits["workspace_bytes"]:
        raise ValueError("A file ceiling cannot exceed the workspace ceiling.")
    assets, metadata = {}, []
    attachments = card.get("attachments", [])
    if not isinstance(attachments, list) or not 1 <= len(attachments) <= 8:
        raise ValueError("Use one to eight explicitly declared reference images.")
    for item in attachments:
        identifier = item.get("id", "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", identifier) or identifier in assets:
            raise ValueError("Attachment IDs must be unique and portable.")
        original = Path(item.get("path", ""))
        if original.is_absolute() or not str(original) or original == Path("."):
            raise ValueError("Attachment paths must be relative to their task card.")
        source = path.parent / original
        if source.is_symlink() or not source.is_file() or source.stat().st_nlink != 1:
            raise ValueError("Input images must be regular files without links.")
        if source.stat().st_size > limits["per_file_bytes"]:
            raise ValueError("Input image exceeds the file ceiling.")
        data = source.read_bytes()
        if core.sha(data) != item.get("sha256"):
            raise ValueError("Input image hash differs from the task card.")
        if not all(isinstance(item.get(key), str) and item[key].strip() for key in ("source", "license")):
            raise ValueError("Reference source and license are required.")
        suffix = source.suffix.lower()
        image_format(data, suffix)
        destination = "inputs/" + identifier + suffix
        assets[identifier] = data
        metadata.append({**item, "staged_path": destination, "bytes": len(data)})
    rounds = card.get("rounds", [])
    if not isinstance(rounds, list) or not 2 <= len(rounds) <= 3:
        raise ValueError("Task cards declare two or three actual conversation rounds.")
    for phase in rounds:
        if not isinstance(phase.get("prompt"), str) or not 1 <= len(phase["prompt"]) <= 16000:
            raise ValueError("Each round requires a bounded natural-language prompt.")
        selected = phase.get("attachments", [])
        if not isinstance(selected, list) or len(set(selected)) != len(selected) or any(item not in assets for item in selected):
            raise ValueError("A round references an unknown or duplicate attachment.")
        requirements = phase.get("required_artifacts", [])
        if not isinstance(requirements, list) or not 2 <= len(requirements) <= 32:
            raise ValueError("Each round needs explicit source and preview deliverables.")
        names, kinds = set(), set()
        for item in requirements:
            name = safe_path(item.get("path"))
            if name in names or item.get("format") not in FORMATS or item.get("kind") not in {"editable", "preview"}:
                raise ValueError("Invalid or repeated artifact declaration.")
            if Path(name).suffix != "." + item["format"] or (item["kind"] == "preview") != (item["format"] == "png"):
                raise ValueError("Preview artifacts are PNGs; editable sources use declared source formats.")
            for dimension in ("width", "height"):
                if dimension in item and (type(item[dimension]) is not int or not 0 < item[dimension] <= 16384 or item["format"] != "png"):
                    raise ValueError("Only PNGs may declare bounded pixel dimensions.")
            names.add(name)
            kinds.add(item["kind"])
        if kinds != {"editable", "preview"}:
            raise ValueError("Every round requires an editable source and a PNG preview.")
    rubric = card.get("rubric", [])
    if not isinstance(rubric, list) or not 1 <= len(rubric) <= 32 or len({item.get("id") for item in rubric}) != len(rubric):
        raise ValueError("A unique evaluator-only rubric is required.")
    for atom in rubric:
        if not isinstance(atom.get("criterion"), str) or set(atom.get("anchors", {})) != {"0", "1", "2"}:
            raise ValueError("Quality atoms need a criterion and explicit 0/1/2 anchors.")
        applicable = atom.get("applicable_turns", list(range(1, len(rounds) + 1)))
        if not isinstance(applicable, list) or not applicable or len(set(applicable)) != len(applicable) or any(type(turn) is not int or not 1 <= turn <= len(rounds) for turn in applicable):
            raise ValueError("Invalid applicable_turns in an evaluator-only quality atom.")
    return {**card, "attachments": metadata, "card_sha256": core.sha(path.read_bytes())}, assets


def skill_files(directory=None, commit=None, repository=core.ROOT):
    files, identity = core.source_files(directory=directory, commit=commit, repository=repository)
    excluded = [name for name in files if "__pycache__" in Path(name).parts or Path(name).suffix in {".pyc", ".pyo"}]
    files = {name: data for name, data in files.items() if name not in excluded}
    identity.update({"files": {name: core.sha(data) for name, data in files.items()}, "excluded_generated_files": excluded})
    identity["sha256"] = core.sha(json.dumps(identity["files"], sort_keys=True).encode())
    return files, identity


def environment(renderer):
    return ("Offline tools: /usr/bin/python3 and an isolated static SVG renderer, " + str(renderer / "bin/python") +
            " -m cairosvg INPUT.svg -o OUTPUT.png. PNG image inspection is available. No browser playback or production avatar importer is configured. "
            "Supplied inputs and skill files are read-only; command networking is disabled.\n")


def prompt(card, turn, renderer):
    phase = card["rounds"][turn - 1]
    references = ", ".join(item["staged_path"] for item in card["attachments"])
    return phase["prompt"] + "\n\nRead skill/SKILL.md and only applicable supporting resources. " + environment(renderer) + "Reference files: " + references


def command(executable, package, workspace, renderer, final, attachments, thread=None):
    args = [executable, "--no-daemon", "--cd", str(workspace), *core.config_args(package, renderer=renderer, readonly_inputs=True), "exec"]
    if thread:
        uuid.UUID(thread)
        args.append("resume")
    for path in attachments:
        args.extend(["--image", str(path)])
    args.extend(["--ignore-user-config", "--ignore-rules", "--skip-git-repo-check", "--json", "--model", core.MODEL,
                 "--output-last-message", str(final), "--"])
    if thread:
        args.append(thread)
    return args + ["-"]


def inventory(workspace, limits):
    files, violations, total = [], [], 0
    for path in workspace.rglob("*"):
        relative = path.relative_to(workspace).as_posix()
        if path.is_symlink():
            violations.append({"path": relative, "reason": "symlink"})
        elif path.is_file():
            stat = path.stat()
            total += stat.st_size
            files.append({"path": relative, "bytes": stat.st_size})
            if stat.st_size > limits["per_file_bytes"] or stat.st_nlink != 1:
                violations.append({"path": relative, "reason": "file ceiling or hardlink"})
        elif not path.is_dir():
            violations.append({"path": relative, "reason": "special file"})
        if len(files) > 5000:
            violations.append({"reason": "file count exceeds bounded fixture support"})
            break
    if total > limits["workspace_bytes"]:
        violations.append({"reason": "workspace byte ceiling", "bytes": total})
    return {"files": files, "bytes": total, "violations": violations, "passed": not violations}


def capture(workspace, destination, limits):
    state = inventory(workspace, limits)
    destination.mkdir()
    records = []
    for item in state["files"]:
        if Path(item["path"]).parts[0] in {"skill", "inputs"}:
            continue
        path = workspace / item["path"]
        if not state["passed"]:
            records.append({**item, "capture_status": "rejected_due_to_workspace_violation"})
            continue
        target = destination / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        records.append({**item, "sha256": core.sha(target.read_bytes()), "capture_status": "copied"})
    return {**state, "artifacts": records}


def artifact_checks(artifacts, phase):
    checks = []
    for requirement in phase["required_artifacts"]:
        path = artifacts / requirement["path"]
        record = {"path": requirement["path"], "kind": requirement["kind"], "passed": False}
        try:
            if path.is_symlink() or not path.is_file():
                raise ValueError("Required artifact is missing or a link.")
            data = path.read_bytes()
            record.update({"sha256": core.sha(data), "bytes": len(data)})
            if requirement["format"] == "png":
                dimensions = png_info(data)
                record.update(dimensions)
                if any(dimensions[key] != requirement[key] for key in ("width", "height") if key in requirement):
                    raise ValueError("Preview dimensions differ from the delivery contract.")
            elif requirement["format"] == "svg":
                if re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", data, re.I) or ET.fromstring(data).tag.split("}")[-1] != "svg":
                    raise ValueError("Invalid SVG container or unsafe declarations.")
            elif requirement["format"] == "json":
                json.loads(data)
            else:
                data.decode("utf-8")
            record["passed"] = bool(data)
        except (OSError, ValueError, ET.ParseError) as error:
            record["error"] = str(error)
        checks.append(record)
    return {"delivery_pass": all(item["passed"] for item in checks), "artifacts": checks,
            "quality_status": "unassessed", "quality_scores": None,
            "source_editability_verified": False, "note": "Container and delivery checks do not grade composition, relationships or aesthetic quality."}


def rollout_evidence(identifier, turn, workspace):
    base = feedback.image_evidence(identifier, turn=turn)
    root = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "sessions"
    files = list(root.glob("*/*/*/*" + identifier + ".jsonl"))
    active, user_images, calls, outputs = 0, 0, {}, {}
    def images(value):
        if isinstance(value, dict):
            return int(value.get("type") == "input_image") + sum(images(item) for item in value.values())
        if isinstance(value, list):
            return sum(images(item) for item in value)
        if isinstance(value, str) and value.startswith(("[", "{")):
            try:
                return images(json.loads(value))
            except ValueError:
                pass
        return 0
    for path in files:
        for line in path.read_text().splitlines():
            event = json.loads(line)
            payload = event.get("payload", {})
            if event.get("type") == "event_msg" and payload.get("type") == "task_started":
                active += 1
            if active != turn:
                continue
            if payload.get("type") == "message" and payload.get("role") == "user":
                user_images += images(payload.get("content", []))
            if payload.get("type") in {"function_call", "custom_tool_call"}:
                content = str(payload.get("input", payload.get("arguments", "")))
                if "view_image" not in content and payload.get("name", "").split(".")[-1] != "view_image":
                    continue
                paths = re.findall(r"[\"']path[\"']\s*:\s*[\"']([^\"']+)[\"']|\bpath\s*:\s*[\"']([^\"']+)[\"']", content)
                classes = []
                for match in paths:
                    value = next(item for item in match if item)
                    target = Path(value)
                    target = (target if target.is_absolute() else workspace / target).resolve()
                    if target.is_relative_to((workspace / "inputs").resolve()):
                        classes.append("reference")
                    elif target.is_relative_to(workspace.resolve()):
                        classes.append("artifact")
                    else:
                        classes.append("unclassified")
                calls[payload.get("call_id")] = classes or ["unclassified"]
            if payload.get("type") in {"function_call_output", "custom_tool_call_output"}:
                outputs[payload.get("call_id")] = images(payload.get("output", []))
    return {**base, "reference_input_image_items": user_images,
            "returned_view_call_classes": {name: sum(name in kinds and outputs.get(key, 0) > 0 for key, kinds in calls.items()) for name in ("reference", "artifact", "unclassified")},
            "inspection_classification_note": "Literal paths only; dynamic code paths remain unclassified. Input attachments are distinct from tool-image outputs."}


def verify_inputs(workspace, card):
    return all((workspace / item["staged_path"]).is_file() and not (workspace / item["staged_path"]).is_symlink()
               and core.sha((workspace / item["staged_path"]).read_bytes()) == item["sha256"] for item in card["attachments"])


def prepare(args):
    output, renderer = private_path(args.output), Path(args.renderer).resolve()
    cards, assets = [], {}
    for filename in args.task_card:
        card, payloads = load_card(filename)
        if any(previous["id"] == card["id"] for previous in cards):
            raise ValueError("Task identities must be unique.")
        cards.append(card)
        assets[card["id"]] = payloads
    planned = 2 * sum(len(card["rounds"]) for card in cards)
    if not 1 <= len(cards) <= 2 or not 1 <= args.max_cli_calls <= 12 or planned > args.max_cli_calls:
        raise ValueError("Use at most two tasks and at most twelve explicitly budgeted CLI calls.")
    sources = {arm: skill_files(directory=getattr(args, arm + "_dir"), commit=getattr(args, arm + "_commit"), repository=args.repo) for arm in ("old", "new")}
    output.mkdir(parents=True, mode=0o700)
    manifest = {"schema_version": 1, "state": "prepared", "model": core.MODEL, "effort": core.EFFORT, "codex_version": core.CLI_VERSION,
                "renderer": str(renderer), "max_cli_calls": args.max_cli_calls, "reserved_cli_calls": 0, "max_wall_seconds": 5400,
                "run_started_epoch": None, "cards": cards, "skills": {arm: value[1] for arm, value in sources.items()},
                "prompt_sha256": {card["id"]: [core.sha(prompt(card, turn, renderer).encode()) for turn in range(1, len(card["rounds"]) + 1)] for card in cards},
                "quality_status": "unassessed", "provider_snapshot": None, "seed": None, "currency_cost": None}
    manifest["cards_sha256"] = {card["id"]: core.sha(json.dumps(card, sort_keys=True).encode()) for card in cards}
    for arm, (files, _) in sources.items():
        for card in cards:
            workspace = output / arm / card["id"] / "workspace"
            workspace.mkdir(parents=True)
            for name, data in files.items():
                path = workspace / "skill" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            for item in card["attachments"]:
                path = workspace / item["staged_path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(assets[card["id"]][item["id"]])
            (workspace / "environment.txt").write_text(environment(renderer))
            if not inventory(workspace, card["limits"])["passed"]:
                raise ValueError("Prepared inputs and skills already exceed the declared workspace ceilings.")
    core.dump(output / "manifest.json", manifest)
    return {"manifest": str(output / "manifest.json"), "planned_cli_calls": planned, "skills": {arm: {"sha256": value[1]["sha256"], "logical_files": len(value[1]["files"])} for arm, value in sources.items()}, "model_called": False}


def load_manifest(output):
    manifest = json.loads((output / "manifest.json").read_text())
    if (manifest.get("model"), manifest.get("effort"), manifest.get("codex_version")) != (core.MODEL, core.EFFORT, core.CLI_VERSION):
        raise ValueError("Prepared runtime pins changed.")
    if not 1 <= manifest.get("max_cli_calls", 0) <= 12 or manifest.get("max_wall_seconds") != 5400:
        raise ValueError("The explicit experiment ceilings changed.")
    renderer = Path(manifest["renderer"])
    for card in manifest["cards"]:
        if manifest.get("cards_sha256", {}).get(card["id"]) != core.sha(json.dumps(card, sort_keys=True).encode()):
            raise ValueError("A frozen task card, limit or evaluator rubric changed.")
        if manifest["prompt_sha256"][card["id"]] != [core.sha(prompt(card, turn, renderer).encode()) for turn in range(1, len(card["rounds"]) + 1)]:
            raise ValueError("A frozen user input or environment changed.")
    return manifest


def rows(output):
    return [json.loads(path.read_text()) for path in sorted(output.glob("*/*/round*/result.json"))]


def run(args):
    output = Path(args.output).resolve()
    manifest = load_manifest(output)
    renderer = Path(manifest["renderer"])
    cards = [card for card in manifest["cards"] if args.task is None or card["id"] == args.task]
    if not cards:
        raise ValueError("The requested task is not in this experiment.")
    preflight = core.doctor(renderer=renderer, readonly_inputs=True)
    core.dump(output / ("preflight-" + args.arm + ".json"), preflight)
    executable, package = core.runtime()
    if manifest["run_started_epoch"] is None:
        manifest["run_started_epoch"] = time.time()
    deadline = manifest["run_started_epoch"] + manifest["max_wall_seconds"]
    manifest["state"] = "running"
    core.dump(output / "manifest.json", manifest)
    for card in cards:
        trial = output / args.arm / card["id"]
        workspace = trial / "workspace"
        identifier, previous_usage = None, None
        for turn, instructions in enumerate(card["rounds"], 1):
            if args.through_turn is not None and turn > args.through_turn:
                break
            phase = trial / ("round" + str(turn))
            if (phase / "result.json").exists():
                previous = json.loads((phase / "result.json").read_text())
                if previous["status"] != "completed":
                    break
                identifier, previous_usage = previous["thread_id"], previous["reported_cumulative_usage"]
                continue
            if phase.exists():
                raise ValueError("An interrupted phase has raw output; it cannot be retried automatically.")
            _, identity = skill_files(directory=workspace / "skill")
            if identity["sha256"] != manifest["skills"][args.arm]["sha256"] or not verify_inputs(workspace, card):
                raise ValueError("A frozen staged skill or input changed.")
            if time.time() >= deadline or manifest["reserved_cli_calls"] >= manifest["max_cli_calls"]:
                raise ValueError("The experiment reached its wall-clock or CLI-call ceiling.")
            phase.mkdir()
            manifest["reserved_cli_calls"] += 1
            core.dump(output / "manifest.json", manifest)
            paths = [workspace / next(item["staged_path"] for item in card["attachments"] if item["id"] == value) for value in instructions["attachments"]]
            started = time.monotonic()
            timeout = min(card["limits"]["timeout_seconds"], deadline - time.time())
            status = "completed"
            with (phase / "events.jsonl").open("w") as events, (phase / "stderr.log").open("w") as error:
                process = subprocess.Popen(command(executable, package, workspace, renderer, phase / "final.txt", paths, identifier), cwd=workspace,
                                           env=core.host_env(), stdin=subprocess.PIPE, stdout=events, stderr=error, text=True, start_new_session=True)
                first = True
                while True:
                    remaining = timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        status = "timeout"
                        core.stop(process)
                        break
                    try:
                        process.communicate(prompt(card, turn, renderer) if first else None, timeout=min(1, remaining))
                        break
                    except subprocess.TimeoutExpired:
                        first = False
                        if not inventory(workspace, card["limits"])["passed"]:
                            status = "workspace-limit"
                            core.stop(process)
                            break
            if process.returncode and status == "completed":
                status = "cli-error"
            captured = capture(workspace, phase / "artifacts", card["limits"])
            input_ok = verify_inputs(workspace, card)
            evidence, outcome, evaluation_error = {}, artifact_checks(phase / "artifacts", instructions), None
            try:
                current = feedback.thread_id(phase / "events.jsonl")
                if identifier and identifier != current:
                    raise ValueError("Resume returned a different conversation ID.")
                identifier = current
                evidence = rollout_evidence(identifier, turn, workspace)
                if paths and evidence["reference_input_image_items"] < len(paths):
                    status = "input-evidence-missing"
                if not input_ok or not captured["passed"]:
                    status = "input-changed" if not input_ok else "workspace-limit"
            except (ValueError, OSError, TypeError) as error:
                evaluation_error = str(error)
                status = "evidence-error"
            raw = core.usage(phase / "events.jsonl")
            if raw["usage_status"] != "reported_by_cli" and status == "completed":
                status = "usage-evidence-missing"
            row = {"arm": args.arm, "task": card["id"], "turn": turn, "status": status, "exit_code": process.returncode,
                   "elapsed_seconds": time.monotonic() - started, "thread_id": identifier,
                   "usage": feedback.turn_usage(raw, previous_usage), "reported_cumulative_usage": raw,
                   "reference_attachments": [{"id": item["id"], "sha256": item["sha256"]} for item in card["attachments"] if item["id"] in instructions["attachments"]],
                   "inputs_unchanged": input_ok, "image_evidence": evidence, "outcome": outcome,
                   "capture": captured, "evaluation_error": evaluation_error}
            core.dump(phase / "result.json", row)
            core.dump(output / "summary.json", {"results": rows(output), "quality_status": "unassessed", "currency_cost": None})
            print(json.dumps({key: row[key] for key in ("task", "turn", "status", "elapsed_seconds")}), flush=True)
            previous_usage = raw
            if status != "completed":
                raise ValueError("Stopped this execution path after " + status + "; raw output is preserved and no model retry is allowed.")
    return {"actual_cli_calls": len(rows(output)), "reserved_cli_calls": manifest["reserved_cli_calls"], "quality_status": "unassessed"}


def preservation(card, task_rows):
    if any(row["task"] != card["id"] for row in task_rows) or len({row["arm"] for row in task_rows}) > 1:
        raise ValueError("Preservation comparisons require exactly one task and arm.")
    comparisons = []
    by_turn = {row["turn"]: row for row in task_rows}
    for turn in range(2, len(card["rounds"]) + 1):
        if turn not in by_turn or turn - 1 not in by_turn:
            continue
        before = {item["path"]: item.get("sha256") for item in by_turn[turn - 1]["outcome"]["artifacts"]}
        for item in by_turn[turn]["outcome"]["artifacts"]:
            comparisons.append({"turn": turn, "path": item["path"], "same_as_previous": bool(item.get("sha256")) and item.get("sha256") == before.get(item["path"])})
    return comparisons


def applicable_atoms(task, turn):
    return [atom for atom in task["rubric"] if turn in atom.get("applicable_turns", list(range(1, len(task.get("rounds", task.get("prompts", []))) + 1)))]


def check(args):
    output = Path(args.output).resolve()
    manifest = load_manifest(output)
    results = rows(output)
    return {"results": [{key: row[key] for key in ("arm", "task", "turn", "status", "outcome", "image_evidence", "usage", "elapsed_seconds")} for row in results],
            "hash_comparisons": {arm + "/" + card["id"]: preservation(card, [row for row in results if row["arm"] == arm and row["task"] == card["id"]]) for arm in ("old", "new") for card in manifest["cards"]},
            "quality_status": "unassessed", "quality_scores": None}


def blind_export(args):
    output, destination = Path(args.output).resolve(), private_path(args.dest)
    manifest = load_manifest(output)
    destination.mkdir(mode=0o700, parents=True)
    entries, mapping = [], {}
    pairs = [(arm, card) for arm in ("old", "new") for card in manifest["cards"]]
    random.SystemRandom().shuffle(pairs)
    for arm, card in pairs:
        identifier = uuid.uuid4().hex[:12]
        entry = {"id": identifier, "task": card["id"], "turns": []}
        mapping[identifier] = {"arm": arm, "task": card["id"]}
        for turn in range(1, len(card["rounds"]) + 1):
            phase = output / arm / card["id"] / ("round" + str(turn))
            if not (phase / "result.json").is_file():
                continue
            result = json.loads((phase / "result.json").read_text())
            target = destination / identifier / ("round" + str(turn))
            target.mkdir(parents=True)
            previews = []
            for index, requirement in enumerate(card["rounds"][turn - 1]["required_artifacts"], 1):
                source = phase / "artifacts" / requirement["path"]
                if requirement["kind"] == "preview" and source.is_file() and not source.is_symlink():
                    name = "preview-" + str(index) + ".png"
                    shutil.copyfile(source, target / name)
                    previews.append({"path": (target / name).relative_to(destination).as_posix(), "deliverable": requirement["path"]})
            notes = phase / "artifacts/notes.md"
            if notes.is_file() and not notes.is_symlink():
                shutil.copyfile(notes, target / "notes.md")
            entry["turns"].append({"turn": turn, "previews": previews, "notes": (target / "notes.md").relative_to(destination).as_posix() if notes.is_file() else None,
                                   "image_evidence": {key: value for key, value in result["image_evidence"].items() if key != "note"},
                                   "artifact_hash_comparisons": [item for item in preservation(card, [row for row in rows(output) if row["arm"] == arm and row["task"] == card["id"]]) if item["turn"] == turn]})
        entries.append(entry)
    tasks = []
    for card in manifest["cards"]:
        references = []
        for item in card["attachments"]:
            target = destination / "references" / card["id"] / Path(item["staged_path"]).name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(output / "old" / card["id"] / "workspace" / item["staged_path"], target)
            references.append({"id": item["id"], "path": target.relative_to(destination).as_posix(), "source": item["source"], "license": item["license"], "sha256": item["sha256"]})
        tasks.append({"id": card["id"], "prompts": [phase["prompt"] for phase in card["rounds"]], "rubric": card["rubric"], "references": references})
    packet = {"schema_version": 1, "tasks": tasks, "entries": entries, "quality_status": "unassessed", "allowed_scores": [0, 1, 2, "unverifiable"],
              "note": "Human review only. Container validity and agent self-evaluation do not assign quality scores. Notes may reveal process choices; arm mapping is separate."}
    core.dump(destination / "review.json", packet)
    core.dump(destination / "ratings.json", {"reviewer": None, "ratings": [{"entry": entry["id"], "turn": phase["turn"], "atom": atom["id"], "score": None, "evidence": ""} for entry in entries for phase in entry["turns"] for atom in applicable_atoms(next(card for card in manifest["cards"] if card["id"] == entry["task"]), phase["turn"])]})
    map_path = output / ("blind-map-" + destination.name + ".json")
    core.dump(map_path, mapping)
    return {"packet": str(destination / "review.json"), "ratings": str(destination / "ratings.json"), "entries": [{"id": item["id"], "task": item["task"], "turns": [phase["turn"] for phase in item["turns"]]} for item in entries], "arm_mapping_returned": False}


def validate_scores(args):
    packet = json.loads((Path(args.packet) / "review.json").read_text())
    ratings = json.loads(Path(args.scores).read_text())
    expected = {(entry["id"], phase["turn"], atom["id"]) for entry in packet["entries"] for phase in entry["turns"] for atom in applicable_atoms(next(task for task in packet["tasks"] if task["id"] == entry["task"]), phase["turn"])}
    seen = set()
    for item in ratings.get("ratings", []):
        key = (item.get("entry"), item.get("turn"), item.get("atom"))
        value = item.get("score")
        if key not in expected or key in seen or (value is not None and not ((type(value) is int and value in {0, 1, 2}) or value == "unverifiable")):
            raise ValueError("Ratings contain an unknown/duplicate atom or invalid manual score.")
        if value is not None and not item.get("evidence"):
            raise ValueError("A manual rating needs visible evidence or an unverifiable reason.")
        seen.add(key)
    if seen != expected:
        raise ValueError("Ratings omit expected quality atoms.")
    return {"valid": True, "rated": sum(item.get("score") is not None for item in ratings["ratings"]), "atoms": len(expected), "quality_status": "manual_review" if any(item.get("score") is not None for item in ratings["ratings"]) else "unassessed", "automatic_quality_pass": None}


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="Probe read-only input assets and existing isolation without model calls.")
    doctor.add_argument("--renderer", default=str(DEFAULT_RENDERER))
    staging = commands.add_parser("prepare", help="Freeze trusted task cards, input images and both skill snapshots.")
    for arm in ("old", "new"):
        sources = staging.add_mutually_exclusive_group(required=True)
        sources.add_argument("--" + arm + "-dir")
        sources.add_argument("--" + arm + "-commit")
    staging.add_argument("--repo", default=str(core.ROOT))
    staging.add_argument("--task-card", action="append", required=True)
    staging.add_argument("--renderer", default=str(DEFAULT_RENDERER))
    staging.add_argument("--output", required=True)
    staging.add_argument("--max-cli-calls", type=int, required=True)
    execute = commands.add_parser("run", help="Run or continue an exact-ID conversation; never retry a completed/failed call.")
    execute.add_argument("--output", required=True)
    execute.add_argument("--arm", choices=("old", "new"), required=True)
    execute.add_argument("--task")
    execute.add_argument("--through-turn", type=int, choices=(1, 2, 3))
    execute.add_argument("--execute", action="store_true", required=True)
    checking = commands.add_parser("check", help="Return delivery evidence and hashes; leave quality unassessed.")
    checking.add_argument("--output", required=True)
    exporting = commands.add_parser("blind-export", help="Export anonymous image entries and blank manual quality ratings.")
    exporting.add_argument("--output", required=True)
    exporting.add_argument("--dest", required=True)
    scoring = commands.add_parser("validate-scores", help="Validate manual 0/1/2/unverifiable ratings without scoring art.")
    scoring.add_argument("--packet", required=True)
    scoring.add_argument("--scores", required=True)
    args = parser.parse_args()
    try:
        result = core.doctor(renderer=Path(args.renderer), readonly_inputs=True) if args.command == "doctor" else globals()[args.command.replace("-", "_")](args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
