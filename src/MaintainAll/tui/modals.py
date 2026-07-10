"""Modal screens: detail, review, settings, solidify."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static, TextArea

from MaintainAll.config import Settings
from MaintainAll.missions.models import Mission
from MaintainAll.skills.models import SkillMeta


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
            yield VerticalScroll(Static(self._body(), id="detail-body"))
            yield Button("Close", id="detail-close", variant="primary")

    def _body(self) -> str:
        obj = self.obj
        if self.kind == "mission" and isinstance(obj, Mission):
            cmds = "\n".join(
                f"  - {c.pattern} (cwd={c.cwd})" for c in obj.allowed_commands
            ) or "  (none)"
            skills = ", ".join(obj.skills) or "(none)"
            schedule = obj.schedule or "(none)"
            return (
                f"ID: {obj.id}\n"
                f"Name: {obj.name}\n\n"
                f"Description:\n{obj.description}\n\n"
                f"Skills: {skills}\n"
                f"Schedule: {schedule}\n\n"
                f"Allowed commands:\n{cmds}\n"
            )
        if self.kind == "skill" and isinstance(obj, SkillMeta):
            return (
                f"Name: {obj.name}\n\n"
                f"Description:\n{obj.description}\n\n"
                f"Path: {obj.path}\n"
            )
        if isinstance(obj, dict):
            lines = [f"{k}: {v}" for k, v in obj.items()]
            return "\n".join(lines)
        return str(obj)

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
        summary = (
            f"Mission: {draft.get('name') or draft.get('id') or '?'}\n"
            f"Description: {draft.get('description') or '(none)'}\n"
            f"Tasks: {len(draft.get('tasks') or [])}\n"
            f"Allowed commands: {len(draft.get('allowed_commands') or [])}"
        )
        with Vertical(id="review-modal", classes="modal-box"):
            yield Label("Review mission board", classes="modal-title")
            yield Static(summary, id="review-summary")
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
