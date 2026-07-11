"""Modal screens: detail, review, settings, solidify."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Collapsible, Input, Label, Select, Static, TextArea

from MaintainAll.config import Settings
from MaintainAll.graph.nodes import mission_to_dict
from MaintainAll.missions.models import Mission
from MaintainAll.skills.models import SkillMeta


def _format_expect(expect: Any) -> str:
    if expect is None:
        return "(none)"
    if isinstance(expect, dict):
        etype = expect.get("type") or "?"
        parts = [f"type={etype}"]
        for key in ("patterns", "name", "path_glob"):
            if expect.get(key) is not None:
                parts.append(f"{key}={expect[key]!r}")
        return ", ".join(parts)
    return str(expect)


def _is_leaf_task(task: dict[str, Any]) -> bool:
    return not (task.get("tasks") or [])


def _script_preview(script: str, *, max_len: int = 60) -> str:
    text = (script or "").strip().replace("\n", " ")
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _script_is_short(script: str) -> bool:
    text = script or ""
    return len(text.splitlines()) <= 3 or len(text) <= 200


def _script_summary(script: str) -> str:
    text = (script or "").strip()
    if not text:
        return "script: (empty)"
    return f"script: {_script_preview(text)}"


def _format_task_meta(
    task: dict[str, Any],
    depth: int = 0,
    *,
    include_script: bool = True,
) -> str:
    """Format task fields for review.

    When ``include_script`` is False (ReviewModal widget path), skip the script
    preview line if a Collapsible will show the body — avoid duplicating it.
    Missing scripts are still annotated.
    """
    indent = "  " * depth
    lines: list[str] = []
    tid = task.get("id") or "?"
    name = task.get("name") or tid
    lines.append(f"{indent}- [{tid}] {name}")
    needs = task.get("needs") or []
    if needs:
        lines.append(f"{indent}  needs: {', '.join(str(n) for n in needs)}")
    instruction = task.get("instruction")
    if instruction:
        lines.append(f"{indent}  instruction: {instruction}")
    if task.get("expect") is not None:
        lines.append(f"{indent}  expect: {_format_expect(task.get('expect'))}")
    if _is_leaf_task(task):
        script = task.get("script")
        has_script = bool(script and str(script).strip())
        if not has_script:
            lines.append(f"{indent}  script: (missing)")
        elif include_script:
            lines.append(f"{indent}  {_script_summary(str(script))}")
    return "\n".join(lines)


def format_mission_header(draft: dict[str, Any]) -> str:
    """Render mission metadata (no tasks) for human review."""
    lines: list[str] = []
    lines.append(f"ID: {draft.get('id', '?')}")
    lines.append(f"Name: {draft.get('name', '?')}")
    lines.append("")
    lines.append("Description:")
    lines.append(str(draft.get("description") or "(none)"))
    lines.append("")
    skills = draft.get("skills") or []
    lines.append(f"Skills: {', '.join(str(s) for s in skills) if skills else '(none)'}")
    lines.append(f"Schedule: {draft.get('schedule') or '(none)'}")
    notify = draft.get("notify") or {}
    if isinstance(notify, dict):
        oc = notify.get("on_complete", False)
        of = notify.get("on_failure", False)
        lines.append(f"Notify: on_complete={oc}, on_failure={of}")
    else:
        lines.append(f"Notify: {notify}")
    lines.append("")
    lines.append("Allowed commands:")
    cmds = draft.get("allowed_commands") or []
    if not cmds:
        lines.append("  (none)")
    else:
        for cmd in cmds:
            if isinstance(cmd, dict):
                pattern = cmd.get("pattern") or "?"
                cwd = cmd.get("cwd") or "."
                lines.append(f"  - {pattern} (cwd={cwd})")
            else:
                lines.append(f"  - {cmd}")
    return "\n".join(lines)


def _format_tasks(tasks: list[Any], depth: int = 0) -> list[str]:
    lines: list[str] = []
    for task in tasks:
        if not isinstance(task, dict):
            lines.append(f"{'  ' * depth}- {task}")
            continue
        lines.append(_format_task_meta(task, depth))
        children = task.get("tasks") or []
        if children:
            lines.extend(_format_tasks(children, depth + 1))
    return lines


def _compose_mission_tasks(tasks: list[Any], depth: int = 0) -> ComposeResult:
    """Shared task-board widgets: meta Static + Collapsible script (same as review)."""
    for task in tasks:
        if not isinstance(task, dict):
            yield Static(
                f"{'  ' * depth}- {task}",
                classes=f"review-task review-task-depth-{depth}",
            )
            continue
        # Script body lives only in Collapsible — omit duplicate preview from meta.
        yield Static(
            _format_task_meta(task, depth, include_script=False),
            classes=f"review-task review-task-depth-{depth}",
        )
        script = task.get("script")
        if _is_leaf_task(task) and script and str(script).strip():
            script_text = str(script)
            with Collapsible(
                title="script",
                collapsed=not _script_is_short(script_text),
                classes="review-script",
            ):
                yield Static(script_text, classes="script-code")
        children = task.get("tasks") or []
        if children:
            yield from _compose_mission_tasks(children, depth + 1)


def compose_mission_board(draft: dict[str, Any]) -> ComposeResult:
    """Header + Tasks list used by both DetailModal and ReviewModal."""
    yield Static(format_mission_header(draft))
    yield Static("Tasks:", classes="review-tasks-heading")
    tasks = draft.get("tasks") or []
    if not tasks:
        yield Static("  (none)", classes="review-task review-task-depth-0")
    else:
        yield from _compose_mission_tasks(tasks, depth=1)


def format_mission_draft(draft: dict[str, Any]) -> str:
    """Plain-text mission dump (tests / logs). UI boards use ``compose_mission_board``."""
    lines = [format_mission_header(draft), "", "Tasks:"]
    tasks = draft.get("tasks") or []
    if not tasks:
        lines.append("  (none)")
    else:
        lines.extend(_format_tasks(tasks, 1))
    return "\n".join(lines)


def _mission_draft_from_obj(obj: Mission | dict[str, Any]) -> dict[str, Any]:
    if isinstance(obj, Mission):
        return mission_to_dict(obj, include_status=False)
    return obj


class DetailModal(ModalScreen[None]):
    """Show mission or skill details."""

    BINDINGS = [Binding("escape", "dismiss", "Close", show=True)]

    def __init__(self, kind: str, obj: Mission | SkillMeta | dict[str, Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.kind = kind
        self.obj = obj

    def compose(self) -> ComposeResult:
        with Vertical(id="detail-modal", classes="modal-box"):
            yield Label(f"{self.kind.title()} detail", classes="modal-title")
            with VerticalScroll(id="detail-body"):
                yield from self._compose_body()
            yield Button("Close", id="detail-close", variant="primary")

    def _compose_body(self) -> ComposeResult:
        obj = self.obj
        if self.kind == "mission" and isinstance(obj, (Mission, dict)):
            yield from compose_mission_board(_mission_draft_from_obj(obj))
            return
        if self.kind == "skill" and isinstance(obj, SkillMeta):
            yield Static(
                f"Name: {obj.name}\n\n"
                f"Description:\n{obj.description}\n\n"
                f"Path: {obj.path}\n"
            )
            return
        if isinstance(obj, dict):
            if "tasks" in obj:
                yield from compose_mission_board(obj)
            else:
                yield Static("\n".join(f"{k}: {v}" for k, v in obj.items()))
            return
        yield Static(str(obj))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "detail-close":
            self.dismiss(None)


class ReviewModal(ModalScreen[dict[str, Any]]):
    """Approve / Reject / Feedback for mission board review."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=True)]

    def __init__(self, state: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.state = state

    def compose(self) -> ComposeResult:
        draft = self.state.get("mission_draft") or {}
        with Vertical(id="review-modal", classes="modal-box"):
            yield Label("Review mission board", classes="modal-title")
            with VerticalScroll(id="review-body"):
                yield from compose_mission_board(draft)
            yield Label("Feedback (optional — Submit Feedback to rebuild)")
            yield TextArea(id="review-feedback")
            with Horizontal(classes="modal-actions"):
                yield Button("Approve", id="review-approve", variant="success")
                yield Button("Reject", id="review-reject", variant="error")
                yield Button("Submit Feedback", id="review-feedback-btn", variant="primary")

    def action_cancel(self) -> None:
        self.dismiss({"action": "reject", "feedback": ""})

    def on_button_pressed(self, event: Button.Pressed) -> None:
        feedback = self.query_one("#review-feedback", TextArea).text.strip()
        bid = event.button.id
        if bid == "review-approve":
            self.dismiss({"action": "approve", "feedback": ""})
        elif bid == "review-reject":
            self.dismiss({"action": "reject", "feedback": feedback})
        elif bid == "review-feedback-btn":
            self.dismiss({"action": "feedback", "feedback": feedback})

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id != "review-feedback":
            return
        line_count = event.text_area.text.count("\n") + 1
        height = min(12, max(3, line_count + 1))
        event.text_area.styles.height = height


class SolidifyModal(ModalScreen[bool]):
    """Ask whether to persist the mission draft."""

    BINDINGS = [Binding("escape", "no", "No", show=True)]

    def __init__(self, mission: Mission, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.mission = mission

    def compose(self) -> ComposeResult:
        with Vertical(id="solidify-modal", classes="modal-box"):
            yield Label("Solidify mission?", classes="modal-title")
            yield Static(
                f"Save mission '{self.mission.name}' ({self.mission.id}) "
                f"under .agents/missions/?"
            )
            with Horizontal(classes="modal-actions"):
                yield Button("Yes", id="solidify-yes", variant="success")
                yield Button("No", id="solidify-no", variant="default")

    def action_no(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "solidify-yes":
            self.dismiss(True)
        elif event.button.id == "solidify-no":
            self.dismiss(False)


class SettingsModal(ModalScreen[Settings | None]):
    """Edit non-secret settings + secret fields."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=True)]

    MODE_OPTIONS = [
        ("readonly", "readonly"),
        ("restricted", "restricted"),
        ("unlimited", "unlimited"),
    ]

    def __init__(self, settings: Settings, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.settings = settings

    def compose(self) -> ComposeResult:
        s = self.settings
        smtp = s.smtp
        with VerticalScroll(id="settings-modal", classes="modal-box"):
            yield Label("Settings", classes="modal-title")
            yield Label("Model")
            yield Input(value=s.model, id="set-model")
            yield Label("API base")
            yield Input(value=s.api_base, id="set-api-base")
            yield Label("API key")
            yield Input(password=True, placeholder="(unchanged if empty)", id="set-api-key")
            yield Label("Agent mode")
            yield Select(
                self.MODE_OPTIONS,
                value=s.agent_mode,
                id="set-agent-mode",
                allow_blank=False,
            )
            yield Label("Report language (OBSERVE / report body only)")
            yield Input(
                value=s.report_language,
                placeholder="e.g. zh-CN, en, 中文",
                id="set-report-language",
            )
            yield Label("SMTP host")
            yield Input(value=smtp.host, id="set-smtp-host")
            yield Label("SMTP port")
            yield Input(value=str(smtp.port), id="set-smtp-port")
            yield Label("SMTP user")
            yield Input(value=smtp.user, id="set-smtp-user")
            yield Label("SMTP from")
            yield Input(value=smtp.from_addr, id="set-smtp-from")
            yield Label("SMTP to (comma-separated)")
            yield Input(value=", ".join(smtp.to), id="set-smtp-to")
            yield Label("SMTP password")
            yield Input(
                password=True,
                placeholder="(unchanged if empty)",
                id="set-smtp-password",
            )
            with Horizontal(classes="modal-actions"):
                yield Button("Save", id="settings-save", variant="primary")
                yield Button("Cancel", id="settings-cancel")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "settings-cancel":
            self.dismiss(None)
            return
        if event.button.id != "settings-save":
            return

        model = self.query_one("#set-model", Input).value.strip()
        api_base = self.query_one("#set-api-base", Input).value.strip()
        api_key = self.query_one("#set-api-key", Input).value
        mode_val = self.query_one("#set-agent-mode", Select).value
        report_language = self.query_one("#set-report-language", Input).value.strip()
        host = self.query_one("#set-smtp-host", Input).value.strip()
        port_raw = self.query_one("#set-smtp-port", Input).value.strip() or "587"
        user = self.query_one("#set-smtp-user", Input).value.strip()
        from_addr = self.query_one("#set-smtp-from", Input).value.strip()
        to_raw = self.query_one("#set-smtp-to", Input).value.strip()
        smtp_password = self.query_one("#set-smtp-password", Input).value

        try:
            port = int(port_raw)
        except ValueError:
            port = 587
        to_list = [p.strip() for p in to_raw.split(",") if p.strip()]
        agent_mode = mode_val if mode_val in ("readonly", "restricted", "unlimited") else "readonly"

        from MaintainAll.config import SmtpSettings

        updated = self.settings.model_copy(
            update={
                "model": model or self.settings.model,
                "api_base": api_base or self.settings.api_base,
                "agent_mode": agent_mode,
                "report_language": report_language or self.settings.report_language,
                "smtp": SmtpSettings(
                    host=host,
                    port=port,
                    user=user,
                    from_addr=from_addr,
                    to=to_list,
                ),
            }
        )
        # Stash secrets on the object for the app to persist via set_secret
        updated._pending_api_key = api_key  # type: ignore[attr-defined]
        updated._pending_smtp_password = smtp_password  # type: ignore[attr-defined]
        self.dismiss(updated)
