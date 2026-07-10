"""MaintainAll AI-mode TUI — layout C."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, ListView, Static

from MaintainAll.config import (
    Settings,
    load_settings,
    migrate_legacy_json,
    save_non_secrets,
    set_secret,
)
from MaintainAll.graph.llm import build_chat_model
from MaintainAll.graph.workflow import run_session
from MaintainAll.memory.session import SessionMemory
from MaintainAll.missions import load_missions, solidify_mission
from MaintainAll.missions.models import Mission
from MaintainAll.paths import config_dir, missions_dir, skills_dir
from MaintainAll.skills import load_skills
from MaintainAll.skills.models import SkillMeta
from MaintainAll.tui.modals import DetailModal, ReviewModal, SettingsModal, SolidifyModal
from MaintainAll.tui.panes import ChatInput, ChatStream, IdleSidebar, RunStatePane

MODES = ("readonly", "restricted", "unlimited")


class MaintainAllApp(App[None]):
    """AIOps agent console — chat stream + missions/skills sidebar."""

    TITLE = "MaintainAll"
    SUB_TITLE = "AI"

    CSS = """
    Screen {
        layout: vertical;
    }
    #main-row {
        height: 1fr;
    }
    #center-pane {
        width: 1fr;
        height: 1fr;
    }
    #chat-stream {
        height: 1fr;
        border: solid $primary;
        margin: 0 1 0 0;
    }
    #chat-input {
        dock: bottom;
        margin: 0 1 0 0;
    }
    #sidebar {
        width: 30%;
        min-width: 28;
        height: 1fr;
        border: solid $accent;
        padding: 0 1;
    }
    .sidebar-heading {
        text-style: bold;
        margin-top: 1;
        color: $accent;
    }
    #mode-banner {
        dock: top;
        height: 1;
        padding: 0 1;
        background: $surface;
        color: $text;
    }
    .modal-box {
        width: 70%;
        max-width: 90;
        height: auto;
        max-height: 90%;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }
    .modal-title {
        text-style: bold;
        margin-bottom: 1;
    }
    .modal-actions {
        height: auto;
        margin-top: 1;
        align: center middle;
    }
    .modal-actions Button {
        margin: 0 1;
    }
    #settings-modal {
        width: 80%;
        max-height: 90%;
    }
    #settings-modal Input, #settings-modal Select {
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("shift+tab", "cycle_mode", "Cycle mode"),
        Binding("f1", "settings", "Settings"),
        Binding("escape", "close_modal", "Close", show=False),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.settings: Settings = Settings()
        self.memory = SessionMemory()
        self.missions: list[Mission] = []
        self.skills: list[SkillMeta] = []
        self._running = False
        self._run_pane: RunStatePane | None = None
        self._current_draft: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(self._banner_text(), id="mode-banner")
        with Horizontal(id="main-row"):
            with Vertical(id="center-pane"):
                yield ChatStream(id="chat-stream")
                yield ChatInput()
            yield Vertical(id="sidebar")
        yield Footer()

    def on_mount(self) -> None:
        self._bootstrap_config()
        self.settings = load_settings()
        self.memory.mode = self.settings.agent_mode
        self._reload_catalog()
        self._show_idle_sidebar()
        self._refresh_banner()
        stream = self.query_one("#chat-stream", ChatStream)
        stream.write("[dim]MaintainAll AI mode ready. Type a request and press Enter.[/]")
        stream.write(
            f"[dim]Loaded {len(self.missions)} missions, {len(self.skills)} skills. "
            f"Mode: {self.memory.mode}[/]"
        )

    def _bootstrap_config(self) -> None:
        cfg = config_dir()
        legacy = Path.home() / ".maintainall.json"
        if legacy.exists() and not (cfg / "config.toml").exists():
            try:
                migrate_legacy_json(legacy, config_dir=cfg)
                self.notify("Migrated ~/.maintainall.json → config.toml", timeout=4)
            except Exception as exc:
                self.notify(f"Legacy migrate failed: {exc}", severity="error")

    def _banner_text(self) -> str:
        mode = getattr(self, "memory", None).mode if getattr(self, "memory", None) else "readonly"
        return f"MaintainAll · AI · mode: {mode} · Shift+Tab"

    def _refresh_banner(self) -> None:
        try:
            self.query_one("#mode-banner", Static).update(self._banner_text())
        except Exception:
            pass
        self.sub_title = f"AI · {self.memory.mode}"

    def _repo(self) -> Path:
        return Path(self.settings.repo_path)

    def _reload_catalog(self) -> None:
        repo = self._repo()
        try:
            self.missions = load_missions(missions_dir(repo))
        except Exception:
            self.missions = []
        try:
            self.skills = load_skills(skills_dir(repo))
        except Exception:
            self.skills = []

    def _show_idle_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar", Vertical)
        sidebar.remove_children()
        sidebar.mount(
            IdleSidebar(missions=self.missions, skills=self.skills, id="idle-sidebar")
        )
        self._run_pane = None

    def _show_run_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar", Vertical)
        sidebar.remove_children()
        pane = RunStatePane(id="run-sidebar")
        sidebar.mount(pane)
        self._run_pane = pane
        if self._current_draft:
            pane.load_mission(self._current_draft)
        elif self.memory.mission:
            pane.load_mission(self.memory.mission)

    # ── bindings ──────────────────────────────────────────────

    def action_cycle_mode(self) -> None:
        if self._running:
            self.notify("Cannot change mode while a session is running", severity="warning")
            return
        idx = MODES.index(self.memory.mode) if self.memory.mode in MODES else 0
        new_mode = MODES[(idx + 1) % len(MODES)]
        self.memory.mode = new_mode
        self.settings = self.settings.model_copy(update={"agent_mode": new_mode})
        self._refresh_banner()
        if new_mode == "restricted":
            self.notify(
                "Restricted mode: whitelist commands only (leaving pure readonly)",
                severity="warning",
                timeout=5,
            )
        else:
            self.notify(f"Mode: {new_mode}", timeout=2)

    def action_settings(self) -> None:
        self.push_screen(SettingsModal(self.settings), self._on_settings_result)

    def action_close_modal(self) -> None:
        if len(self.screen_stack) > 1:
            self.pop_screen()

    def _on_settings_result(self, result: Settings | None) -> None:
        if result is None:
            return
        api_key = getattr(result, "_pending_api_key", "") or ""
        smtp_password = getattr(result, "_pending_smtp_password", "") or ""
        # Strip pending attrs before save
        clean = result.model_copy()
        save_non_secrets(clean)
        if api_key.strip():
            set_secret("api_key", api_key.strip())
        if smtp_password:
            set_secret("smtp_password", smtp_password)
        self.settings = load_settings()
        self.memory.mode = self.settings.agent_mode
        self._refresh_banner()
        self.notify("Settings saved", timeout=3)

    # ── sidebar selection ─────────────────────────────────────

    @on(ListView.Selected)
    def on_list_selected(self, event: ListView.Selected) -> None:
        if self._running:
            return
        data = getattr(event.item, "data", None)
        if not data:
            return
        kind, obj = data
        self.push_screen(DetailModal(kind, obj))

    # ── chat submit ───────────────────────────────────────────

    @on(Input.Submitted, "#chat-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        if self._running:
            self.notify("Session already running", severity="warning")
            return
        event.input.value = ""
        stream = self.query_one("#chat-stream", ChatStream)
        stream.write(f"\n[bold]you>[/] {text}")
        self._start_session(text)

    def _start_session(self, user_input: str) -> None:
        self._running = True
        self._current_draft = None
        self._show_run_sidebar()
        self.run_agent_session(user_input)

    @staticmethod
    def _session_llm_from_settings(settings: Settings) -> Any | None:
        key = settings.api_key.get_secret_value() if settings.api_key else None
        if not key:
            return None
        return build_chat_model(settings)

    def _invoke_agent_session(
        self,
        user_input: str,
        *,
        event_callback: Callable[[dict[str, Any]], None],
        review_callback: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        llm = self._session_llm_from_settings(self.settings)
        return run_session(
            user_input,
            settings=self.settings,
            memory=self.memory,
            review_callback=review_callback,
            event_callback=event_callback,
            llm=llm,
        )

    @work(thread=True, exclusive=True)
    def run_agent_session(self, user_input: str) -> None:
        def event_callback(event: dict[str, Any]) -> None:
            self.call_from_thread(self._handle_event, event)

        def review_callback(state: dict[str, Any]) -> dict[str, Any]:
            return self._blocking_review(state)

        key = self.settings.api_key.get_secret_value() if self.settings.api_key else None
        if not key:
            self.call_from_thread(
                self._write_info,
                "No API key configured; running without LLM (stub / script path).",
            )

        try:
            result = self._invoke_agent_session(
                user_input,
                event_callback=event_callback,
                review_callback=review_callback,
            )
        except Exception as exc:
            self.call_from_thread(self._write_error, str(exc))
            result = {}

        self.call_from_thread(self._session_finished, result)

    def _write_info(self, message: str) -> None:
        self.query_one("#chat-stream", ChatStream).write(f"[yellow]{message}[/]")

    def _write_error(self, message: str) -> None:
        self.query_one("#chat-stream", ChatStream).write(f"[bold red]error:[/] {message}")

    def _blocking_review(self, state: dict[str, Any]) -> dict[str, Any]:
        """Block worker thread until the user dismisses ReviewModal."""
        ready = threading.Event()
        box: list[dict[str, Any]] = []

        def deliver(decision: dict[str, Any] | None) -> None:
            box.append(decision or {"action": "reject", "feedback": ""})
            ready.set()

        self.call_from_thread(self._push_review, state, deliver)
        ready.wait()
        return box[0]

    def _push_review(
        self,
        state: dict[str, Any],
        deliver: Callable[[dict[str, Any] | None], None],
    ) -> None:
        draft = state.get("mission_draft")
        if isinstance(draft, dict):
            self._current_draft = draft
            if self._run_pane is not None:
                self._run_pane.load_mission(draft)

        def on_dismiss(result: dict[str, Any] | None) -> None:
            deliver(result)

        self.push_screen(ReviewModal(state), on_dismiss)

    def _handle_event(self, event: dict[str, Any]) -> None:
        stream = self.query_one("#chat-stream", ChatStream)
        stream.append_event(event)
        etype = event.get("type")
        if etype == "board" and self._run_pane is not None:
            # Prefer draft already captured; otherwise show placeholder counts
            if self._current_draft:
                self._run_pane.load_mission(self._current_draft)
        elif etype == "task_status" and self._run_pane is not None:
            self._run_pane.update_task_status(event.get("id"), str(event.get("status") or ""))
        elif etype == "cmd_count" and self._run_pane is not None:
            self._run_pane.update_cmd_count(
                str(event.get("pattern") or "*"),
                int(event.get("count") or 0),
            )
        # Sync command counts from memory if present
        if self._run_pane is not None and self.memory.command_counts:
            self._run_pane.set_cmd_counts(self.memory.command_counts)

    def _session_finished(self, result: dict[str, Any]) -> None:
        stream = self.query_one("#chat-stream", ChatStream)
        if result.get("report_path"):
            stream.write(f"[green]Report written:[/] {result['report_path']}")
        if result.get("reject_reason"):
            stream.write(f"[red]Rejected:[/] {result['reject_reason']}")

        interrupt = result.get("interrupt")
        mission = self.memory.mission
        if interrupt == "solidify" and mission is not None:
            self.push_screen(SolidifyModal(mission), self._on_solidify_result)
        else:
            self._end_running_ui()

    def _on_solidify_result(self, yes: bool | None) -> None:
        if yes and self.memory.mission is not None:
            try:
                path = solidify_mission(
                    self.memory.mission,
                    missions_root=missions_dir(self._repo()),
                )
                self.query_one("#chat-stream", ChatStream).write(
                    f"[green]Solidified:[/] {path}"
                )
                self._reload_catalog()
            except Exception as exc:
                self.notify(f"Solidify failed: {exc}", severity="error")
        elif not yes:
            self.query_one("#chat-stream", ChatStream).write(
                "[dim]Skipped solidify. Say /solidify later if needed.[/]"
            )
        self._end_running_ui()

    def _end_running_ui(self) -> None:
        self._running = False
        self._current_draft = None
        self._show_idle_sidebar()


def main() -> None:
    MaintainAllApp().run()


if __name__ == "__main__":
    main()
