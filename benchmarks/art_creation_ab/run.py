#!/usr/bin/env python3
"""Small old/new skill experiments using the pinned Codex Linux sandbox."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
MODEL = "gpt-6.1-sol"
EFFORT = "low"
CLI_VERSION = "codex-cli 0.160.0"
PROFILE = "art_bench"
TASKS = {
    "expressive-ribbon": (
        "Create an original editable SVG study for an airy luminous ribbon with a strong turning motion. "
        "Show two visibly different directions on the same 320 by 240 canvas. Use the accent color #58dcff. "
        "Keep the ribbon a vector object, not a raster image or an unrelated overlay. "
        "I have not selected or accepted either direction. Keep interpretations as hypotheses."
    ),
    "fashion-boundary": (
        "Explore two original outfit silhouette directions for a virtual character: airy but with a strong "
        "directional ribbon accent. Use editable SVG on a 320 by 240 canvas and accent #58dcff. "
        "The final target is undecided between Live2D and VRM. No Blender, Houdini, Live2D Core, or "
        "VRM target importer is configured for this task. Keep the requested silhouette medium, "
        "distinguish a preview from a production pattern or verified target import, and state capability limits. "
        "I have not selected or accepted a direction."
    ),
}
CONTRACT = (
    "Read skill/SKILL.md first, and only the relevant resources under skill/. "
    "Write preview-a.svg, preview-b.svg, and brief.json directly in the workspace. "
    "brief.json must contain intent_hypotheses (list), alternatives (two objects with ids a and b), "
    "confirmed_preferences (an empty list), pending_preferences (nonempty list), and capability_limits (list). "
    "Produce actual vector files, not prose claiming files exist. Do not install software, use the network, "
    "change the supplied skill, or claim that the user approved anything."
)


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def toml(value):
    if isinstance(value, dict):
        return "{" + ",".join(json.dumps(k) + "=" + toml(v) for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ",".join(toml(item) for item in value) + "]"
    if isinstance(value, bool):
        return str(value).lower()
    return json.dumps(value)


def host_skill_paths():
    """Enumerate manifest paths only; never load their instructions or credential contents."""
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    roots = {Path.home() / ".agents" / "skills", codex_home / "skills", codex_home / "plugins" / "cache"}
    paths = set()
    for root in roots:
        for directory, _, names in os.walk(root, followlinks=True):
            if "SKILL.md" in names:
                paths.add(str(Path(directory) / "SKILL.md"))
    return sorted(paths)


def config_args(package, renderer=None, readonly_inputs=False):
    values = {
        "default_permissions": PROFILE,
        f"permissions.{PROFILE}.filesystem": {
            ":root": "deny", ":minimal": "read", ":slash_tmp": "deny", ":tmpdir": "deny",
            str(package): "read",
            ":workspace_roots": {".": "write", "skill": "read"},
        },
        f"permissions.{PROFILE}.network.enabled": False,
        "approval_policy": "never",
        "project_doc_max_bytes": 0,
        "web_search": "disabled",
        "features.skip_host_skill_discovery": True,
        "features.skill_search": False,
        "features.skill_mcp_dependency_install": False,
        "features.shell_snapshot": False,
        "features.enable_mcp_apps": False,
        "features.plugins": False,
        "skills.config": [{"path": path, "enabled": False} for path in host_skill_paths()],
        "shell_environment_policy.inherit": "none",
        "shell_environment_policy.set": {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        "model_reasoning_effort": EFFORT,
    }
    if renderer:
        values[f"permissions.{PROFILE}.filesystem"][str(renderer)] = "read"
    if readonly_inputs:
        values[f"permissions.{PROFILE}.filesystem"][":workspace_roots"]["inputs"] = "read"
    return [item for key, value in values.items() for item in ("-c", key + "=" + toml(value))]


def host_env():
    # The trusted CLI reads local authentication; model-generated commands inherit none of this.
    names = ("PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "CODEX_HOME",
             "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
             "http_proxy", "https_proxy", "all_proxy", "no_proxy")
    return {name: os.environ[name] for name in names if name in os.environ}


def runtime():
    if platform.system() != "Linux":
        raise ValueError("This v0 backend requires the verified Linux Codex sandbox.")
    executable = shutil.which("codex")
    if not executable:
        raise ValueError("Codex CLI is not installed.")
    version = subprocess.check_output([executable, "--version"], text=True, timeout=10).strip()
    if version != CLI_VERSION:
        raise ValueError(f"Expected {CLI_VERSION}; found {version}. Revalidate the backend before changing the pin.")
    package = Path(executable).resolve().parent.parent
    if not (package / "package.json").is_file():
        raise ValueError("Expected the pinned npm Codex package layout; cannot safely grant its runtime path.")
    return executable, package


def source_files(directory=None, commit=None, repository=ROOT):
    if directory is not None:
        source = Path(directory)
        if source.is_symlink() or not source.is_dir():
            raise ValueError("Skill directories must be real directories, not symbolic links.")
        files = {}
        for path in sorted(source.rglob("*")):
            if path.is_symlink():
                raise ValueError("Skill snapshots must not contain symbolic links.")
            if path.is_file():
                if path.stat().st_nlink != 1:
                    raise ValueError("Skill snapshots must not contain hard-linked files.")
                files[path.relative_to(source).as_posix()] = path.read_bytes()
        identity = {"kind": "directory", "path": str(source.resolve())}
    else:
        revision = subprocess.check_output(
            ["git", "-C", str(repository), "rev-parse", "--verify", "--end-of-options", commit + "^{commit}"],
            text=True, stderr=subprocess.PIPE, timeout=10,
        ).strip()
        archive = subprocess.check_output(
            ["git", "-C", str(repository), "archive", revision, "skills/art-creation"], timeout=10,
        )
        files = {}
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            for member in stream:
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ValueError("Commit snapshots must not contain symbolic links or special files.")
                relative = Path(member.name).relative_to("skills/art-creation")
                if ".." in relative.parts or relative.is_absolute():
                    raise ValueError("Unsafe archive path.")
                files[relative.as_posix()] = stream.extractfile(member).read()
        identity = {"kind": "commit", "commit": revision, "repository": str(Path(repository).resolve())}
    if "SKILL.md" not in files:
        raise ValueError("The selected source must contain SKILL.md.")
    if sum(map(len, files.values())) > 20_000_000:
        raise ValueError("The skill snapshot exceeds the v0 size limit.")
    for name in files:
        if any(part in {".git", ".codex", ".env", "auth.json", "node_modules"} for part in Path(name).parts):
            raise ValueError("A skill snapshot contains a credential or runtime directory name.")
    identity["files"] = {name: sha(data) for name, data in files.items()}
    identity["sha256"] = sha(json.dumps(identity["files"], sort_keys=True).encode())
    return files, identity


def prepare(args):
    output = Path(args.output).resolve()
    if output.is_relative_to(ROOT) or output.exists():
        raise ValueError("Use a new private output directory outside this repository.")
    tasks = args.task or ["expressive-ribbon"]
    if len(tasks) > 2 or len(set(tasks)) != len(tasks):
        raise ValueError("Select one or two distinct tasks: two or four CLI invocations in total.")
    snapshots = {}
    identities = {}
    for arm in ("old", "new"):
        snapshots[arm], identities[arm] = source_files(
            directory=getattr(args, arm + "_dir"), commit=getattr(args, arm + "_commit"), repository=args.repo,
        )
    output.mkdir(mode=0o700, parents=True)
    manifest = {
        "schema_version": 1, "state": "prepared", "model": MODEL, "effort": EFFORT,
        "codex_version": CLI_VERSION, "backend": "codex-linux-permission-profile",
        "timeout_seconds": args.timeout, "cli_invocations": 2 * len(tasks),
        "provider_requests": None, "tasks": tasks, "order": ["old", "new"],
        "provider_snapshot": None, "seed": None, "repetitions_per_task": 1, "viewport": [320, 240],
        "skills": identities, "same_skill_content": identities["old"]["sha256"] == identities["new"]["sha256"],
        "task_sha256": {task: sha((TASKS[task] + CONTRACT).encode()) for task in tasks},
        "prompt_sha256": {task: sha((TASKS[task] + "\n\n" + CONTRACT).encode()) for task in tasks},
        "preference_score": None, "currency_cost": None,
        "cost_note": "Local subscription authentication; monetary and provider-request costs are unknown.",
    }
    for arm in manifest["order"]:
        for task in tasks:
            workspace = output / arm / task / "workspace"
            workspace.mkdir(parents=True)
            for name, data in snapshots[arm].items():
                target = workspace / "skill" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            (workspace / "task.txt").write_text(TASKS[task] + "\n\n" + CONTRACT + "\n")
    dump(output / "manifest.json", manifest)
    return {"manifest": str(output / "manifest.json"), "cli_invocations": manifest["cli_invocations"],
            "same_skill_content": manifest["same_skill_content"], "model_called": False}


def usage(events):
    records = []
    tool_commands = 0
    nonzero_tool_commands = 0
    cli_warning_items = 0
    cli_error_items = 0
    for line in Path(events).read_text().splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("type") == "turn.completed" and isinstance(item.get("usage"), dict):
            records.append(item["usage"])
        if item.get("type") == "item.completed" and item.get("item", {}).get("type") == "command_execution":
            tool_commands += 1
            code = item["item"].get("exit_code")
            nonzero_tool_commands += isinstance(code, int) and code != 0
        if item.get("type") == "item.completed" and item.get("item", {}).get("type") == "error":
            warning = item["item"].get("message", "").startswith("Under-development features enabled:")
            cli_warning_items += warning
            cli_error_items += not warning
    result = {"input_tokens": None, "cached_input_tokens": None, "uncached_input_tokens": None,
              "output_tokens": None, "total_tokens": None, "provider_requests": None,
              "compactions": None, "currency_cost": None, "tool_commands": tool_commands,
              "nonzero_tool_commands": nonzero_tool_commands, "cli_warning_items": cli_warning_items,
              "cli_error_items": cli_error_items,
              "usage_status": "missing" if not records else "ambiguous"}
    if len(records) == 1:
        record = records[0]
        result.update({key: record.get(key) for key in ("input_tokens", "cached_input_tokens", "output_tokens")})
        incoming, cached, outgoing = (result[key] for key in ("input_tokens", "cached_input_tokens", "output_tokens"))
        if isinstance(incoming, int) and isinstance(outgoing, int) and incoming >= 0 and outgoing >= 0:
            result["total_tokens"] = incoming + outgoing
            if isinstance(cached, int) and 0 <= cached <= incoming:
                result["uncached_input_tokens"] = incoming - cached
            result["usage_status"] = "reported_by_cli"
    return result


def score(workspace, task):
    workspace = Path(workspace)
    checks = {}
    digests = []
    allowed = {"svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
               "text", "tspan", "defs", "linearGradient", "radialGradient", "stop", "title", "desc"}
    for name in ("a", "b"):
        path = workspace / f"preview-{name}.svg"
        valid = False
        if path.is_file() and not path.is_symlink() and path.stat().st_size <= 100_000:
            payload = path.read_bytes()
            digests.append(sha(payload))
            try:
                if re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", payload, flags=re.I):
                    raise ValueError("SVG declarations are not allowed.")
                svg = ET.fromstring(payload)
                box = [float(x) for x in re.split(r"[ ,]+", svg.attrib.get("viewBox", "").strip())]
                valid = svg.tag.split("}")[-1] == "svg" and box == [0.0, 0.0, 320.0, 240.0]
                vector = False
                for node in svg.iter():
                    tag = node.tag.split("}")[-1]
                    if tag not in allowed:
                        valid = False
                    vector |= tag in {"path", "polygon", "polyline"}
                    for key, value in node.attrib.items():
                        if key.lower().startswith("on") or (key.endswith("href") and not value.startswith("#")):
                            valid = False
                        if re.search(r"url\((?!\s*#)", value, flags=re.I):
                            valid = False
                valid &= vector and b"#58dcff" in payload.lower()
            except (ET.ParseError, ValueError):
                valid = False
        checks[f"editable_vector_{name}"] = bool(valid)
    checks["distinct_file_contents"] = len(digests) == 2 and digests[0] != digests[1]
    try:
        path = workspace / "brief.json"
        if path.is_symlink() or path.stat().st_size > 30_000:
            raise ValueError("Unsafe brief.")
        brief = json.loads(path.read_text())
        checks["hypotheses_and_pending"] = all(isinstance(brief.get(key), list) and bool(brief[key])
                                                for key in ("intent_hypotheses", "pending_preferences"))
        checks["no_invented_acceptance"] = brief.get("confirmed_preferences") == []
        alternatives = brief.get("alternatives")
        checks["two_named_alternatives"] = (isinstance(alternatives, list) and len(alternatives) == 2
                                             and {x.get("id") for x in alternatives} == {"a", "b"})
        checks["capability_limits_present"] = isinstance(brief.get("capability_limits"), list)
        if task == "fashion-boundary":
            checks["capability_limits_nonempty"] = bool(brief.get("capability_limits"))
    except (OSError, ValueError, TypeError, AttributeError):
        checks["readable_brief"] = False
    return {"mechanical_pass": all(checks.values()), "checks": checks, "preference_score": None,
            "manual_review_required": ["visible directional difference", "intent fit", "coherence",
                                       "accurate capability boundaries", "no unsupported success claims"],
            "note": "File differences and brief fields are mechanical proxies, not aesthetic approval."}


def discover(executable, package, workspace, renderer=None, readonly_inputs=False):
    """List skills without starting a thread or making a model request."""
    env = host_env()
    command = [executable, *config_args(package, renderer=renderer, readonly_inputs=readonly_inputs), "app-server", "--stdio"]
    process = subprocess.Popen(command, cwd=workspace, env=env, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                               start_new_session=True)
    messages = [
        {"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "art-bench", "version": "0"},
                                                      "capabilities": {"experimentalApi": True}}},
        {"method": "initialized", "params": {}},
        {"id": 2, "method": "skills/list", "params": {"cwds": [str(workspace)], "forceReload": True}},
        {"id": 3, "method": "config/read", "params": {"includeLayers": False}},
    ]
    for message in messages:
        process.stdin.write(json.dumps(message) + "\n")
    process.stdin.flush()
    responses = {}
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + 10
    try:
        while time.monotonic() < deadline and not {2, 3}.issubset(responses):
            for key, _ in selector.select(0.2):
                line = key.fileobj.readline()
                if not line:
                    raise ValueError("The Codex discovery probe exited before returning results.")
                message = json.loads(line)
                if message.get("id") in {2, 3}:
                    responses[message["id"]] = message
    finally:
        selector.close()
        stop(process)
    if any(i not in responses or "error" in responses[i] for i in (2, 3)):
        raise ValueError("Cannot verify isolated skill discovery without model calls.")
    skills = [skill for entry in responses[2]["result"].get("data", []) for skill in entry.get("skills", [])]
    config = responses[3]["result"].get("config", {})
    return {"enabled_host_skill_catalog_empty": not any(skill.get("enabled", True) for skill in skills),
            "agents_document_loading_disabled": config.get("project_doc_max_bytes") == 0,
            "skill_discovery_skip_enabled": config.get("features", {}).get("skip_host_skill_discovery") is True}


def stop(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def doctor(renderer=None, readonly_inputs=False):
    executable, package = runtime()
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    global_agents_absent = not any((codex_home / name).exists() for name in ("AGENTS.md", "AGENTS.override.md"))
    if not global_agents_absent:
        raise ValueError("Global Codex AGENTS documents exist; the project byte limit does not disable them. No model call is allowed.")
    with tempfile.TemporaryDirectory(prefix="art-bench-doctor-") as directory:
        base = Path(directory)
        workspace = base / "workspace"
        workspace.mkdir()
        (base / "host-canary").write_text("Private test canary; never print this content.")
        (base / "AGENTS.md").write_text("Do not load this parent document into the experiment.")
        (workspace / "skill").mkdir()
        (workspace / "skill" / "SKILL.md").write_text("# Read-only test skill\n")
        if readonly_inputs:
            (workspace / "inputs").mkdir()
            (workspace / "inputs" / "reference.txt").write_text("Public input canary")
        paths = {"host_canary": str(base / "host-canary"), "auth": str(Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "auth.json"),
                 "user_agents": str(Path.home() / ".agents"), "user_codex": str(Path.home() / ".codex")}
        probe = workspace / "probe.py"
        probe.write_text(
            "import json,pathlib,socket\nc={}\n"
            "p=pathlib.Path('allowed.txt');p.write_text('ok');c['workspace_write']=p.read_text()=='ok'\n"
            f"for name,path in {paths!r}.items():\n"
            " try:\n  q=pathlib.Path(path);q.read_bytes() if q.is_file() else list(q.iterdir());c[name+'_denied']=False\n"
            " except OSError:c[name+'_denied']=True\n"
            f"for name,path in {{'outside_write':{str(base / 'illegal-write')!r},'skill_write':'skill/SKILL.md'}}.items():\n"
            " try:\n  pathlib.Path(path).write_text('bad');c[name+'_denied']=False\n"
            " except OSError:c[name+'_denied']=True\n"
            "try:\n s=socket.socket();s.settimeout(1);s.connect(('1.1.1.1',443));s.close();c['network_denied']=False\n"
            "except OSError:c['network_denied']=True\n"
            + ("c['input_read']=pathlib.Path('inputs/reference.txt').read_text()=='Public input canary'\n"
               "for name,operation in [('input_overwrite_denied',lambda:pathlib.Path('inputs/reference.txt').write_text('bad')),('input_create_denied',lambda:pathlib.Path('inputs/new.txt').write_text('bad')),('input_rename_denied',lambda:pathlib.Path('inputs').rename('moved-inputs'))]:\n"
               " try:\n  operation();c[name]=False\n"
               " except OSError:c[name]=True\n" if readonly_inputs else "")
            + "print(json.dumps(c));raise SystemExit(not all(c.values()))\n"
        )
        result = subprocess.run([executable, "sandbox", "-P", PROFILE, "-C", str(workspace),
                                 *config_args(package, renderer=renderer, readonly_inputs=readonly_inputs), "/usr/bin/python3", str(probe)],
                                env=host_env(), text=True, capture_output=True, timeout=20)
        if result.returncode:
            raise ValueError("The sandbox enforcement probe failed: " + result.stderr[:300] + result.stdout[:1000])
        checks = json.loads(result.stdout)
        checks["global_agents_absent"] = global_agents_absent
        checks.update(discover(executable, package, workspace, renderer=renderer, readonly_inputs=readonly_inputs))
        if renderer:
            svg = workspace / "renderer-probe.svg"
            svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240"><path fill="#58dcff" d="M10 10Q80 200 300 10Z"/></svg>')
            png = workspace / "renderer-probe.png"
            rendered = subprocess.run([executable, "sandbox", "-P", PROFILE, "-C", str(workspace),
                                       *config_args(package, renderer=renderer, readonly_inputs=readonly_inputs), str(Path(renderer) / "bin/python"),
                                       "-m", "cairosvg", str(svg), "-o", str(png)],
                                      env=host_env(), text=True, capture_output=True, timeout=20)
            checks["cairo_sandbox_render"] = rendered.returncode == 0 and png.is_file() and png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
            if not checks["cairo_sandbox_render"]:
                raise ValueError("CairoSVG could not render inside the verified permission profile: " + rendered.stderr[-500:])
        if not all(checks.values()):
            raise ValueError("The isolation preflight failed: " + json.dumps(checks))
        return {"passed": True, "checks": checks, "codex_version": CLI_VERSION,
                "platform": platform.platform(), "python": platform.python_version(),
                "model": MODEL, "effort": EFFORT, "model_called": False,
                "backend": "official Codex Linux permission profile (bubblewrap/seccomp)"}


def run(args):
    output = Path(args.output).resolve()
    manifest = json.loads((output / "manifest.json").read_text())
    if manifest["state"] != "prepared":
        raise ValueError("This experiment already started; prepare a new private directory rather than rerunning it.")
    if (manifest.get("model"), manifest.get("effort"), manifest.get("codex_version")) != (MODEL, EFFORT, CLI_VERSION):
        raise ValueError("The prepared runtime identity differs from the pinned runner.")
    tasks = manifest.get("tasks", [])
    if (not 1 <= len(tasks) <= 2 or len(set(tasks)) != len(tasks) or any(task not in TASKS for task in tasks)
            or manifest.get("order") != ["old", "new"] or manifest.get("cli_invocations") != 2 * len(tasks)
            or not isinstance(manifest.get("timeout_seconds"), int) or not 30 <= manifest["timeout_seconds"] <= 600):
        raise ValueError("The prepared task order or budget was changed.")
    for task in tasks:
        if manifest.get("task_sha256", {}).get(task) != sha((TASKS[task] + CONTRACT).encode()):
            raise ValueError("The task input changed after preparation.")
    preflight = doctor()
    dump(output / "preflight.json", preflight)
    executable, package = runtime()
    manifest["state"] = "running"
    dump(output / "manifest.json", manifest)
    results = []
    for arm in manifest["order"]:
        for task in manifest["tasks"]:
            trial = output / arm / task
            workspace = trial / "workspace"
            files, identity = source_files(directory=workspace / "skill")
            if identity["sha256"] != manifest["skills"][arm]["sha256"]:
                raise ValueError("The staged skill changed after preparation.")
            prompt = TASKS[task] + "\n\n" + CONTRACT
            command = [executable, "--no-daemon", *config_args(package), "exec", "--ignore-user-config",
                       "--ignore-rules", "--ephemeral", "--skip-git-repo-check", "--json", "--color", "never",
                       "--model", MODEL, "--cd", str(workspace), "--output-last-message", str(trial / "final.txt"), "-"]
            started = time.monotonic()
            with (trial / "events.jsonl").open("w") as events, (trial / "stderr.log").open("w") as error:
                process = subprocess.Popen(command, cwd=workspace, env=host_env(), stdin=subprocess.PIPE,
                                           stdout=events, stderr=error, text=True, start_new_session=True)
                timed_out = False
                try:
                    process.communicate(prompt, timeout=manifest["timeout_seconds"])
                except subprocess.TimeoutExpired:
                    timed_out = True
                    stop(process)
            row = {"arm": arm, "task": task, "elapsed_seconds": time.monotonic() - started,
                   "exit_code": process.returncode, "status": "timeout" if timed_out else "completed" if process.returncode == 0 else "cli-error",
                   "usage": usage(trial / "events.jsonl"), "outcome": score(workspace, task)}
            dump(trial / "result.json", row)
            results.append(row)
    manifest["state"] = "completed"
    dump(output / "manifest.json", manifest)
    summary = {"model": MODEL, "effort": EFFORT, "results": results, "preference_score": None,
               "note": "Review the two SVG directions and evidence manually. This tiny old/new experiment is not a ranking."}
    dump(output / "summary.json", summary)
    return summary


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Verify isolation and discovery without calling a model.")
    prepare_parser = commands.add_parser("prepare", help="Freeze one or two small old/new tasks without calling a model.")
    for arm in ("old", "new"):
        source = prepare_parser.add_mutually_exclusive_group(required=True)
        source.add_argument("--" + arm + "-dir", help="A real skill directory containing SKILL.md.")
        source.add_argument("--" + arm + "-commit", help="A commit containing skills/art-creation/.")
    prepare_parser.add_argument("--repo", default=str(ROOT), help="Repository used to read commit snapshots.")
    prepare_parser.add_argument("--task", action="append", choices=TASKS, help="Repeat for at most two tasks.")
    prepare_parser.add_argument("--output", required=True, help="New private artifact directory outside this repository.")
    prepare_parser.add_argument("--timeout", type=int, default=240, help="Wall-clock seconds per CLI invocation (30–600).")
    run_parser = commands.add_parser("run", help="Run a prepared, approved old/new experiment using existing local auth.")
    run_parser.add_argument("--output", required=True)
    run_parser.add_argument("--execute", required=True, action="store_true", help="Explicitly start model calls for this prepared candidate.")
    check = commands.add_parser("check", help="Check output contracts; never assign aesthetic preference.")
    check.add_argument("--workspace", required=True)
    check.add_argument("--task", choices=TASKS, required=True)
    usage_parser = commands.add_parser("usage", help="Read reported CLI usage; keep unknown costs explicit.")
    usage_parser.add_argument("--events", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            if not 30 <= args.timeout <= 600:
                raise ValueError("The timeout must be between 30 and 600 seconds.")
            value = prepare(args)
        elif args.command == "doctor":
            value = doctor()
        elif args.command == "run":
            value = run(args)
        elif args.command == "check":
            value = score(args.workspace, args.task)
        else:
            value = usage(args.events)
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 1 if args.command == "check" and not value["mechanical_pass"] else 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
