from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_report(mission_id: str, body: str, reports_root: Path) -> Path:
    reports_root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = reports_root / f"{mission_id}-{ts}.md"
    path.write_text(body, encoding="utf-8")
    return path


def _zh_titles(report_language: str) -> bool:
    return (report_language or "").strip().lower().startswith("zh")


def _expect_summary(expect: Any) -> str:
    if not isinstance(expect, dict):
        return ""
    etype = str(expect.get("type") or "").strip()
    if etype == "contains":
        patterns = expect.get("patterns") or []
        joined = ", ".join(str(p) for p in patterns if str(p).strip())
        return f"contains: {joined}" if joined else "contains"
    if etype == "report_section":
        name = expect.get("name") or ""
        return f"report_section: {name}" if name else "report_section"
    if etype == "file_exists":
        path_glob = expect.get("path_glob") or ""
        return f"file_exists: {path_glob}" if path_glob else "file_exists"
    return etype or ""


def _script_preview(script: Any) -> str:
    if not script:
        return ""
    line = str(script).strip().splitlines()[0]
    if len(line) > 80:
        return line[:77] + "..."
    return line


def _flatten_task_dicts(tasks: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        out.append(task)
        out.extend(_flatten_task_dicts(task.get("tasks") or []))
    return out


def _summary_conclusion(
    validation_ok: bool | None,
    errors: list[str],
    *,
    zh: bool,
) -> str:
    if validation_ok:
        return "成功" if zh else "Success"
    if errors:
        first = str(errors[0])
        if zh:
            return f"失败：{first}"
        return f"Failed: {first}"
    if zh:
        return "失败"
    return "Failed"


def format_mission_report(state: dict[str, Any]) -> str:
    """Build a structured markdown mission report from graph state."""
    draft = state.get("mission_draft") or {}
    mission_id = str(draft.get("id") or "unknown")
    report_language = (state.get("report_language") or "zh-CN").strip() or "zh-CN"
    zh = _zh_titles(report_language)

    validation_ok = state.get("validation_ok")
    errors = list(state.get("validation_errors") or [])
    observations = list(state.get("observations") or [])
    report_draft = (state.get("report_draft") or "").strip()

    if zh:
        summary_title = "## 摘要 / Summary"
        board_title = "## 任务板"
        exec_title = "## 执行记录"
        body_title = "## 报告正文"
        validate_title = "## 校验结果"
        validation_label = "通过" if validation_ok else "失败"
        conclusion_label = "结论"
        name_label = "名称 / name"
        mode_label = "模式 / mode"
        validate_field = "校验 / validation"
        no_body = "(无 OBSERVE 正文)"
        no_errors = "无"
    else:
        summary_title = "## Summary"
        board_title = "## Task Board"
        exec_title = "## Execution Log"
        body_title = "## Report Body"
        validate_title = "## Validation"
        validation_label = "pass" if validation_ok else "fail"
        conclusion_label = "Conclusion"
        name_label = "name"
        mode_label = "mode"
        validate_field = "validation"
        no_body = "(no OBSERVE body)"
        no_errors = "none"

    conclusion = _summary_conclusion(validation_ok, errors, zh=zh)

    lines = [
        f"# Mission Report: {mission_id}",
        "",
        summary_title,
        f"- {name_label}: {draft.get('name', '')}",
        f"- {mode_label}: {state.get('mode', '')}",
        f"- {validate_field}: {validation_label}",
        f"- {conclusion_label}: {conclusion}",
        "",
        board_title,
        f"- description: {draft.get('description', '')}",
    ]

    for cmd in draft.get("allowed_commands") or []:
        if isinstance(cmd, dict):
            pattern = cmd.get("pattern") or ""
            cwd = cmd.get("cwd") or "."
        else:
            pattern = str(cmd)
            cwd = "."
        lines.append(f"- allowed_commands: {pattern} ({cwd})")

    for task in _flatten_task_dicts(draft.get("tasks") or []):
        tid = task.get("id") or "?"
        tname = task.get("name") or ""
        expect = _expect_summary(task.get("expect"))
        script = _script_preview(task.get("script"))
        task_line = f"- tasks: {tid}, {tname}, {expect}"
        if script:
            task_line += f", script: {script}"
        lines.append(task_line)

    lines.extend(["", exec_title, ""])
    if observations:
        for idx, obs in enumerate(observations, start=1):
            lines.append(f"{idx}. {obs}")
    else:
        lines.append("1. (none)")

    lines.extend(["", body_title, ""])
    lines.append(report_draft if report_draft else no_body)

    lines.extend(["", validate_title, f"- validation_ok: {validation_ok}"])
    if errors:
        for err in errors:
            lines.append(f"- {err}")
    else:
        lines.append(f"- {no_errors}")

    return "\n".join(lines) + "\n"
