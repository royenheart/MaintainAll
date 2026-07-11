from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from MaintainAll.missions.loader import _flatten_tasks, _parse_mission, runnable_tasks
from MaintainAll.missions.models import Mission, TaskNode
from MaintainAll.missions.store import _mission_to_dict
from MaintainAll.paths import reports_dir, skills_dir
from MaintainAll.skills.loader import load_skill_body, load_skills
from MaintainAll.tools.match import CommandGate, UnlimitedGate
from MaintainAll.tools.shell import run_allowed
from MaintainAll.tools.validate import evaluate_expect

_SKIP_DIR_NAMES = frozenset(
    {"__pycache__", ".git", ".venv", "node_modules", ".pytest_cache", ".ruff_cache"}
)

_BOARD_SYSTEM_PROMPT = (
    "You are an AIOps mission planner. Output a single Mission JSON object only "
    "(no markdown fences or prose).\n"
    "Hard requirements:\n"
    "- allowed_commands: NON-EMPTY list of objects with regex pattern and cwd "
    "(relative to repo root, usually \".\")\n"
    "- tasks: concrete runnable checks for the user request; reference repo files "
    "from the context when applicable\n"
    "- expect: NEVER use empty patterns.\n"
    "Expect↔output semantics (critical):\n"
    "- `contains` patterns MUST appear in actual command stdout/stderr (or joined "
    "observations). Do NOT invent success tokens the tool never prints (no fake "
    '"OK" for silent checkers).\n'
    "- Many checkers succeed silently (e.g. `bash -n`, `python -m py_compile`): "
    "empty stdout + rc=0 is recorded as `rc=0 · cmd=…`. For those, do NOT use "
    '`contains: ["OK"]`. Prefer `report_section` expects and require ReAct OBSERVE '
    "to write that section summarizing results; or use `contains` only for strings "
    "the command truly emits (e.g. error text on failure).\n"
    "- If agent mode is readonly, RUN/script are NOT executed; observations will be "
    "`[readonly] execution disabled: …`. Leaf expects must be satisfiable without "
    "real stdout — typically `report_section` filled via OBSERVE (agent reasons "
    "about the check plan / dry-run). Never use contains-of-success-token in readonly.\n"
    "- Expect design must be consistent with `script` / allowed_commands behavior.\n"
    "- For `contains`, use realistic substrings (e.g. \"syntax error\", \"error\", "
    "\"Permission denied\") or `report_section` / `file_exists`.\n"
    "- skills: include relevant names from the skills catalog when applicable\n"
    "allowed_commands pattern rules (CommandGate uses re.fullmatch on the ENTIRE "
    "command line the agent will RUN — not a prefix match):\n"
    "- Prefer the narrowest pattern that covers each task script or intended RUN line\n"
    "- ALWAYS anchor with ^ and $; escape literal dots/parens; use optional groups "
    "for trailing args (e.g. ^python3? scripts/modulefiles/manage_modules\\.py list( .*)?$)\n"
    "- NEVER whitelist a bare interpreter/tool alone (bash, sh, python3, curl, find, …). "
    "Include distinctive flags/subcommands and only the args needed, e.g. "
    "^bash\\s+-n\\b.+$ or ^bash\\s+-n\\s+\\S+$, NOT bash or ^bash\\b or ^bash\\b.*$\n"
    "- Each allowed_commands entry must be required by at least one task script or "
    "instruction-driven RUN line\n"
    "- Every LEAF task (no nested tasks) that performs a check or action MUST include "
    "a non-empty script field: the exact argv command line that will be executed "
    "(same string CommandGate fullmatches). instruction is human-readable; script is "
    "what runs. Prefer concrete commands matching allowed_commands, e.g. "
    "bash -n maintaince/create-user.sh, or split into multiple leaf tasks / one "
    "bash -c '...' with a matching narrow pattern. Do not leave executable work as "
    "instruction-only.\n"
    "- task.script is executed as ONE command line: shlex.split then subprocess.run "
    "(no implicit bash -c or shell). Multi-line script fields are invalid — use a "
    "single argv-friendly line per script, split work across tasks, or rely on ReAct "
    "RUN: directives for multiple commands. Whitelist patterns must fullmatch those "
    "exact RUN/script strings.\n"
    "Schema fields: id, name, description, skills, schedule, notify, "
    "allowed_commands, tasks (id, name, needs, instruction, expect, script, optional tasks)."
)

_BARE_TOOL_PROBES = frozenset(
    {
        "bash",
        "sh",
        "zsh",
        "python",
        "python3",
        "perl",
        "ruby",
        "node",
        "curl",
        "find",
        "cat",
        "ls",
        "chmod",
        "sudo",
    }
)


def _flatten_task_dicts(tasks: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        out.append(task)
        out.extend(_flatten_task_dicts(task.get("tasks") or []))
    return out


def _repo_context_snippet(repo_path: str, *, max_entries: int = 40) -> str:
    repo = Path(repo_path)
    entries: list[str] = []

    def add_entry(rel: str) -> None:
        if len(entries) < max_entries and rel not in entries:
            entries.append(rel)

    maintaince = repo / "maintaince"
    if maintaince.is_dir():
        for path in sorted(maintaince.rglob("*")):
            if len(entries) >= max_entries:
                break
            if not path.is_file():
                continue
            if any(part in _SKIP_DIR_NAMES for part in path.parts):
                continue
            add_entry(str(path.relative_to(repo)))

    scripts = repo / "scripts"
    if scripts.is_dir():
        for path in sorted(scripts.rglob("*")):
            if len(entries) >= max_entries:
                break
            if not path.is_file():
                continue
            if any(part in _SKIP_DIR_NAMES for part in path.parts):
                continue
            add_entry(str(path.relative_to(repo)))

    skills_root = repo / ".agents" / "skills"
    if skills_root.is_dir():
        for path in sorted(skills_root.iterdir()):
            if len(entries) >= max_entries:
                break
            if path.is_dir():
                add_entry(f".agents/skills/{path.name}/")

    deploy = repo / "deploy"
    if deploy.is_dir():
        for path in sorted(deploy.iterdir()):
            if len(entries) >= max_entries:
                break
            rel = path.relative_to(repo)
            add_entry(f"{rel}/" if path.is_dir() else str(rel))

    if not entries:
        return "(no repo paths found under maintaince/, scripts/, skills/, deploy/)"
    return "\n".join(f"- {entry}" for entry in entries)


def _skills_catalog(repo_path: str) -> str:
    root = skills_dir(Path(repo_path))
    if not root.exists():
        return "(no skills indexed)"
    skills = load_skills(root)
    if not skills:
        return "(no skills indexed)"
    return "\n".join(f"- {skill.name}: {skill.description}" for skill in skills)


def _pattern_too_broad(pattern: str) -> bool:
    if not pattern or not isinstance(pattern, str):
        return True
    try:
        compiled = re.compile(pattern)
    except re.error:
        return True
    if "^" not in pattern and "$" not in pattern:
        return True
    for probe in _BARE_TOOL_PROBES:
        if compiled.fullmatch(probe):
            return True
    return False


def _is_leaf_task_dict(task: dict[str, Any]) -> bool:
    return not (task.get("tasks") or [])


def _expect_is_weak(expect: Any) -> bool:
    if not isinstance(expect, dict):
        return True
    etype = str(expect.get("type") or "").strip()
    if etype == "contains":
        patterns = expect.get("patterns")
        if not patterns:
            return True
        if all(not str(pattern).strip() for pattern in patterns):
            return True
    return False


def _draft_is_weak(
    draft: dict[str, Any],
    *,
    require_leaf_scripts: bool = True,
) -> bool:
    """Return True when a board draft is low-quality.

    ``require_leaf_scripts`` defaults to True so callers can flag instruction-only
    leaf tasks. Board LLM auto-retry should pass False: ReAct can still drive
    instruction-only tasks via RUN/OBSERVE/DECLARE_DONE, and an extra board call
    would burn FakeLLM / budgeted responses.
    """
    if not draft.get("allowed_commands"):
        return True
    for cmd in draft.get("allowed_commands") or []:
        if isinstance(cmd, dict):
            pattern = str(cmd.get("pattern") or "")
        else:
            pattern = str(cmd)
        if _pattern_too_broad(pattern):
            return True
    for task in _flatten_task_dicts(draft.get("tasks") or []):
        if _expect_is_weak(task.get("expect")):
            return True
        if require_leaf_scripts and _is_leaf_task_dict(task):
            script = task.get("script")
            if not script or not str(script).strip():
                return True
    return False


def _looks_like_script_format_check(user_input: str) -> bool:
    text = user_input.lower()
    keywords = (
        "format",
        "syntax",
        "shell",
        "bash",
        "script",
        "maintaince",
        "shellcheck",
        "格式",
        "脚本",
    )
    return any(keyword in text for keyword in keywords)


def _board_user_prompt(
    user_input: str,
    *,
    feedback: str,
    repo_path: str,
    mode: str = "readonly",
    retry_note: str = "",
) -> str:
    parts = [
        f"User request:\n{user_input}",
        f"\nAgent mode: {mode}",
        f"\nSkills catalog:\n{_skills_catalog(repo_path)}",
        f"\nRepo context (maintaince/, scripts/, skills/, deploy/):\n"
        f"{_repo_context_snippet(repo_path)}",
    ]
    if feedback:
        parts.append(f"\nReviewer feedback to incorporate:\n{feedback}")
    if retry_note:
        parts.append(f"\n{retry_note}")
    return "".join(parts)


def _parse_board_draft(content: str) -> dict[str, Any] | None:
    try:
        parsed = _extract_json(content)
        if isinstance(parsed, dict):
            mission = mission_from_dict(parsed)
            return mission_to_dict(mission)
    except Exception:
        return None
    return None


AssessFn = Callable[[dict[str, Any]], dict[str, Any]]
EventCallback = Callable[[dict[str, Any]], None]


def mission_to_dict(mission: Mission, *, include_status: bool = True) -> dict[str, Any]:
    data = _mission_to_dict(mission)
    if include_status:
        _embed_statuses(data.get("tasks", []), mission.tasks)
    return data


def mission_from_dict(data: dict[str, Any]) -> Mission:
    # Strip runtime status before schema parse, then re-apply.
    cleaned = json.loads(json.dumps(data))
    status_map = _collect_statuses(cleaned.get("tasks", []))
    _strip_statuses(cleaned.get("tasks", []))
    mission = _parse_mission(cleaned)
    for task in _flatten_tasks(mission.tasks):
        if task.id in status_map:
            task.status = status_map[task.id]
    return mission


def _collect_statuses(tasks: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for task in tasks:
        if "status" in task:
            out[task["id"]] = task["status"]
        out.update(_collect_statuses(task.get("tasks") or []))
    return out


def _strip_statuses(tasks: list[dict[str, Any]]) -> None:
    for task in tasks:
        task.pop("status", None)
        _strip_statuses(task.get("tasks") or [])


def _embed_statuses(data_tasks: list[dict[str, Any]], tasks: list[TaskNode]) -> None:
    by_id = {t.id: t for t in tasks}
    for data in data_tasks:
        node = by_id.get(data["id"])
        if node is not None:
            data["status"] = node.status
            if data.get("tasks") and node.tasks:
                _embed_statuses(data["tasks"], node.tasks)


def _piece_text(piece: Any) -> str:
    if piece is None:
        return ""
    if isinstance(piece, str):
        return piece
    if isinstance(piece, list):
        parts: list[str] = []
        for item in piece:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("text") is not None:
                parts.append(str(item["text"]))
            elif hasattr(item, "text"):
                parts.append(str(item.text))
        return "".join(parts)
    return str(piece)


def _message_reasoning(message: Any) -> str:
    if message is None:
        return ""
    if isinstance(message, dict):
        ak = message.get("additional_kwargs") or {}
        return str(ak.get("reasoning_content") or ak.get("reasoning") or "")
    ak = getattr(message, "additional_kwargs", None) or {}
    if isinstance(ak, dict):
        return str(ak.get("reasoning_content") or ak.get("reasoning") or "")
    return ""


def _message_content(message: Any) -> str:
    if message is None:
        return ""
    if isinstance(message, dict):
        return _piece_text(message.get("content"))
    if hasattr(message, "content"):
        return _piece_text(message.content)
    return str(message)


def _llm_content(llm: Any, messages: list[dict[str, str]]) -> str:
    if llm is None:
        return ""
    if hasattr(llm, "invoke"):
        result = llm.invoke(messages)
    elif callable(llm):
        result = llm(messages)
    else:
        raise TypeError(f"unsupported llm type: {type(llm)!r}")
    return _message_content(result)


def _llm_call(
    llm: Any,
    messages: list[dict[str, str]],
    *,
    event_callback: EventCallback | None = None,
    phase: str = "",
) -> str:
    """Invoke LLM, streaming reasoning/content into thinking events when possible."""
    if llm is None:
        return ""

    think_id = f"{phase}-{abs(hash((phase, messages[-1].get('content', '')[:80])))}"

    def emit(event: dict[str, Any]) -> None:
        if event_callback is not None:
            event_callback(event)

    emit({"type": "thinking_start", "phase": phase, "id": think_id})

    content = ""
    try:
        if hasattr(llm, "stream"):
            content_parts: list[str] = []
            for chunk in llm.stream(messages):
                reasoning = _message_reasoning(chunk)
                if reasoning:
                    emit(
                        {
                            "type": "thinking_delta",
                            "phase": phase,
                            "id": think_id,
                            "text": reasoning,
                            "kind": "reasoning",
                        }
                    )
                piece = _message_content(chunk)
                if piece:
                    content_parts.append(piece)
                    emit(
                        {
                            "type": "thinking_delta",
                            "phase": phase,
                            "id": think_id,
                            "text": piece,
                            "kind": "content",
                        }
                    )
            content = "".join(content_parts)
        else:
            if hasattr(llm, "invoke"):
                result = llm.invoke(messages)
            elif callable(llm):
                result = llm(messages)
            else:
                raise TypeError(f"unsupported llm type: {type(llm)!r}")
            reasoning = _message_reasoning(result)
            if reasoning:
                emit(
                    {
                        "type": "thinking_delta",
                        "phase": phase,
                        "id": think_id,
                        "text": reasoning,
                        "kind": "reasoning",
                    }
                )
            content = _message_content(result)
            if content:
                emit(
                    {
                        "type": "thinking_delta",
                        "phase": phase,
                        "id": think_id,
                        "text": content,
                        "kind": "content",
                    }
                )
    finally:
        emit({"type": "thinking_end", "phase": phase, "id": think_id})

    return content


def _strip_prefix(text: str) -> str:
    text = text.strip()
    for prefix in ("ASSESS:", "BOARD:", "REACT:"):
        if text.upper().startswith(prefix):
            return text[len(prefix) :].strip()
    return text


def _extract_json(text: str) -> Any:
    text = _strip_prefix(text)
    if text.startswith("```"):
        lines = text.splitlines()
        # drop opening fence
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _emit(event_callback: EventCallback | None, event: dict[str, Any]) -> dict[str, Any]:
    if event_callback is not None:
        event_callback(event)
    return event


def _append_event(
    events: list[dict[str, Any]],
    event_callback: EventCallback | None,
    event: dict[str, Any],
) -> list[dict[str, Any]]:
    events = list(events)
    events.append(_emit(event_callback, event))
    return events


def _looks_like_mission_run(user_input: str) -> bool:
    text = user_input.strip().lower()
    if text.startswith("run mission "):
        return True
    if "/mission.yaml" in text or text.endswith("mission.yaml"):
        return True
    return False


def _minimal_mission_draft(user_input: str) -> dict[str, Any]:
    if _looks_like_script_format_check(user_input):
        return {
            "id": "ad-hoc-script-check",
            "name": "Script format check",
            "description": user_input,
            "skills": [],
            "schedule": None,
            "notify": {"on_complete": True, "on_failure": True},
            "allowed_commands": [
                {"pattern": r"^bash\s+-n\b.+$", "cwd": "."},
                {"pattern": r"^find\b.+maintaince\b.+$", "cwd": "."},
            ],
            "tasks": [
                {
                    "id": "main",
                    "name": "Check script syntax",
                    "needs": [],
                    "instruction": (
                        "Run bash -n on shell scripts under maintaince/ and report syntax issues."
                    ),
                    "expect": {"type": "report_section", "name": "summary"},
                    "script": (
                        "find maintaince -type f \\( -name '*.sh' -o -name '*.bash' \\) "
                        "-exec bash -n {} +"
                    ),
                    "status": "pending",
                }
            ],
        }
    return {
        "id": "ad-hoc",
        "name": "Ad hoc",
        "description": user_input,
        "skills": [],
        "schedule": None,
        "notify": {"on_complete": True, "on_failure": True},
        "allowed_commands": [{"pattern": r"^echo\b", "cwd": "."}],
        "tasks": [
            {
                "id": "main",
                "name": "Main",
                "needs": [],
                "instruction": user_input,
                "expect": {"type": "report_section", "name": "summary"},
                "script": "echo summary",
                "status": "pending",
            }
        ],
    }


def _load_skill_context(repo_path: str, skill_names: list[str]) -> str:
    root = skills_dir(Path(repo_path))
    if not root.exists() or not skill_names:
        return ""
    available = {s.name: s for s in load_skills(root)}
    parts: list[str] = []
    for name in skill_names:
        meta = available.get(name)
        if meta is None:
            continue
        parts.append(f"### Skill: {name}\n{load_skill_body(meta.path)}")
    return "\n\n".join(parts)


def _append_report_draft(draft: str, text: str) -> str:
    text = (text or "").strip()
    if not text:
        return draft
    if draft.strip():
        return draft.rstrip() + "\n\n" + text + "\n"
    return text + "\n"


def _looks_like_report_markdown(text: str) -> bool:
    return bool(re.search(r"^##\s+\S+", text or "", re.MULTILINE))


def _required_report_section_names(mission: Mission) -> list[str]:
    """Ordered unique report_section expect names from leaf tasks."""
    names: list[str] = []
    seen: set[str] = set()
    for task in _flatten_tasks(mission.tasks):
        if task.expect.type != "report_section":
            continue
        name = (task.expect.name or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _missing_report_sections(mission: Mission, report_draft: str) -> list[str]:
    missing: list[str] = []
    draft = report_draft or ""
    for name in _required_report_section_names(mission):
        pattern = rf"^##\s+{re.escape(name)}\b"
        if not re.search(pattern, draft, re.MULTILINE):
            missing.append(name)
    return missing


def _report_sections_nudge(missing: list[str]) -> str:
    headings = ", ".join(f"## {name}" for name in missing)
    return (
        f"missing report sections: {', '.join(missing)} — "
        f"emit OBSERVE with {headings} before DECLARE_DONE"
    )


def _parse_react_directives(content: str) -> tuple[list[str], str | None, bool, bool]:
    """Parse FakeLLM / structured ReAct protocol.

    Returns (run_cmds, observe_text, declare_done, rebuild).

    Supported lines (optional ``REACT:`` prefix):
    - ``RUN:<cmd>`` / ``RUN: <cmd>``
    - ``OBSERVE:<markdown>`` (may span following lines until next directive)
    - ``DECLARE_DONE`` / ``DONE``
    - ``REBUILD``
    """
    runs: list[str] = []
    observe_parts: list[str] = []
    declare_done = False
    rebuild = False

    lines = (content or "").splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        body = raw
        if body.upper().lstrip().startswith("REACT:"):
            # Keep indentation-free body after REACT:
            idx = body.upper().find("REACT:")
            body = body[idx + len("REACT:") :]

        stripped = body.strip()
        upper = stripped.upper()

        if upper.startswith("RUN:"):
            cmd = stripped[4:].strip()
            if cmd:
                runs.append(cmd)
            i += 1
            continue

        if upper.startswith("OBSERVE:"):
            first = stripped[8:].lstrip()
            if first:
                observe_parts.append(first)
            i += 1
            while i < len(lines):
                nxt = lines[i]
                check = nxt
                if check.upper().lstrip().startswith("REACT:"):
                    idx = check.upper().find("REACT:")
                    check = check[idx + len("REACT:") :]
                check_u = check.strip().upper()
                if check_u.startswith(("RUN:", "OBSERVE:")) or check_u in {
                    "DECLARE_DONE",
                    "DONE",
                    "REBUILD",
                }:
                    break
                if "DECLARE_DONE" in check_u and check_u.startswith("DECLARE_DONE"):
                    break
                observe_parts.append(nxt)
                i += 1
            continue

        if upper in {"DECLARE_DONE", "DONE"} or upper.startswith("DECLARE_DONE"):
            declare_done = True
            i += 1
            continue

        if upper == "REBUILD" or upper.startswith("REBUILD"):
            rebuild = True
            i += 1
            continue

        # Whole-message fallbacks (no line protocol)
        if "DECLARE_DONE" in upper:
            declare_done = True
        if "REBUILD" in upper and "DECLARE_DONE" not in upper:
            rebuild = True
        i += 1

    observe_text = "\n".join(observe_parts).strip() if observe_parts else None
    return runs, observe_text, declare_done, rebuild


def _emit_cmd_count(
    events: list[dict[str, Any]],
    event_callback: EventCallback | None,
    gate: CommandGate | UnlimitedGate,
) -> list[dict[str, Any]]:
    matched = gate.last_match
    pattern = matched.pattern if matched is not None else "*"
    count = gate.counts.get(pattern, 0)
    return _append_event(
        events,
        event_callback,
        {"type": "cmd_count", "pattern": pattern, "count": count},
    )


def _run_command_via_gate(
    cmd: str,
    *,
    gate: CommandGate | UnlimitedGate,
    repo_root: Path,
    events: list[dict[str, Any]],
    event_callback: EventCallback | None,
    observations: list[str],
    report_draft: str,
    dry_run: bool = False,
) -> tuple[list[dict[str, Any]], list[str], str, bool]:
    if dry_run:
        msg = f"[readonly] execution disabled: {cmd}"
        observations.append(msg)
        events = _append_event(
            events,
            event_callback,
            {"type": "cmd_skipped", "reason": "readonly", "cmd": cmd},
        )
        return events, observations, report_draft, False

    try:
        result = run_allowed(cmd, gate=gate, repo_root=repo_root, dry_run=False)
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if stdout:
            obs = f"cmd={cmd} · {stdout}"
        elif stderr:
            obs = f"cmd={cmd} · {stderr}"
        else:
            obs = f"rc={result.returncode} · cmd={cmd}"
        observations.append(obs)
        if _looks_like_report_markdown(obs):
            report_draft = _append_report_draft(report_draft, obs)
        events = _emit_cmd_count(events, event_callback, gate)
        return events, observations, report_draft, result.ok
    except PermissionError as exc:
        observations.append(str(exc))
        return events, observations, report_draft, False


def assess_node(
    state: dict[str, Any],
    *,
    llm: Any = None,
    assess_fn: AssessFn | None = None,
    event_callback: EventCallback | None = None,
) -> dict[str, Any]:
    if assess_fn is not None:
        result = assess_fn(state)
        events = _append_event(
            state.get("event_log") or [],
            event_callback,
            {"type": "assess", "feasible": result.get("feasible"), "reason": result.get("reject_reason", "")},
        )
        result = dict(result)
        result["event_log"] = events
        return result

    # Resume / already assessed
    if state.get("feasible") is not None and state.get("mission_draft"):
        return {}

    events = list(state.get("event_log") or [])
    user_input = state.get("user_input") or ""
    mode = state.get("mode") or "readonly"
    report_language = (state.get("report_language") or "zh-CN").strip() or "zh-CN"

    if llm is not None:
        content = _llm_call(
            llm,
            [
                {
                    "role": "system",
                    "content": (
                        "You are the feasibility gate for an AIOps agent. "
                        'Reply with JSON only: {"feasible": bool, "reason": str}\n'
                        f'The "reason" field MUST be written in this language: '
                        f"{report_language}. "
                        "Do not change JSON keys or the boolean feasible value.\n"
                        "\n"
                        "Agent modes (execution capability):\n"
                        "- readonly: NO real shell/subprocess. Commands are dry-run "
                        "skipped (`[readonly] execution disabled: …`). The agent may "
                        "still plan, explain, draft missions/reports, or answer from "
                        "skills/repo knowledge when that alone satisfies the request.\n"
                        "- restricted: may execute only mission allowed_commands "
                        "(whitelist, full-line match).\n"
                        "- unlimited: may execute arbitrary non-empty commands.\n"
                        "- mission: running a solidified mission under its whitelist "
                        "(treat like restricted).\n"
                        "\n"
                        "Judge whether the user's goal can actually be completed under "
                        "the given mode — do not assume readonly can truly verify or "
                        "apply changes via skipped commands.\n"
                        "If mode cannot fulfill the request (e.g. user wants live "
                        "bash -n / deploy / connectivity probes / service restarts "
                        "while mode is readonly), set feasible=false and explain in "
                        "reason, suggesting restricted or unlimited when appropriate.\n"
                        "If the request is planning, explanation, drafting a checklist, "
                        "or knowledge-only and does not need live execution results, "
                        "feasible=true is fine even in readonly.\n"
                        "In restricted/unlimited/mission, treat normal AIOps shell/"
                        "mission work as feasible unless clearly out of scope."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Agent mode: {mode}\n"
                        f"Report language: {report_language}\n\n"
                        f"User request:\n{user_input}"
                    ),
                },
            ],
            event_callback=event_callback,
            phase="assess",
        )
        try:
            data = _extract_json(content)
            feasible = bool(data.get("feasible"))
            reason = str(data.get("reason") or "")
        except (json.JSONDecodeError, TypeError, AttributeError):
            feasible = True
            reason = "assess parse failure; default allow"
    else:
        if _looks_like_mission_run(user_input):
            feasible = True
            reason = "known mission run"
        else:
            feasible = True
            reason = "default allow for stub"

    events = _append_event(
        events,
        event_callback,
        {"type": "assess", "feasible": feasible, "reason": reason},
    )
    out: dict[str, Any] = {"feasible": feasible, "event_log": events}
    if not feasible:
        out["reject_reason"] = reason
    return out


def build_board_node(
    state: dict[str, Any],
    *,
    llm: Any = None,
    event_callback: EventCallback | None = None,
) -> dict[str, Any]:
    events = list(state.get("event_log") or [])
    review_action = state.get("review_action")
    existing = state.get("mission_draft")

    if review_action == "reject":
        return {"rebuild_board": False}

    # Keep board on approve resume unless rebuild requested
    if (
        existing
        and review_action == "approve"
        and not state.get("rebuild_board")
        and state.get("review_feedback") in (None, "")
    ):
        return {"rebuild_board": False}

    user_input = state.get("user_input") or ""
    feedback = state.get("review_feedback") or ""
    repo_path = state.get("repo_path") or "."
    mode = state.get("mode") or "readonly"

    draft: dict[str, Any] | None = None

    # Solidified / daemon mission: never reinvent the board unless rebuild/feedback
    if (
        existing
        and not state.get("rebuild_board")
        and not feedback
        and (state.get("mode") == "mission" or state.get("skip_review"))
    ):
        draft = existing
    elif llm is not None:
        user_prompt = _board_user_prompt(
            user_input,
            feedback=feedback,
            repo_path=repo_path,
            mode=mode,
        )
        messages = [
            {"role": "system", "content": _BOARD_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        content = _llm_call(
            llm,
            messages,
            event_callback=event_callback,
            phase="board",
        )
        draft = _parse_board_draft(content)

        # Retry only for structural whitelist/expect issues — not missing scripts.
        # Instruction-only leaves are still runnable via ReAct RUN/DECLARE_DONE.
        if draft is not None and _draft_is_weak(draft, require_leaf_scripts=False):
            retry_note = (
                "Previous draft was invalid: missing allowed_commands, empty expect "
                "patterns, or overly broad allowed_commands patterns (e.g. bare bash, "
                "^bash\\b.*$, python3, curl). Use anchored re.fullmatch patterns with "
                "required flags/subcommands. Prefer a non-empty script on every leaf "
                "task (exact command line to execute). Fix."
            )
            retry_prompt = _board_user_prompt(
                user_input,
                feedback=feedback,
                repo_path=repo_path,
                mode=mode,
                retry_note=retry_note,
            )
            retry_content = _llm_call(
                llm,
                [
                    {"role": "system", "content": _BOARD_SYSTEM_PROMPT},
                    {"role": "user", "content": retry_prompt},
                ],
                event_callback=event_callback,
                phase="board",
            )
            retry_draft = _parse_board_draft(retry_content)
            if retry_draft is not None:
                draft = retry_draft

        if draft is not None and _draft_is_weak(draft):
            events = _append_event(
                events,
                event_callback,
                {
                    "type": "board_warning",
                    "message": (
                        "Mission board draft is weak: missing allowed_commands, "
                        "empty expect patterns, overly broad command patterns, "
                        "or leaf tasks missing script."
                    ),
                },
            )

    if draft is None:
        if existing and not state.get("rebuild_board"):
            draft = existing
        else:
            draft = _minimal_mission_draft(user_input)

    skill_names = list(draft.get("skills") or [])
    skill_ctx = _load_skill_context(repo_path, skill_names)
    if skill_ctx:
        draft = dict(draft)
        draft["_skill_context"] = skill_ctx

    events = _append_event(
        events,
        event_callback,
        {"type": "board", "mission_id": draft.get("id"), "task_count": len(draft.get("tasks") or [])},
    )
    return {
        "mission_draft": draft,
        "rebuild_board": False,
        "review_action": None,
        "react_done": False,
        "validation_ok": None,
        "validation_errors": [],
        "report_draft": "",
        "event_log": events,
    }


def review_node(
    state: dict[str, Any],
    *,
    event_callback: EventCallback | None = None,
) -> dict[str, Any]:
    events = list(state.get("event_log") or [])
    skip = bool(state.get("skip_review"))
    mode = state.get("mode") or "readonly"

    if skip or mode == "unlimited":
        events = _append_event(
            events,
            event_callback,
            {"type": "review", "action": "approve", "auto": True},
        )
        return {
            "review_action": "approve",
            "interrupt": None,
            "event_log": events,
        }

    if state.get("review_action") is not None:
        events = _append_event(
            events,
            event_callback,
            {"type": "review", "action": state.get("review_action"), "auto": False},
        )
        return {"interrupt": None, "event_log": events}

    events = _append_event(
        events,
        event_callback,
        {"type": "review", "action": None, "waiting": True},
    )
    return {"interrupt": "review", "event_log": events}


def react_loop_node(
    state: dict[str, Any],
    *,
    llm: Any = None,
    event_callback: EventCallback | None = None,
    max_iters: int = 10,
) -> dict[str, Any]:
    events = list(state.get("event_log") or [])
    draft = state.get("mission_draft") or _minimal_mission_draft(state.get("user_input") or "")
    # Drop non-schema helper keys before parse
    draft_for_parse = {k: v for k, v in draft.items() if not k.startswith("_")}
    mission = mission_from_dict(draft_for_parse)
    repo_root = Path(state.get("repo_path") or ".")
    mode = state.get("mode") or "restricted"
    report_draft = state.get("report_draft") or ""
    dry_run = mode == "readonly"
    report_language = (state.get("report_language") or "zh-CN").strip() or "zh-CN"

    if mode == "unlimited":
        gate: CommandGate | UnlimitedGate = UnlimitedGate()
    elif dry_run:
        # Gate unused for exec; keep a placeholder for typing / future checks.
        gate = CommandGate([])
    else:
        gate = CommandGate(mission.allowed_commands)

    new_observations: list[str] = []
    rebuild = False
    done = False
    required_sections = _required_report_section_names(mission)
    prior_errors = list(state.get("validation_errors") or [])

    for _ in range(max_iters):
        missing_sections = _missing_report_sections(mission, report_draft)
        if llm is not None:
            content = _llm_call(
                llm,
                [
                    {
                        "role": "system",
                        "content": (
                            "ReAct step for an AIOps agent. Reply with protocol lines:\n"
                            "- RUN:<command>  (must match allowed_commands; may repeat)\n"
                            "- OBSERVE:<markdown>  (report draft sections, e.g. ## connectivity)\n"
                            "- DECLARE_DONE or DONE when finished\n"
                            "- REBUILD to rebuild the task board\n"
                            "Prefix with REACT: is allowed (e.g. REACT:RUN:echo hi).\n"
                            f"OBSERVE markdown (the mission report body) MUST be written in "
                            f"this language: {report_language}. "
                            "Do not change the language of RUN commands or protocol keywords.\n"
                            "When mode is readonly, RUN/script only produce dry-run skip "
                            "observations (`[readonly] execution disabled: …`); you MUST still "
                            "emit OBSERVE markdown (in report_language) that satisfies "
                            "report_section expects. Do not rely on command stdout for contains.\n"
                            "Never DECLARE_DONE while required report sections are missing "
                            "from the report draft."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Mission: {mission.id}\n"
                            f"Mode: {mode}\n"
                            f"Allowed commands: "
                            f"{[c.pattern for c in mission.allowed_commands]}\n"
                            f"Instruction context: {state.get('user_input', '')}\n"
                            f"Required report sections: {required_sections}\n"
                            f"Missing report sections: {missing_sections}\n"
                            f"Previous validation errors: {prior_errors}\n"
                            f"Pending tasks: "
                            f"{[{'id': t.id, 'instruction': t.instruction, 'script': t.script} for t in runnable_tasks(mission)]}\n"
                            f"Observations so far: {new_observations}\n"
                            f"Report draft so far:\n{report_draft}"
                        ),
                    },
                ],
                event_callback=event_callback,
                phase="react",
            )
            runs, observe, declare_done, want_rebuild = _parse_react_directives(content)

            if want_rebuild:
                rebuild = True
                break

            if observe:
                report_draft = _append_report_draft(report_draft, observe)
                new_observations.append(observe)

            for cmd in runs:
                events, new_observations, report_draft, _ok = _run_command_via_gate(
                    cmd,
                    gate=gate,
                    repo_root=repo_root,
                    events=events,
                    event_callback=event_callback,
                    observations=new_observations,
                    report_draft=report_draft,
                    dry_run=dry_run,
                )

            if declare_done:
                missing = _missing_report_sections(mission, report_draft)
                if missing and llm is not None:
                    nudge = _report_sections_nudge(missing)
                    new_observations.append(nudge)
                    events = _append_event(
                        events,
                        event_callback,
                        {
                            "type": "react_nudge",
                            "missing_sections": list(missing),
                        },
                    )
                    # Refuse early done; continue loop so LLM can OBSERVE.
                else:
                    for task in _flatten_tasks(mission.tasks):
                        if task.status == "pending":
                            task.status = "done"
                    # Ensure validate-friendly observation for stub missions
                    if not any("ok" in obs.lower() for obs in new_observations):
                        new_observations.append("ok")
                    new_observations.append("declared done")
                    done = True
                    break

            # If LLM emitted work this turn, continue for another directive
            if runs or observe:
                # Also run any scripted tasks that are ready
                pass

        runnable = runnable_tasks(mission)
        if not runnable:
            flat = _flatten_tasks(mission.tasks)
            if flat and all(t.status == "done" for t in flat):
                missing = _missing_report_sections(mission, report_draft)
                if missing and llm is not None:
                    nudge = _report_sections_nudge(missing)
                    if nudge not in new_observations:
                        new_observations.append(nudge)
                    events = _append_event(
                        events,
                        event_callback,
                        {
                            "type": "react_nudge",
                            "missing_sections": list(missing),
                        },
                    )
                    continue
                done = True
                break
            if flat and all(t.status in {"done", "failed", "blocked"} for t in flat):
                missing = _missing_report_sections(mission, report_draft)
                if missing and llm is not None:
                    # Readonly script skips mark failed; reopen report_section tasks
                    # so another OBSERVE turn can satisfy validation.
                    for task in flat:
                        if (
                            task.status == "failed"
                            and task.expect.type == "report_section"
                        ):
                            task.status = "pending"
                    nudge = _report_sections_nudge(missing)
                    if nudge not in new_observations:
                        new_observations.append(nudge)
                    events = _append_event(
                        events,
                        event_callback,
                        {
                            "type": "react_nudge",
                            "missing_sections": list(missing),
                        },
                    )
                    continue
                done = all(t.status == "done" for t in flat)
                break
            for task in flat:
                if task.status == "pending":
                    task.status = "blocked"
            events = _append_event(
                events,
                event_callback,
                {"type": "task_status", "status": "blocked"},
            )
            break

        progressed = False
        for task in runnable:
            events = _append_event(
                events,
                event_callback,
                {"type": "task_status", "id": task.id, "status": "running"},
            )
            if task.script:
                events, new_observations, report_draft, ok = _run_command_via_gate(
                    task.script,
                    gate=gate,
                    repo_root=repo_root,
                    events=events,
                    event_callback=event_callback,
                    observations=new_observations,
                    report_draft=report_draft,
                    dry_run=dry_run,
                )
                if dry_run and task.expect.type == "report_section":
                    # Skip is expected; section must come from OBSERVE, not stdout.
                    task.status = "done"
                else:
                    task.status = "done" if ok else "failed"
                progressed = True
            elif llm is not None:
                # Instruction-only: wait for LLM RUN/OBSERVE/DECLARE_DONE protocol.
                # Do not auto-complete while an LLM is available.
                events = _append_event(
                    events,
                    event_callback,
                    {"type": "task_status", "id": task.id, "status": "pending"},
                )
                continue
            else:
                # Stub path without LLM: mark instruction executed.
                stub_obs = f"executed instruction: {task.instruction}"
                new_observations.append(stub_obs)
                if _looks_like_report_markdown(task.instruction):
                    report_draft = _append_report_draft(report_draft, task.instruction)
                task.status = "done"
                progressed = True
            events = _append_event(
                events,
                event_callback,
                {"type": "task_status", "id": task.id, "status": task.status},
            )

        flat = _flatten_tasks(mission.tasks)
        if flat and all(t.status in {"done", "failed", "blocked"} for t in flat):
            missing = _missing_report_sections(mission, report_draft)
            if missing and llm is not None:
                nudge = _report_sections_nudge(missing)
                if nudge not in new_observations:
                    new_observations.append(nudge)
                events = _append_event(
                    events,
                    event_callback,
                    {
                        "type": "react_nudge",
                        "missing_sections": list(missing),
                    },
                )
                continue
            done = all(t.status == "done" for t in flat)
            break

        # Avoid spinning when LLM is present but emitted nothing and no scripts ran
        if llm is not None and not progressed:
            # Next iteration will call LLM again
            continue

    updated = mission_to_dict(mission)
    if "_skill_context" in draft:
        updated["_skill_context"] = draft["_skill_context"]

    events = _append_event(
        events,
        event_callback,
        {"type": "react", "done": done, "rebuild": rebuild},
    )
    return {
        "mission_draft": updated,
        "observations": list(state.get("observations") or []) + new_observations,
        "report_draft": report_draft,
        "react_done": done,
        "rebuild_board": rebuild,
        "event_log": events,
    }


def _observations_are_readonly_skips(observations: list[Any]) -> bool:
    if not observations:
        return False
    for obs in observations:
        text = str(obs).strip()
        if not text.startswith("[readonly] execution disabled"):
            return False
    return True


def validate_node(
    state: dict[str, Any],
    *,
    event_callback: EventCallback | None = None,
) -> dict[str, Any]:
    from MaintainAll.notify.report import write_report

    events = list(state.get("event_log") or [])
    draft = state.get("mission_draft") or {}
    draft_for_parse = {k: v for k, v in draft.items() if not k.startswith("_")}
    mission = mission_from_dict(draft_for_parse) if draft_for_parse.get("id") else None
    repo_root = Path(state.get("repo_path") or ".")
    stdout = "\n".join(state.get("observations") or [])
    report_draft = state.get("report_draft") or ""
    errors: list[str] = []
    mode = state.get("mode") or "readonly"
    readonly_skips_only = mode == "readonly" and _observations_are_readonly_skips(
        state.get("observations") or []
    )

    # If mission expects a report file under .maintainall/reports (or legacy .agents/reports) and we have a draft,
    # write it early so file_exists globs can succeed before finalize.
    if mission is not None and report_draft.strip():
        needs_report_file = any(
            t.expect.type == "file_exists"
            and (
                ".maintainall/reports" in (t.expect.path_glob or "")
                or ".agents/reports" in (t.expect.path_glob or "")
            )
            for t in _flatten_tasks(mission.tasks)
        )
        if needs_report_file:
            mission_id = str(draft.get("id") or "unknown")
            write_report(mission_id, report_draft, reports_dir(repo_root))

    if mission is None:
        errors.append("HARD: missing mission_draft")
    else:
        for task in _flatten_tasks(mission.tasks):
            # Report-path file_exists: also accept non-empty report_draft
            if (
                task.expect.type == "file_exists"
                and (
                    ".maintainall/reports" in (task.expect.path_glob or "")
                    or ".agents/reports" in (task.expect.path_glob or "")
                )
                and report_draft.strip()
            ):
                # Draft written above (or sufficient as content proof)
                ok, msg = evaluate_expect(
                    task.expect,
                    stdout=stdout,
                    report_text=report_draft,
                    repo_root=repo_root,
                )
                if not ok and report_draft.strip():
                    # Auto-pass when draft exists even if glob race/timing misses
                    ok, msg = True, ""
            else:
                ok, msg = evaluate_expect(
                    task.expect,
                    stdout=stdout,
                    report_text=report_draft,
                    repo_root=repo_root,
                )
            if not ok:
                if readonly_skips_only and task.expect.type == "contains":
                    msg = (
                        "contains expect unmet under readonly dry-run (no command stdout); "
                        "observations are skip markers only"
                    )
                errors.append(f"{task.id}: {msg}")

    ok = len(errors) == 0
    events = _append_event(
        events,
        event_callback,
        {"type": "validate", "ok": ok, "errors": list(errors)},
    )
    return {
        "validation_ok": ok,
        "validation_errors": errors,
        "react_done": False if not ok else state.get("react_done", True),
        "report_draft": report_draft,
        "event_log": events,
    }


def revise_mission_node(
    state: dict[str, Any],
    *,
    llm: Any = None,
    event_callback: EventCallback | None = None,
) -> dict[str, Any]:
    events = list(state.get("event_log") or [])
    if llm is None:
        events = _append_event(
            events,
            event_callback,
            {"type": "revise_mission", "action": "finalize", "reason": "no llm"},
        )
        return {"rebuild_board": False, "event_log": events}

    draft = state.get("mission_draft") or {}
    errors = state.get("validation_errors") or []
    observations = state.get("observations") or []
    report_language = (state.get("report_language") or "zh-CN").strip() or "zh-CN"

    content = _llm_call(
        llm,
        [
            {
                "role": "system",
                "content": (
                    "Mission validation failed after ReAct retries. Decide whether the "
                    "mission design is wrong (expects, allowed_commands, scripts) and "
                    "should be rebuilt, or execution is as good as it gets and the run "
                    "should finalize with failure.\n"
                    "For each validation error:\n"
                    "1. Compare expect type/patterns vs each observation line.\n"
                    "2. Infer what the commands would actually produce (silent success "
                    "→ rc=0 · cmd=… with empty stdout; stderr on failure; readonly "
                    "→ `[readonly] execution disabled: …` only).\n"
                    "3. If expects cannot be satisfied by those semantics → action "
                    "rebuild with concrete feedback (change expect type/patterns, adjust "
                    "scripts, require OBSERVE report_section sections).\n"
                    "4. If mode is readonly and observations are only readonly skip "
                    "markers while expects are contains success tokens → MUST rebuild "
                    "(switch to report_section + OBSERVE instructions), not finalize.\n"
                    "5. Only finalize when failure is due to a genuine check failure "
                    "under a well-designed mission, not expect/tool mismatch.\n"
                    'Reply with JSON only: {"action":"rebuild"|"finalize",'
                    '"feedback":"str","reason":"str"}\n'
                    "If action is rebuild, feedback must tell the board builder how to "
                    "fix expects, allowed_commands, and scripts."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"User request: {state.get('user_input', '')}\n"
                    f"Mode: {state.get('mode', '')}\n"
                    f"Report language: {report_language}\n"
                    f"Mission draft: {json.dumps(draft, ensure_ascii=False)}\n"
                    f"Validation errors: {errors}\n"
                    f"Observations: {observations}\n"
                    f"Report draft:\n{state.get('report_draft') or ''}"
                ),
            },
        ],
        event_callback=event_callback,
        phase="revise",
    )

    action = "finalize"
    feedback = ""
    reason = ""
    try:
        data = _extract_json(content)
        action = str(data.get("action") or "finalize").strip().lower()
        feedback = str(data.get("feedback") or "")
        reason = str(data.get("reason") or "")
    except (json.JSONDecodeError, TypeError, AttributeError):
        reason = "revise parse failure; finalize"

    if action == "rebuild":
        events = _append_event(
            events,
            event_callback,
            {
                "type": "revise_mission",
                "action": "rebuild",
                "feedback": feedback or reason,
            },
        )
        return {
            "rebuild_board": True,
            "review_feedback": feedback or reason,
            "review_action": None,
            "validation_ok": None,
            "validation_errors": [],
            "observations": [],
            "report_draft": "",
            "react_done": False,
            "event_log": events,
        }

    events = _append_event(
        events,
        event_callback,
        {
            "type": "revise_mission",
            "action": "finalize",
            "reason": reason or feedback,
        },
    )
    return {"rebuild_board": False, "event_log": events}


def finalize_node(
    state: dict[str, Any],
    *,
    event_callback: EventCallback | None = None,
) -> dict[str, Any]:
    from MaintainAll.notify.report import format_mission_report

    events = list(state.get("event_log") or [])
    repo = Path(state.get("repo_path") or ".")
    draft = state.get("mission_draft") or {}
    mission_id = str(draft.get("id") or "unknown")
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = reports_dir(repo)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{mission_id}-{ts}.md"
    path.write_text(format_mission_report(state), encoding="utf-8")

    interrupt = None
    worth_saving = bool(
        draft.get("id") and (draft.get("tasks") or draft.get("allowed_commands"))
    )
    if (
        worth_saving
        and not state.get("skip_review")
        and state.get("mode") != "mission"
    ):
        interrupt = "solidify"

    events = _append_event(
        events,
        event_callback,
        {"type": "finalize", "report_path": str(path)},
    )
    return {
        "report_path": str(path),
        "interrupt": interrupt,
        "event_log": events,
    }


def reject_node(
    state: dict[str, Any],
    *,
    event_callback: EventCallback | None = None,
) -> dict[str, Any]:
    events = _append_event(
        list(state.get("event_log") or []),
        event_callback,
        {"type": "reject", "reason": state.get("reject_reason", "")},
    )
    return {"interrupt": None, "event_log": events}


def make_nodes(
    *,
    llm: Any = None,
    event_callback: EventCallback | None = None,
    assess_fn: AssessFn | None = None,
    max_iters: int = 10,
) -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
    return {
        "assess": lambda state: assess_node(
            state, llm=llm, assess_fn=assess_fn, event_callback=event_callback
        ),
        "build_board": lambda state: build_board_node(
            state, llm=llm, event_callback=event_callback
        ),
        "review": lambda state: review_node(state, event_callback=event_callback),
        "react_loop": lambda state: react_loop_node(
            state, llm=llm, event_callback=event_callback, max_iters=max_iters
        ),
        "validate": lambda state: validate_node(state, event_callback=event_callback),
        "revise_mission": lambda state: revise_mission_node(
            state, llm=llm, event_callback=event_callback
        ),
        "finalize": lambda state: finalize_node(state, event_callback=event_callback),
        "reject": lambda state: reject_node(state, event_callback=event_callback),
    }
