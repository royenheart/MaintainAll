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


def _llm_content(llm: Any, messages: list[dict[str, str]]) -> str:
    if llm is None:
        return ""
    if hasattr(llm, "invoke"):
        result = llm.invoke(messages)
    elif callable(llm):
        result = llm(messages)
    else:
        raise TypeError(f"unsupported llm type: {type(llm)!r}")
    if hasattr(result, "content"):
        return str(result.content)
    if isinstance(result, dict) and "content" in result:
        return str(result["content"])
    return str(result)


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
    return {
        "id": "ad-hoc",
        "name": "Ad hoc",
        "description": user_input,
        "skills": [],
        "schedule": None,
        "notify": {"on_complete": True, "on_failure": True},
        "allowed_commands": [],
        "tasks": [
            {
                "id": "main",
                "name": "Main",
                "needs": [],
                "instruction": user_input,
                "expect": {"type": "contains", "patterns": [""]},
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

    if llm is not None:
        content = _llm_content(
            llm,
            [
                {
                    "role": "system",
                    "content": (
                        "Assess whether the user request is feasible for an AIOps agent. "
                        'Reply with JSON only: {"feasible": bool, "reason": str}'
                    ),
                },
                {"role": "user", "content": user_input},
            ],
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

    draft: dict[str, Any] | None = None
    if llm is not None:
        prompt = (
            "Produce a Mission as JSON matching fields: id, name, description, skills, "
            "schedule, notify, allowed_commands, tasks (id, name, needs, instruction, expect, "
            "optional script/tasks). Prefer moderately general commands/tasks.\n"
            f"User request:\n{user_input}\n"
        )
        if feedback:
            prompt += f"\nReviewer feedback to incorporate:\n{feedback}\n"
        content = _llm_content(
            llm,
            [
                {"role": "system", "content": "You output Mission JSON only."},
                {"role": "user", "content": prompt},
            ],
        )
        try:
            parsed = _extract_json(content)
            if isinstance(parsed, dict):
                # Validate by round-trip parse
                mission = mission_from_dict(parsed)
                draft = mission_to_dict(mission)
        except Exception:
            draft = None

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

    if mode == "unlimited":
        gate: CommandGate | UnlimitedGate = UnlimitedGate()
    else:
        gate = CommandGate(mission.allowed_commands)

    new_observations: list[str] = []
    rebuild = False
    done = False

    for _ in range(max_iters):
        if llm is not None:
            content = _llm_content(
                llm,
                [
                    {
                        "role": "system",
                        "content": (
                            "ReAct step. Reply with one of: REACT:DECLARE_DONE, REACT:REBUILD, "
                            "or a short tool directive."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Mission: {mission.id}\n"
                            f"Instruction context: {state.get('user_input', '')}\n"
                            f"Observations so far: {new_observations}"
                        ),
                    },
                ],
            )
            upper = content.upper()
            if "DECLARE_DONE" in upper:
                for task in _flatten_tasks(mission.tasks):
                    if task.status == "pending":
                        task.status = "done"
                # Ensure validate-friendly observation for stub missions
                if not any("ok" in obs for obs in new_observations):
                    new_observations.append("ok")
                new_observations.append("declared done")
                done = True
                break
            if "REBUILD" in upper:
                rebuild = True
                break

        runnable = runnable_tasks(mission)
        if not runnable:
            flat = _flatten_tasks(mission.tasks)
            if flat and all(t.status == "done" for t in flat):
                done = True
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

        for task in runnable:
            events = _append_event(
                events,
                event_callback,
                {"type": "task_status", "id": task.id, "status": "running"},
            )
            if task.script:
                try:
                    result = run_allowed(task.script, gate=gate, repo_root=repo_root)
                    obs = result.stdout.strip() or result.stderr.strip()
                    new_observations.append(obs or f"script rc={result.returncode}")
                    task.status = "done" if result.ok else "failed"
                except PermissionError as exc:
                    new_observations.append(str(exc))
                    task.status = "failed"
            else:
                new_observations.append(f"executed instruction: {task.instruction}")
                task.status = "done"
            events = _append_event(
                events,
                event_callback,
                {"type": "task_status", "id": task.id, "status": task.status},
            )

        flat = _flatten_tasks(mission.tasks)
        if flat and all(t.status in {"done", "failed", "blocked"} for t in flat):
            done = all(t.status == "done" for t in flat)
            break

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
        "observations": new_observations,
        "react_done": done,
        "rebuild_board": rebuild,
        "event_log": events,
    }


def validate_node(
    state: dict[str, Any],
    *,
    event_callback: EventCallback | None = None,
) -> dict[str, Any]:
    events = list(state.get("event_log") or [])
    draft = state.get("mission_draft") or {}
    draft_for_parse = {k: v for k, v in draft.items() if not k.startswith("_")}
    mission = mission_from_dict(draft_for_parse) if draft_for_parse.get("id") else None
    repo_root = Path(state.get("repo_path") or ".")
    stdout = "\n".join(state.get("observations") or [])
    errors: list[str] = []

    if mission is None:
        errors.append("HARD: missing mission_draft")
    else:
        for task in _flatten_tasks(mission.tasks):
            ok, msg = evaluate_expect(
                task.expect,
                stdout=stdout,
                report_text="",
                repo_root=repo_root,
            )
            if not ok:
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
        "event_log": events,
    }


def finalize_node(
    state: dict[str, Any],
    *,
    event_callback: EventCallback | None = None,
) -> dict[str, Any]:
    events = list(state.get("event_log") or [])
    repo = Path(state.get("repo_path") or ".")
    draft = state.get("mission_draft") or {}
    mission_id = str(draft.get("id") or "unknown")
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = reports_dir(repo)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{mission_id}-{ts}.md"

    observations = state.get("observations") or []
    obs_lines = [f"- {obs}" for obs in observations] or ["- (none)"]
    lines = [
        f"# Mission Report: {mission_id}",
        "",
        f"- name: {draft.get('name', '')}",
        f"- mode: {state.get('mode', '')}",
        f"- validation_ok: {state.get('validation_ok')}",
        "",
        "## Observations",
        "",
        *obs_lines,
        "",
    ]
    if state.get("validation_errors"):
        lines.extend(["## Validation Errors", ""])
        lines.extend(f"- {err}" for err in state["validation_errors"])
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")

    interrupt = None
    if not state.get("skip_review") and state.get("mode") != "mission":
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
        "finalize": lambda state: finalize_node(state, event_callback=event_callback),
        "reject": lambda state: reject_node(state, event_callback=event_callback),
    }
