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
from MaintainAll.tui.links import try_open_url


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


class LinkOfferModal(ModalScreen[None]):
    """Show an external URL/path for headless or when browser open is unsafe.

    Copies the target to the clipboard when possible so the user can paste it
    into a browser on their local machine.
    """

    BINDINGS = [Binding("escape", "close", "Close", show=True)]

    def __init__(self, title: str, target: str, note: str = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._target = target
        self._note = note

    def compose(self) -> ComposeResult:
        with Vertical(id="link-offer-modal", classes="modal-box"):
            yield Label(self._title, classes="modal-title")
            if self._note:
                yield Static(self._note, id="link-offer-note")
            yield Label("URL / path (copy to your local browser):")
            yield Input(value=self._target, id="link-offer-target")
            with Horizontal(classes="modal-actions"):
                yield Button("Copy", id="link-offer-copy", variant="primary")
                yield Button("Close", id="link-offer-close")

    def on_mount(self) -> None:
        self._copy_target(silent=True)

    def _copy_target(self, *, silent: bool = False) -> None:
        try:
            self.app.copy_to_clipboard(self._target)
        except Exception:
            if not silent:
                self.notify("Clipboard unavailable — select the URL and copy manually", severity="warning")
            return
        if not silent:
            self.notify("Copied to clipboard", timeout=2)

    def action_close(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "link-offer-copy":
            self._copy_target()
        elif event.button.id == "link-offer-close":
            self.dismiss(None)


class SettingsModal(ModalScreen[Settings | None]):
    """Edit non-secret settings + secret fields."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=True)]

    MODE_OPTIONS = [
        ("readonly", "readonly"),
        ("restricted", "restricted"),
        ("unlimited", "unlimited"),
    ]

    REPORT_LANGUAGE_OPTIONS = [
        ("中文 (zh-CN)", "zh-CN"),
        ("English (en)", "en"),
        ("日本語 (ja)", "ja"),
        ("한국어 (ko)", "ko"),
        ("Français (fr)", "fr"),
        ("Deutsch (de)", "de"),
        ("Español (es)", "es"),
        ("Русский (ru)", "ru"),
    ]

    PROVIDER_OPTIONS = [
        ("Gmail", "gmail"),
        ("Outlook", "outlook"),
        ("Custom", "custom"),
    ]

    AUTH_OPTIONS = [
        ("Password / App password", "password"),
        ("OAuth", "oauth"),
    ]

    _SECRET_MASK = "***"

    def __init__(self, settings: Settings, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.settings = settings
        self._pending_refresh_token = ""
        self._oauth_just_authorized = False

    @staticmethod
    def _secret_is_set(secret: Any) -> bool:
        if secret is None:
            return False
        try:
            return bool(secret.get_secret_value())
        except Exception:
            return False

    def _secret_field_value(self, secret: Any) -> str:
        return self._SECRET_MASK if self._secret_is_set(secret) else ""

    def _pending_secret(self, raw: str) -> str:
        """Empty or mask → leave unchanged; anything else → new secret value."""
        text = (raw or "").strip()
        if not text or text == self._SECRET_MASK:
            return ""
        return text

    def _report_language_value(self) -> str:
        current = (self.settings.report_language or "zh-CN").strip()
        known = {value for _label, value in self.REPORT_LANGUAGE_OPTIONS}
        return current if current in known else "zh-CN"

    def _smtp_provider_value(self) -> str:
        p = getattr(self.settings.smtp, "provider", "custom") or "custom"
        return p if p in ("gmail", "outlook", "custom") else "custom"

    def _smtp_auth_value(self) -> str:
        a = getattr(self.settings.smtp, "auth", "password") or "password"
        return a if a in ("password", "oauth") else "password"

    def _oauth_status_text(self) -> str:
        if self._oauth_just_authorized or self._secret_is_set(
            self.settings.smtp_refresh_token
        ):
            return "OAuth: authorized"
        return "OAuth: not authorized"

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
            yield Input(
                value=self._secret_field_value(s.api_key),
                password=True,
                placeholder="",
                id="set-api-key",
            )
            yield Label("Agent mode")
            yield Select(
                self.MODE_OPTIONS,
                value=s.agent_mode,
                id="set-agent-mode",
                allow_blank=False,
            )
            yield Label("Report language (OBSERVE / report body only)")
            yield Select(
                self.REPORT_LANGUAGE_OPTIONS,
                value=self._report_language_value(),
                id="set-report-language",
                allow_blank=False,
            )
            yield Label("Data dir (reports / logs / history)")
            yield Input(value=s.data_dir, id="set-data-dir")

            yield Label("Mail provider")
            yield Select(
                self.PROVIDER_OPTIONS,
                value=self._smtp_provider_value(),
                id="set-smtp-provider",
                allow_blank=False,
            )
            yield Static("", id="smtp-setup-hint")
            with Horizontal(id="smtp-setup-links"):
                yield Button("Open console…", id="smtp-open-console")
                yield Button("Authorize OAuth…", id="smtp-oauth-authorize")
            yield Label(self._oauth_status_text(), id="smtp-oauth-status")

            # OAuth (Gmail / Outlook) — above account fields
            yield Label("OAuth client ID", id="lbl-smtp-client-id")
            yield Input(
                value=getattr(smtp, "client_id", "") or "",
                id="set-smtp-client-id",
            )
            yield Label("OAuth tenant ID (Outlook)", id="lbl-smtp-tenant-id")
            yield Input(
                value=getattr(smtp, "tenant_id", "common") or "common",
                id="set-smtp-tenant-id",
            )
            yield Label("OAuth client secret (optional)", id="lbl-smtp-client-secret")
            yield Input(
                value=self._secret_field_value(s.smtp_client_secret),
                password=True,
                placeholder="",
                id="set-smtp-client-secret",
            )

            yield Label("Account", id="lbl-smtp-user")
            yield Input(value=smtp.user, id="set-smtp-user")
            yield Label("From", id="lbl-smtp-from")
            yield Input(value=smtp.from_addr, id="set-smtp-from")
            yield Label("To (comma-separated)", id="lbl-smtp-to")
            yield Input(value=", ".join(smtp.to), id="set-smtp-to")

            # Custom SMTP only
            yield Label("SMTP auth (custom only)", id="lbl-smtp-auth")
            yield Select(
                self.AUTH_OPTIONS,
                value=self._smtp_auth_value(),
                id="set-smtp-auth",
                allow_blank=False,
            )
            yield Label("SMTP host", id="lbl-smtp-host")
            yield Input(value=smtp.host, id="set-smtp-host")
            yield Label("SMTP port", id="lbl-smtp-port")
            yield Input(value=str(smtp.port), id="set-smtp-port")
            yield Label("SMTP password", id="lbl-smtp-password")
            yield Input(
                value=self._secret_field_value(s.smtp_password),
                password=True,
                placeholder="",
                id="set-smtp-password",
            )

            with Horizontal(classes="modal-actions"):
                yield Button("Save", id="settings-save", variant="primary")
                yield Button("Cancel", id="settings-cancel")

    def on_mount(self) -> None:
        self._sync_smtp_field_visibility()
        self._refresh_smtp_setup_hint()

    def _refresh_smtp_setup_hint(self) -> None:
        from MaintainAll.notify.providers import provider_setup_hint

        provider = self.query_one("#set-smtp-provider", Select).value
        hint = provider_setup_hint(str(provider), auth="oauth")
        try:
            widget = self.query_one("#smtp-setup-hint", Static)
        except Exception:
            return
        widget.update(hint if hint else "")
        widget.styles.display = "block" if hint else "none"

    def _sync_smtp_field_visibility(self) -> None:
        provider = self.query_one("#set-smtp-provider", Select).value
        api_mode = provider in ("gmail", "outlook")
        custom_mode = provider == "custom"

        def _show(widget_id: str, visible: bool) -> None:
            try:
                w = self.query_one(f"#{widget_id}")
            except Exception:
                return
            w.styles.display = "block" if visible else "none"

        # Custom = traditional SMTP password
        for wid in (
            "lbl-smtp-auth",
            "set-smtp-auth",
            "lbl-smtp-host",
            "set-smtp-host",
            "lbl-smtp-port",
            "set-smtp-port",
            "lbl-smtp-password",
            "set-smtp-password",
        ):
            _show(wid, custom_mode)

        # Gmail / Outlook = OAuth + HTTP API
        for wid in (
            "smtp-setup-hint",
            "smtp-setup-links",
            "smtp-open-console",
            "smtp-oauth-authorize",
            "smtp-oauth-status",
            "lbl-smtp-client-id",
            "set-smtp-client-id",
            "lbl-smtp-client-secret",
            "set-smtp-client-secret",
        ):
            _show(wid, api_mode)
        _show("lbl-smtp-tenant-id", api_mode and provider == "outlook")
        _show("set-smtp-tenant-id", api_mode and provider == "outlook")
        self._refresh_smtp_setup_hint()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "set-smtp-provider":
            provider = event.value
            if provider in ("gmail", "outlook", "custom"):
                from MaintainAll.notify.providers import apply_provider_preset

                current = {
                    "host": self.query_one("#set-smtp-host", Input).value,
                    "port": self.query_one("#set-smtp-port", Input).value,
                    "user": self.query_one("#set-smtp-user", Input).value,
                    "client_id": self.query_one("#set-smtp-client-id", Input).value,
                    "tenant_id": self.query_one("#set-smtp-tenant-id", Input).value,
                }
                try:
                    port = int(str(current["port"]).strip() or "587")
                except ValueError:
                    port = 587
                updated = apply_provider_preset(
                    {
                        "host": current["host"],
                        "port": port,
                        "user": current["user"],
                        "client_id": current["client_id"],
                        "tenant_id": current["tenant_id"],
                    },
                    provider,
                )
                self.query_one("#set-smtp-host", Input).value = str(updated.get("host", ""))
                self.query_one("#set-smtp-port", Input).value = str(updated.get("port", 587))
                if "auth" in updated:
                    try:
                        self.query_one("#set-smtp-auth", Select).value = updated["auth"]
                    except Exception:
                        pass
                if updated.get("tenant_id"):
                    self.query_one("#set-smtp-tenant-id", Input).value = str(
                        updated["tenant_id"]
                    )
            self._sync_smtp_field_visibility()
        elif event.select.id == "set-smtp-auth":
            self._sync_smtp_field_visibility()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _present_external_link(self, title: str, url: str, *, note: str = "") -> None:
        """Prefer showing/copying the URL; only open a browser when safe."""
        opened = try_open_url(url)
        default_note = (
            "No local GUI browser (headless / remote). "
            "Open this URL on your laptop, then paste the Client ID back here."
            if not opened
            else "Also copied below if you need it again."
        )
        self.app.push_screen(
            LinkOfferModal(title, url, note=note or default_note)
        )
        if opened:
            self.notify("Tried to open in browser; URL also shown for copy", timeout=3)

    def _open_smtp_console(self) -> None:
        from MaintainAll.notify.providers import PROVIDER_SETUP_LINKS

        provider = self.query_one("#set-smtp-provider", Select).value
        links = PROVIDER_SETUP_LINKS.get(str(provider)) or {}
        if provider == "outlook":
            # Any Entra directory works. Azure free is default (M365 Dev often
            # rejects: "You don't currently qualify for a sandbox").
            url = links.get("get_directory") or links.get("console")
            if not url:
                self.notify("No console link for this provider", severity="warning")
                return
            entra = links.get("console") or ""
            m365 = links.get("get_directory_m365_dev") or ""
            note = "\n".join(
                [
                    "Outlook uses Microsoft Graph sendMail (not SMTP).",
                    "You cannot register an app on a personal MSA alone — need a directory.",
                    "",
                    "1) Open this Azure free signup (creates an Entra directory).",
                    "   (If you already have Azure/Entra, skip to step 2.)",
                    "2) Entra → App registrations → New registration.",
                    "3) Platform: Mobile and desktop → redirect http://127.0.0.1",
                    "4) Enable public client flows; add delegated Mail.Send + offline_access.",
                    f"5) Apps list: {entra}",
                    "6) Paste Client ID here, then click Authorize OAuth.",
                    "",
                    f"Alternate (often restricted): M365 Developer Program — {m365}",
                ]
            )
            self._present_external_link(
                "Outlook: create Azure / Entra directory",
                url,
                note=note,
            )
            return

        url = links.get("new_app") or links.get("console") or links.get("api_enable")
        if not url:
            self.notify("No console link for this provider", severity="warning")
            return
        if provider == "gmail":
            enable = links.get("api_enable") or url
            note = "\n".join(
                [
                    "Gmail uses Gmail API (not SMTP).",
                    "",
                    f"1) Enable Gmail API: {enable}",
                    "2) Credentials → Create OAuth client → Desktop app.",
                    "3) Paste Client ID here.",
                    "4) Click Authorize OAuth (scope gmail.send).",
                ]
            )
            self._present_external_link(
                "Gmail API — create OAuth client",
                url,
                note=note,
            )
            return
        self._present_external_link(
            "Create OAuth Client ID",
            url,
            note="\n".join(
                [
                    "Open this URL on your laptop.",
                    "Create a Desktop / public client, then paste the Client ID into Settings.",
                ]
            ),
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:


        if event.button.id == "settings-cancel":
            self.dismiss(None)
            return
        if event.button.id == "smtp-open-console":
            self._open_smtp_console()
            return
        if event.button.id == "smtp-oauth-authorize":
            self._run_oauth_authorize()
            return
        if event.button.id != "settings-save":
            return

        model = self.query_one("#set-model", Input).value.strip()
        api_base = self.query_one("#set-api-base", Input).value.strip()
        api_key = self._pending_secret(self.query_one("#set-api-key", Input).value)
        mode_val = self.query_one("#set-agent-mode", Select).value
        lang_val = self.query_one("#set-report-language", Select).value
        provider_val = self.query_one("#set-smtp-provider", Select).value
        auth_val = self.query_one("#set-smtp-auth", Select).value
        host = self.query_one("#set-smtp-host", Input).value.strip()
        port_raw = self.query_one("#set-smtp-port", Input).value.strip() or "587"
        user = self.query_one("#set-smtp-user", Input).value.strip()
        from_addr = self.query_one("#set-smtp-from", Input).value.strip()
        to_raw = self.query_one("#set-smtp-to", Input).value.strip()
        smtp_password = self._pending_secret(
            self.query_one("#set-smtp-password", Input).value
        )
        client_id = self.query_one("#set-smtp-client-id", Input).value.strip()
        tenant_id = self.query_one("#set-smtp-tenant-id", Input).value.strip() or "common"
        smtp_client_secret = self._pending_secret(
            self.query_one("#set-smtp-client-secret", Input).value
        )

        try:
            port = int(port_raw)
        except ValueError:
            port = 587
        to_list = [p.strip() for p in to_raw.split(",") if p.strip()]
        agent_mode = (
            mode_val if mode_val in ("readonly", "restricted", "unlimited") else "readonly"
        )
        known_langs = {value for _label, value in self.REPORT_LANGUAGE_OPTIONS}
        report_language = (
            lang_val if lang_val in known_langs else self.settings.report_language
        )
        data_dir = self.query_one("#set-data-dir", Input).value.strip() or self.settings.data_dir
        provider = (
            provider_val if provider_val in ("gmail", "outlook", "custom") else "custom"
        )
        # Gmail/Outlook always OAuth API; custom always SMTP password
        auth = "oauth" if provider in ("gmail", "outlook") else "password"

        from MaintainAll.config import SmtpSettings
        from MaintainAll.notify.providers import apply_provider_preset

        smtp_data = apply_provider_preset(
            {
                "host": host,
                "port": port,
                "user": user,
                "from_addr": from_addr,
                "to": to_list,
                "client_id": client_id,
                "tenant_id": tenant_id,
                "auth": auth,
                "security": "starttls",
            },
            provider,
        )
        smtp_data["auth"] = auth
        if provider == "custom":
            smtp_data["host"] = host
            smtp_data["port"] = port
        else:
            smtp_data["host"] = ""

        updated = self.settings.model_copy(
            update={
                "model": model or self.settings.model,
                "api_base": api_base or self.settings.api_base,
                "agent_mode": agent_mode,
                "report_language": report_language or self.settings.report_language,
                "data_dir": data_dir,
                "smtp": SmtpSettings(
                    provider=smtp_data["provider"],
                    auth=smtp_data["auth"],
                    host=smtp_data.get("host", host),
                    port=int(smtp_data.get("port", port)),
                    security=smtp_data.get("security", "starttls"),
                    user=user,
                    from_addr=from_addr,
                    to=to_list,
                    client_id=client_id,
                    tenant_id=tenant_id,
                ),
            }
        )
        updated._pending_api_key = api_key  # type: ignore[attr-defined]
        updated._pending_smtp_password = smtp_password  # type: ignore[attr-defined]
        updated._pending_smtp_refresh_token = self._pending_refresh_token  # type: ignore[attr-defined]
        updated._pending_smtp_client_secret = smtp_client_secret  # type: ignore[attr-defined]
        self.dismiss(updated)

    def _present_oauth_authorize_url(self, url: str, port: int) -> None:
        note = "\n".join(
            [
                "Waiting for login in the browser…",
                "",
                "On this machine with a real GUI browser, open the URL below.",
                "",
                "If you are on SSH / Cursor remote (no local browser):",
                f"  1) In another terminal: ssh -L {port}:127.0.0.1:{port} <user>@<this-host>",
                "  2) Open the URL on your laptop browser.",
                "  3) After Google/Microsoft consent, the callback hits this server.",
                "",
                "Do not use Cursor's remote BROWSER helper — it breaks the redirect.",
            ]
        )
        self.app.push_screen(LinkOfferModal("Authorize OAuth", url, note=note))
        self.notify(
            f"Authorize URL ready (callback port {port}) — open it, then wait",
            timeout=6,
        )

    def _run_oauth_authorize(self) -> None:
        provider = self.query_one("#set-smtp-provider", Select).value
        if provider not in ("gmail", "outlook"):
            self.notify("OAuth authorize requires Gmail or Outlook provider", severity="warning")
            return
        client_id = self.query_one("#set-smtp-client-id", Input).value.strip()
        if not client_id:
            self.notify("Fill OAuth client ID first", severity="warning")
            return
        tenant_id = self.query_one("#set-smtp-tenant-id", Input).value.strip() or "common"
        user = self.query_one("#set-smtp-user", Input).value.strip()
        client_secret_raw = self.query_one("#set-smtp-client-secret", Input).value
        client_secret = self._pending_secret(client_secret_raw)
        if not client_secret and self._secret_is_set(self.settings.smtp_client_secret):
            client_secret = self.settings.smtp_client_secret.get_secret_value()  # type: ignore[union-attr]
        if not client_secret:
            client_secret = None

        self.notify("Starting OAuth — waiting for browser login…", timeout=4)

        def _work() -> str:
            from MaintainAll.notify.oauth import run_localhost_oauth_flow

            def on_ready(url: str, port: int) -> None:
                self.app.call_from_thread(self._present_oauth_authorize_url, url, port)

            return run_localhost_oauth_flow(
                provider=provider,
                client_id=client_id,
                client_secret=client_secret,
                tenant_id=tenant_id,
                login_hint=user,
                on_ready=on_ready,
            )

        self.run_worker(_work, exclusive=True, thread=True, name="smtp-oauth")

    def on_worker_state_changed(self, event: Any) -> None:
        from textual.worker import WorkerState

        worker = getattr(event, "worker", None)
        if worker is None or getattr(worker, "name", None) != "smtp-oauth":
            return
        state = getattr(event, "state", None)
        if state == WorkerState.SUCCESS:
            token = worker.result
            if token:
                self._pending_refresh_token = str(token)
                self._oauth_just_authorized = True
                try:
                    self.query_one("#smtp-oauth-status", Label).update("OAuth: authorized")
                except Exception:
                    pass
                self.notify("OAuth authorized — click Save to persist", timeout=4)
            return
        if state == WorkerState.ERROR:
            err = getattr(worker, "error", None) or "authorize failed"
            self.notify(f"OAuth failed: {err}", severity="error", timeout=8)
