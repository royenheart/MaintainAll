#!/usr/bin/env python3
"""Two real feedback turns in a private, exact-ID Codex conversation."""

import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET

SPEC = importlib.util.spec_from_file_location("art_ab_core", Path(__file__).with_name("run.py"))
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)
DEFAULT_RENDERER = Path.home() / ".local/state/maintainall/art-creation-ab/runtime/cairo"
TASKS = {
    "fashion-feedback": [
        "Explore two visibly different original airy outfit silhouettes for a virtual character, with an attached waist ribbon. "
        "Use editable 320 by 240 SVGs and accent #58dcff. Live2D versus VRM is undecided, and no target importer or production backend is configured. "
        "I have not selected either direction. Keep each outfit, its hem, and its attached ribbon editable. "
        "For inspectable object identity, use outfit-a/hem-a/ribbon-a IDs in direction a and outfit-b/hem-b/ribbon-b in b; the ribbon must belong to its outfit group.",
        "I choose direction a only for its overall silhouette and color identity. This does not approve the hem fullness, "
        "ribbon motion, production construction, or target delivery. Keep the color identity, waist ribbon object, "
        "and its attachment to the same outfit. Make only the hem fuller, which remains an unaccepted revision. "
        "Keep the original unselected b file unchanged. Save the revised chosen SVG as selected.svg. "
        "In brief.json set selected_direction to a and confirmed_preferences to exactly [silhouette, color_identity]; "
        "keep other decisions pending. Render and inspect the revised preview before reporting the result.",
    ],
    "source-motion": [
        "Explore two original turning ribbon motion directions on a 320 by 240 stage with accent #58dcff. "
        "The ribbon's own editable path geometry must bend over time; moving a separate glow or decoration does not satisfy that. "
        "Keep a two-second cycle and an identifiable ribbon-a/ribbon-b source object. I have not selected a direction. "
        "Provide an editable generate.py that generates actual source SVG samples at 0 and 0.5 seconds, "
        "frames/a-0.svg and frames/a-1.svg, plus two direction previews. Include motion-preview.html if playable. "
        "mechanism.json must identify the source object, driven property, sample times, cycle_seconds, and actual playback_status. "
        "If live playback cannot be verified with the available tools, explicitly report sampled-frame fallback rather than claiming playback.",
        "I choose direction a only for the turning direction of its source ribbon. This does not approve amplitude, "
        "background, overall style, or final delivery. Keep the same source object, cycle duration, canvas, and accent identity. "
        "Reduce only its bending amplitude, which remains an unaccepted revision. Regenerate frames/a-0.svg and frames/a-1.svg "
        "at the same times and save selected.svg. Keep the original unselected b file unchanged. "
        "In brief.json set selected_direction to a and confirmed_preferences to exactly [motion_direction]; keep other decisions pending. "
        "Render and inspect the revised source frames, and distinguish sampled deformation from verified continuous playback.",
    ],
}
CONTRACT = (
    "Read skill/SKILL.md first and only relevant resources; do not install software, use the network, or modify skill/. "
    "For the first turn, write preview-a.svg, preview-b.svg, brief.json and rendered preview-a.png/preview-b.png. "
    "brief.json uses intent_hypotheses, alternatives (objects with ids a/b), confirmed_preferences, pending_preferences, "
    "and capability_limits lists; initial confirmed_preferences must be empty. "
    "For later turns keep the brief current and render selected.png. Use the image-viewing tool to inspect actual rendered files. "
    "Record limitations honestly. Available rendering tools are described in environment.txt."
)


def environment(renderer):
    return ("Offline static renderer: " + str(renderer / "bin/python") + " -m cairosvg INPUT.svg -o OUTPUT.png. "
            "CairoSVG 2.9.0 and its isolated runtime are readable; it renders static SVG, not JavaScript or continuous playback. "
            "The image-viewing tool can inspect workspace PNGs. Chrome cannot start under this profile's strict network syscall filter. "
            "No browser, production importer, or live playback is validated. Keep HOME/CODEX_HOME and host files inaccessible.\n")


def prompt(task, turn, renderer):
    return TASKS[task][turn - 1] + "\n\n" + CONTRACT + "\n\n" + environment(renderer)


def command(executable, package, workspace, renderer, final, thread=None):
    args = [executable, "--no-daemon", "--cd", str(workspace), *core.config_args(package, renderer=renderer), "exec"]
    if thread:
        uuid.UUID(thread)
        args.append("resume")
    args.extend(["--ignore-user-config", "--ignore-rules", "--skip-git-repo-check", "--json", "--model", core.MODEL,
                 "--output-last-message", str(final)])
    if thread:
        args.append(thread)
    return args + ["-"]


def thread_id(events):
    identifiers = []
    for line in Path(events).read_text().splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "thread.started":
            value = event.get("thread_id")
            uuid.UUID(value)
            identifiers.append(value)
    if len(set(identifiers)) != 1:
        raise ValueError("No unique thread ID was recorded; exact-ID resume is required.")
    return identifiers[0]


def image_evidence(identifier, turn=None):
    """Read only this experiment's exact persisted rollout, never other session contents."""
    uuid.UUID(identifier)
    root = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "sessions"
    files = list(root.glob("*/*/*/*" + identifier + ".jsonl"))
    calls, outputs, image_items, active_turn = {}, {}, 0, 0
    def images(value):
        if isinstance(value, dict):
            return int(value.get("type") == "input_image") + sum(images(x) for x in value.values())
        if isinstance(value, list):
            return sum(images(x) for x in value)
        if isinstance(value, str) and value.startswith(("[", "{")):
            try:
                return images(json.loads(value))
            except ValueError:
                return 0
        return 0
    for path in files:
        for line in path.read_text().splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            payload = event.get("payload", {})
            if event.get("type") == "event_msg" and payload.get("type") == "task_started":
                active_turn += 1
            if turn is not None and active_turn != turn:
                continue
            if payload.get("type") in {"function_call", "custom_tool_call"}:
                content = str(payload.get("input", payload.get("arguments", "")))
                invocations = len(re.findall(r"\bview_image\s*\(", content))
                if payload.get("name", "").split(".")[-1] == "view_image":
                    invocations = max(invocations, 1)
                if invocations:
                    calls[payload.get("call_id")] = invocations
            if payload.get("type") in {"function_call_output", "custom_tool_call_output"}:
                outputs[payload.get("call_id")] = images(payload.get("output", []))
                image_items += outputs[payload.get("call_id")]
    return {"rollout_found": len(files) == 1, "view_image_calls": len(calls),
            "view_image_code_invocations": sum(calls.values()),
            "view_image_calls_with_image_outputs": sum(outputs.get(key, 0) > 0 for key in calls),
            "image_items_from_view_calls": sum(outputs.get(key, 0) for key in calls), "image_items": image_items,
            "turn": turn, "note": "Exact private rollout; task_started boundaries separate real user turns."}


def turn_usage(current, previous=None):
    result = dict(current)
    if previous:
        keys = ("input_tokens", "cached_input_tokens", "output_tokens")
        if any(not isinstance(current.get(key), int) or not isinstance(previous.get(key), int)
               or current[key] < previous[key] for key in keys):
            return {**result, **{key: None for key in keys}, "uncached_input_tokens": None,
                    "total_tokens": None, "usage_status": "nonmonotonic_thread_totals"}
        result.update({key: current[key] - previous[key] for key in keys})
    if isinstance(result.get("input_tokens"), int) and isinstance(result.get("output_tokens"), int):
        result["uncached_input_tokens"] = result["input_tokens"] - result["cached_input_tokens"]
        result["total_tokens"] = result["input_tokens"] + result["output_tokens"]
        result["usage_status"] = "thread_total_delta" if previous else "initial_thread_total"
    return result


def svg(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 100_000:
        raise ValueError("Missing or unsafe SVG.")
    data = path.read_bytes()
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", data, re.I):
        raise ValueError("SVG declarations are not allowed.")
    return ET.fromstring(data)


def node(path, identifier):
    return next((x for x in svg(path).iter() if x.get("id") == identifier), None)


def source_delta(first, second, identifier):
    left, right = node(first, identifier), node(second, identifier)
    if left is None or right is None:
        return None
    pattern = r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?"
    a, b = ([float(x) for x in re.findall(pattern, item.get("d", ""))] for item in (left, right))
    if not a or len(a) != len(b):
        return None
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def signature(element):
    if element is None:
        return None
    return [(x.tag, sorted(x.attrib.items())) for x in element.iter()]


def png(path):
    path = Path(path)
    return path.is_file() and not path.is_symlink() and path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def check(workspace, task, turn, previous=None):
    workspace = Path(workspace)
    checks = {}
    if turn == 1:
        checks.update(core.score(workspace, "expressive-ribbon")["checks"])
        checks["two_rendered_previews"] = all(png(workspace / ("preview-" + label + ".png")) for label in ("a", "b"))
    else:
        brief = json.loads((workspace / "brief.json").read_text())
        expected = {"silhouette", "color_identity"} if task == "fashion-feedback" else {"motion_direction"}
        checks["limited_confirmation_scope"] = set(brief.get("confirmed_preferences", [])) == expected
        checks["chosen_a_with_pending_revision"] = brief.get("selected_direction") == "a" and bool(brief.get("pending_preferences"))
        checks["unselected_b_retained"] = core.sha((workspace / "preview-b.svg").read_bytes()) == core.sha((previous / "preview-b.svg").read_bytes())
        checks["revised_preview_rendered"] = png(workspace / "selected.png")
        checks["selected_canvas_identity"] = svg(workspace / "selected.svg").get("viewBox") == "0 0 320 240"
    if task == "fashion-feedback":
        path = workspace / ("preview-a.svg" if turn == 1 else "selected.svg")
        owner = node(path, "outfit-a")
        checks["ribbon_belongs_to_outfit"] = owner is not None and any(x.get("id") == "ribbon-a" for x in owner.iter())
        if turn == 2:
            before = previous / "preview-a.svg"
            checks["ribbon_object_retained"] = signature(node(before, "ribbon-a")) == signature(node(path, "ribbon-a")) is not None
            checks["hem_geometry_changed"] = signature(node(before, "hem-a")) != signature(node(path, "hem-a")) and node(path, "hem-a") is not None
    else:
        delta = source_delta(workspace / "frames/a-0.svg", workspace / "frames/a-1.svg", "ribbon-a")
        checks["source_path_sampled_deformation"] = delta is not None and delta > 0
        mechanism = json.loads((workspace / "mechanism.json").read_text())
        checks["cycle_identity"] = mechanism.get("cycle_seconds") == 2
        checks["playback_status_present"] = bool(mechanism.get("playback_status"))
        if turn == 2:
            old_delta = source_delta(previous / "frames/a-0.svg", previous / "frames/a-1.svg", "ribbon-a")
            checks["sampled_deformation_reduced"] = delta is not None and old_delta is not None and 0 < delta < old_delta
    return {"mechanical_pass": all(checks.values()), "checks": checks, "preference_score": None,
            "continuous_playback_verified": False, "manual_review_required": ["intent fit", "visible differences", "confirmation and object relationships", "limits and actual source mechanism"]}


def snapshot(workspace, destination):
    destination.mkdir()
    for path in workspace.rglob("*"):
        if path.is_file() and not path.is_symlink() and "skill" not in path.relative_to(workspace).parts and path.suffix in {".svg", ".png", ".json", ".html", ".py"} and path.stat().st_size < 2_000_000:
            target = destination / path.relative_to(workspace)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


def prepare(args):
    output, renderer = Path(args.output).resolve(), Path(args.renderer).resolve()
    if output.exists() or output.is_relative_to(core.ROOT):
        raise ValueError("Use a new private output outside the repository.")
    tasks = args.task or list(TASKS)
    if len(set(tasks)) != len(tasks) or not 1 <= len(tasks) <= 2 or not 30 <= args.timeout <= 180:
        raise ValueError("Use one or two distinct tasks and a 30–180 second timeout.")
    files, identity = core.source_files(directory=args.skill_dir, commit=args.skill_commit, repository=args.repo)
    output.mkdir(mode=0o700, parents=True)
    for task in tasks:
        workspace = output / args.arm / task / "workspace"
        workspace.mkdir(parents=True)
        for name, data in files.items():
            path = workspace / "skill" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (workspace / "environment.txt").write_text(environment(renderer))
    manifest = {"state": "prepared", "arm": args.arm, "skill": identity, "model": core.MODEL,
                "effort": core.EFFORT, "codex_version": core.CLI_VERSION, "renderer": str(renderer),
                "tasks": tasks, "turns": 2, "cli_invocations": 2 * len(tasks), "timeout_seconds": args.timeout,
                "prompt_sha256": {task: [core.sha(prompt(task, turn, renderer).encode()) for turn in (1, 2)] for task in tasks},
                "provider_requests": None, "currency_cost": None, "preference_score": None}
    core.dump(output / "manifest.json", manifest)
    return {"manifest": str(output / "manifest.json"), "skill_sha256": identity["sha256"], "cli_invocations": manifest["cli_invocations"], "model_called": False}


def run(args):
    output = Path(args.output).resolve()
    manifest = json.loads((output / "manifest.json").read_text())
    if manifest["state"] != "prepared" or (manifest["model"], manifest["effort"], manifest["codex_version"]) != (core.MODEL, core.EFFORT, core.CLI_VERSION):
        raise ValueError("The prepared experiment state or runtime identity is invalid.")
    renderer = Path(manifest["renderer"])
    for task in manifest["tasks"]:
        if manifest["prompt_sha256"][task] != [core.sha(prompt(task, turn, renderer).encode()) for turn in (1, 2)]:
            raise ValueError("A feedback input changed after preparation.")
    core.dump(output / "preflight.json", core.doctor(renderer=renderer))
    executable, package = core.runtime()
    manifest["state"] = "running"
    core.dump(output / "manifest.json", manifest)
    rows = []
    for task in manifest["tasks"]:
        trial = output / manifest["arm"] / task
        workspace, identifier, previous_usage = trial / "workspace", None, None
        for turn in (1, 2):
            _, identity = core.source_files(directory=workspace / "skill")
            if identity["sha256"] != manifest["skill"]["sha256"]:
                raise ValueError("The staged skill changed.")
            phase = trial / ("round" + str(turn))
            phase.mkdir()
            started = time.monotonic()
            with (phase / "events.jsonl").open("w") as events, (phase / "stderr.log").open("w") as error:
                process = subprocess.Popen(command(executable, package, workspace, renderer, phase / "final.txt", identifier),
                                           cwd=workspace, env=core.host_env(), stdin=subprocess.PIPE, stdout=events,
                                           stderr=error, text=True, start_new_session=True)
                timed_out = False
                try:
                    process.communicate(prompt(task, turn, renderer), timeout=manifest["timeout_seconds"])
                except subprocess.TimeoutExpired:
                    timed_out = True
                    core.stop(process)
            snapshot(workspace, phase / "artifacts")
            status = "timeout" if timed_out else "completed" if process.returncode == 0 else "cli-error"
            try:
                current_id = thread_id(phase / "events.jsonl")
                if identifier is not None and current_id != identifier:
                    raise ValueError("Resume changed the conversation ID.")
                identifier = current_id
                evidence = image_evidence(identifier, turn=turn)
                outcome = check(workspace, task, turn, trial / "round1/artifacts" if turn == 2 else None)
            except (OSError, ValueError, TypeError, ET.ParseError) as error:
                evidence, outcome = {}, {"mechanical_pass": False, "evaluation_error": str(error), "preference_score": None}
            reported_usage = core.usage(phase / "events.jsonl")
            row = {"task": task, "arm": manifest["arm"], "turn": turn, "status": status, "elapsed_seconds": time.monotonic() - started,
                   "exit_code": process.returncode, "thread_id": identifier, "usage": turn_usage(reported_usage, previous_usage),
                   "reported_cumulative_usage": reported_usage,
                   "image_evidence": evidence, "outcome": outcome}
            core.dump(phase / "result.json", row)
            rows.append(row)
            previous_usage = reported_usage
            print(json.dumps({key: row[key] for key in ("task", "arm", "turn", "status", "elapsed_seconds")}), flush=True)
            if turn == 1 and (status != "completed" or identifier is None or not all(png(workspace / ("preview-" + label + ".png")) for label in ("a", "b"))):
                break
    manifest["state"] = "completed"
    core.dump(output / "manifest.json", manifest)
    summary = {"model": core.MODEL, "effort": core.EFFORT, "results": rows, "actual_cli_invocations": len(rows),
               "preference_score": None, "continuous_playback_verified": False, "currency_cost": None}
    core.dump(output / "summary.json", summary)
    return summary


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="Verify the strict sandbox and static renderer without model calls.")
    doctor.add_argument("--renderer", default=str(DEFAULT_RENDERER))
    staging = commands.add_parser("prepare", help="Freeze one arm with two real feedback turns per task.")
    staging.add_argument("--arm", choices=("old", "new"), required=True)
    source = staging.add_mutually_exclusive_group(required=True)
    source.add_argument("--skill-dir")
    source.add_argument("--skill-commit")
    staging.add_argument("--repo", default=str(core.ROOT))
    staging.add_argument("--renderer", default=str(DEFAULT_RENDERER))
    staging.add_argument("--task", action="append", choices=TASKS)
    staging.add_argument("--timeout", type=int, default=180)
    staging.add_argument("--output", required=True)
    execute = commands.add_parser("run", help="Run each first turn, then resume its exact private conversation.")
    execute.add_argument("--output", required=True)
    execute.add_argument("--execute", required=True, action="store_true")
    args = parser.parse_args()
    try:
        result = core.doctor(renderer=Path(args.renderer)) if args.command == "doctor" else prepare(args) if args.command == "prepare" else run(args)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
