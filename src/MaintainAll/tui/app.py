"""MaintainAll AI-mode TUI — layout C."""

from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path
import threading
from typing import Any, Callable

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Footer, Header, Input, ListView, Static

from MaintainAll.config import (
    Settings,
    load_settings,
    migrate_legacy_json,
    save_non_secrets,
    set_secret,
)
from MaintainAll.graph.llm import build_chat_model
from MaintainAll.graph.nodes import mission_to_dict
from MaintainAll.graph.workflow import run_session
from MaintainAll.memory.prompt_history import append_prompt_history, load_prompt_history
from MaintainAll.memory.session import SessionMemory
from MaintainAll.missions import (
    format_mission_candidates,
    load_missions,
    parse_run_command,
    resolve_mission,
    solidify_mission,
)
from MaintainAll.missions.models import Mission
from MaintainAll.paths import config_dir, missions_dir, prompt_history_path, skills_dir
from MaintainAll.skills import load_skills
from MaintainAll.skills.models import SkillMeta
from MaintainAll.tui.cancel import SessionCancelArm
from MaintainAll.tui.modals import (
    DetailModal,
    LinkOfferModal,
    ReviewModal,
    SettingsModal,
    SolidifyModal,
)
from MaintainAll.tui.panes import (
    ChatInput,
    ChatStream,
    CompletionPopup,
    IdleSidebar,
    RunStatePane,
    slash_completion_options,
)

MODES = ("readonly", "restricted", "unlimited")


class AgentEventMsg(Message):
    """Worker → UI: graph event for the chat stream / run sidebar."""

    def __init__(self, event: dict[str, Any]) -> None:
        super().__init__()
        self.event = event


class ReviewRequestMsg(Message):
    """Worker → UI: open review modal; complete ``future`` when user decides."""

    def __init__(self, state: dict[str, Any], future: Future[dict[str, Any]]) -> None:
        super().__init__()
        self.state = state
        self.future = future


class SessionInfoMsg(Message):
    def __init__(self, message: str, *, error: bool = False) -> None:
        super().__init__()
        self.message = message
        self.error = error


class SessionDoneMsg(Message):
    def __init__(self, result: dict[str, Any]) -> None:
        super().__init__()
        self.result = result


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
        margin: 0 1 0 0;
    }
    #chat-input {
        dock: bottom;
        margin: 0 1 0 0;
    }
    #completion-popup {
        height: auto;
        max-height: 10;
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
    ReviewModal, DetailModal, SolidifyModal, SettingsModal, LinkOfferModal {
        align: center middle;
    }
    #review-modal, #detail-modal {
        width: 80%;
        max-width: 110;
        height: auto;
        max-height: 90%;
    }
    #review-body, #detail-body {
        height: 1fr;
        max-height: 24;
        margin-bottom: 1;
    }
    #review-feedback {
        height: 3;
        min-height: 3;
        max-height: 12;
        margin-bottom: 1;
    }
    .review-script {
        margin: 0 0 1 2;
    }
    .script-code {
        padding: 0 1;
        background: $boost;
        color: $text-muted;
        height: auto;
    }
    .review-task-depth-1 {
        margin-left: 2;
    }
    .review-task-depth-2 {
        margin-left: 4;
    }
    .review-task-depth-3 {
        margin-left: 6;
    }
    .review-tasks-heading {
        margin-top: 1;
        text-style: bold;
    }
    #settings-modal {
        width: 80%;
        max-height: 90%;
    }
    #settings-modal Input, #settings-modal Select {
        margin-bottom: 1;
    }
    #smtp-setup-hint {
        color: $text-muted;
        margin-bottom: 1;
        height: auto;
        width: 100%;
        max-height: 8;
    }
    #smtp-setup-links {
        height: auto;
        width: 100%;
        margin-bottom: 1;
    }
    #smtp-setup-links Button {
        width: auto;
        min-width: 16;
        margin-right: 1;
    }
    #link-offer-modal {
        width: 80%;
        max-width: 100;
        height: auto;
        max-height: 40;
    }
    #link-offer-modal #link-offer-target {
        width: 100%;
        margin-bottom: 1;
    }
    #link-offer-note {
        color: $text-muted;
        margin-bottom: 1;
        height: auto;
        max-height: 16;
        width: 100%;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("shift+tab", "cycle_mode", "Cycle mode", priority=True),
        Binding("f1", "settings", "Settings"),
        Binding("escape", "close_modal", "Close", show=False),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.settings: Settings = Settings()
        self.memory = SessionMemory()
        self.missions: list[Mission] = []
        self.skills: list[SkillMeta] = []
        # Do NOT use `_running` — Textual App owns that for the event loop.
        self._session_active = False
        self._run_pane: RunStatePane | None = None
        self._current_draft: dict[str, Any] | None = None
        self._cancel_event = threading.Event()
        self._cancel_arm = SessionCancelArm(window_s=2.0)
        self._pending_review: Future[dict[str, Any]] | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(self._banner_text(), id="mode-banner")
        with Horizontal(id="main-row"):
            with Vertical(id="center-pane"):
                yield ChatStream(id="chat-stream")
                yield CompletionPopup(id="completion-popup")
                yield ChatInput(
                    get_slash_options=self._slash_options,
                    get_missions=self._mission_catalog,
                )
            yield Vertical(id="sidebar")
        yield Footer()

    def _slash_options(self) -> list[str]:
        return slash_completion_options(self.missions)

    def _mission_catalog(self) -> list[Mission]:
        return self.missions

    def on_mount(self) -> None:
        self._bootstrap_config()
        self.settings = load_settings()
        self.memory.mode = self.settings.agent_mode
        self._reload_catalog()
        self._bind_prompt_history()
        self._show_idle_sidebar()
        self._refresh_banner()
        stream = self.query_one("#chat-stream", ChatStream)
        stream.write("[dim]MaintainAll AI mode ready. Type a request and press Enter.[/]")
        stream.write(
            f"[dim]Loaded {len(self.missions)} missions, {len(self.skills)} skills. "
            f"Mode: {self.memory.mode}[/]"
        )

    def _bind_prompt_history(self) -> None:
        path = prompt_history_path(self._repo(), data_dir=self.settings.data_dir)
        entries = load_prompt_history(path, max_size=100)

        def on_push(text: str) -> None:
            append_prompt_history(
                prompt_history_path(self._repo(), data_dir=self.settings.data_dir),
                text,
                max_size=100,
            )

        try:
            chat = self.query_one("#chat-input", ChatInput)
        except Exception:
            return
        chat.bind_history(entries, on_push=on_push, max_size=100)

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
        hint = {
            "readonly": "no exec",
            "restricted": "whitelist",
            "unlimited": "open",
        }.get(str(mode), "")
        suffix = f" ({hint})" if hint else ""
        return f"MaintainAll · AI · mode: {mode}{suffix} · Shift+Tab"

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
        if self._session_active:
            self.notify("Cannot change mode while a session is running", severity="warning")
            return
        idx = MODES.index(self.memory.mode) if self.memory.mode in MODES else 0
        new_mode = MODES[(idx + 1) % len(MODES)]
        self.memory.mode = new_mode
        self.settings = self.settings.model_copy(update={"agent_mode": new_mode})
        self._refresh_banner()
        if new_mode == "readonly":
            self.notify(
                "Readonly: plan/review only — no command execution",
                timeout=4,
            )
        elif new_mode == "restricted":
            self.notify(
                "Restricted: whitelist commands execute",
                severity="warning",
                timeout=5,
            )
        elif new_mode == "unlimited":
            self.notify(
                "Unlimited: any command may execute (no whitelist)",
                severity="error",
                timeout=6,
            )
        else:
            self.notify(f"Mode: {new_mode}", timeout=2)

    def action_settings(self) -> None:
        self.push_screen(SettingsModal(self.settings), self._on_settings_result)

    def action_close_modal(self) -> None:
        if len(self.screen_stack) > 1:
            self.pop_screen()
            return
        if self._session_active:
            self._handle_session_escape()

    def _handle_session_escape(self) -> None:
        result = self._cancel_arm.press()
        if result == "armed":
            self.notify("再按一次 Esc 取消", timeout=2)
            stream = self.query_one("#chat-stream", ChatStream)
            stream.write("再按一次 Esc 取消", markup=False)
            return
        self._request_session_cancel()

    def _request_session_cancel(self) -> None:
        self._cancel_arm.clear()
        if self._cancel_event.is_set():
            return
        self._cancel_event.set()
        stream = self.query_one("#chat-stream", ChatStream)
        stream.write("正在取消…", markup=False)
        pending = self._pending_review
        if pending is not None and not pending.done():
            pending.set_result(
                {"action": "reject", "feedback": "Cancelled by user"}
            )

    def _on_settings_result(self, result: Settings | None) -> None:
        if result is None:
            return
        api_key = getattr(result, "_pending_api_key", "") or ""
        smtp_password = getattr(result, "_pending_smtp_password", "") or ""
        smtp_refresh = getattr(result, "_pending_smtp_refresh_token", "") or ""
        smtp_client_secret = getattr(result, "_pending_smtp_client_secret", "") or ""
        # Strip pending attrs before save
        clean = result.model_copy()
        save_non_secrets(clean)
        if api_key.strip():
            set_secret("api_key", api_key.strip())
        if smtp_password:
            set_secret("smtp_password", smtp_password)
        if smtp_refresh:
            set_secret("smtp_refresh_token", smtp_refresh)
        if smtp_client_secret:
            set_secret("smtp_client_secret", smtp_client_secret)
        self.settings = load_settings()
        self.memory.mode = self.settings.agent_mode
        self._reload_catalog()
        self._bind_prompt_history()
        self._refresh_banner()
        self.notify("Settings saved", timeout=3)

    # ── sidebar selection ─────────────────────────────────────

    @on(ListView.Selected)
    def on_list_selected(self, event: ListView.Selected) -> None:
        if self._session_active:
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
        if self._session_active:
            self.notify("Session already running", severity="warning")
            return
        chat_input = event.input
        if isinstance(chat_input, ChatInput):
            chat_input.push_history(text)
        event.input.value = ""
        stream = self.query_one("#chat-stream", ChatStream)
        stream.write(f"\n[bold]you>[/] {text}")
        if text.lower() in {"/solidify", "solidify"}:
            self._offer_solidify_now()
            return
        run_query = parse_run_command(text)
        if run_query is not None:
            self._run_catalog_mission(run_query)
            return
        self._start_session(text)

    def _offer_solidify_now(self) -> None:
        stream = self.query_one("#chat-stream", ChatStream)
        mission = self.memory.mission
        if mission is None:
            stream.write("[yellow]No mission in memory to solidify.[/]")
            return
        self.push_screen(SolidifyModal(mission), self._on_solidify_result)

    def _run_catalog_mission(self, query: str) -> None:
        stream = self.query_one("#chat-stream", ChatStream)
        self._reload_catalog()
        if not self.missions:
            stream.write("[yellow]No solidified missions in .agents/missions/.[/]")
            return
        if not query:
            stream.write("[yellow]Usage:[/] /run <mission-id|name>")
            stream.write("[dim]Available:[/]")
            for line in format_mission_candidates(self.missions):
                stream.write(f"  {line}")
            return
        mission, candidates = resolve_mission(query, self.missions)
        if mission is None:
            if candidates:
                stream.write(f"[yellow]Ambiguous mission {query!r}. Candidates:[/]")
                for line in format_mission_candidates(candidates):
                    stream.write(f"  {line}")
            else:
                stream.write(f"[yellow]Unknown mission {query!r}. Available:[/]")
                for line in format_mission_candidates(self.missions):
                    stream.write(f"  {line}")
            return
        stream.write(f"[dim]Running solidified mission[/] [bold]{mission.id}[/]…")
        self._start_session(f"run mission {mission.id}", mission=mission)

    def _start_session(
        self,
        user_input: str,
        *,
        mission: Mission | None = None,
    ) -> None:
        self._session_active = True
        self._cancel_event = threading.Event()
        self._cancel_arm.clear()
        self._pending_review = None
        self._current_draft = mission_to_dict(mission) if mission is not None else None
        self._show_run_sidebar()
        stream = self.query_one("#chat-stream", ChatStream)
        stream.write(
            "[dim]working… (Esc 两次取消；LLM 可能较慢)[/]"
        )
        self.run_agent_session(user_input, mission=mission)

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
        mission: Mission | None = None,
    ) -> dict[str, Any]:
        llm = self._session_llm_from_settings(self.settings)
        cancel_event = self._cancel_event
        if mission is not None:
            return run_session(
                user_input,
                settings=self.settings,
                memory=self.memory,
                review_callback=review_callback,
                event_callback=event_callback,
                llm=llm,
                mission_draft=mission_to_dict(mission),
                mode="mission",
                skip_review=False,
                feasible=True,
                cancel_event=cancel_event,
            )
        return run_session(
            user_input,
            settings=self.settings,
            memory=self.memory,
            review_callback=review_callback,
            event_callback=event_callback,
            llm=llm,
            cancel_event=cancel_event,
        )

    @work(thread=True, exclusive=True)
    def run_agent_session(
        self,
        user_input: str,
        mission: Mission | None = None,
    ) -> None:
        cancel_event = self._cancel_event

        def event_callback(event: dict[str, Any]) -> None:
            # Non-blocking: avoids call_from_thread deadlock with the UI loop.
            self.post_message(AgentEventMsg(event))

        def review_callback(state: dict[str, Any]) -> dict[str, Any]:
            future: Future[dict[str, Any]] = Future()
            self._pending_review = future
            self.post_message(ReviewRequestMsg(state, future))
            try:
                while True:
                    if cancel_event.is_set():
                        return {"action": "reject", "feedback": "Cancelled by user"}
                    try:
                        return future.result(timeout=0.2)
                    except TimeoutError:
                        continue
            finally:
                if self._pending_review is future:
                    self._pending_review = None

        key = self.settings.api_key.get_secret_value() if self.settings.api_key else None
        if not key:
            self.post_message(
                SessionInfoMsg(
                    "No API key configured; running without LLM (stub / script path)."
                )
            )

        try:
            result = self._invoke_agent_session(
                user_input,
                event_callback=event_callback,
                review_callback=review_callback,
                mission=mission,
            )
        except Exception as exc:
            self.post_message(SessionInfoMsg(str(exc), error=True))
            result = {}

        self.post_message(SessionDoneMsg(result))

    def on_agent_event_msg(self, message: AgentEventMsg) -> None:
        try:
            self._handle_event(message.event)
        except Exception:
            # One bad UI update must not stall the rest of the stream.
            pass

    def on_session_info_msg(self, message: SessionInfoMsg) -> None:
        if message.error:
            self._write_error(message.message)
        else:
            self._write_info(message.message)

    def on_session_done_msg(self, message: SessionDoneMsg) -> None:
        self._session_finished(message.result)

    def on_review_request_msg(self, message: ReviewRequestMsg) -> None:
        if message.future.done():
            return

        def deliver(decision: dict[str, Any] | None) -> None:
            if not message.future.done():
                message.future.set_result(
                    decision or {"action": "reject", "feedback": ""}
                )

        self._push_review(message.state, deliver)

    def _write_info(self, message: str) -> None:
        self.query_one("#chat-stream", ChatStream).write(f"[yellow]{message}[/]")

    def _write_error(self, message: str) -> None:
        self.query_one("#chat-stream", ChatStream).write(f"[bold red]error:[/] {message}")

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

        self.push_screen(ReviewModal(state), deliver)

    def _handle_event(self, event: dict[str, Any]) -> None:
        stream = self.query_one("#chat-stream", ChatStream)
        try:
            stream.append_event(event)
        except Exception:
            pass
        etype = event.get("type")
        try:
            if etype == "board" and self._run_pane is not None:
                if self._current_draft:
                    self._run_pane.load_mission(self._current_draft)
            elif etype == "task_status" and self._run_pane is not None:
                self._run_pane.update_task_status(
                    event.get("id"), str(event.get("status") or "")
                )
            elif etype == "cmd_count" and self._run_pane is not None:
                self._run_pane.update_cmd_count(
                    str(event.get("pattern") or "*"),
                    int(event.get("count") or 0),
                )
            if self._run_pane is not None and self.memory.command_counts:
                self._run_pane.set_cmd_counts(self.memory.command_counts)
        except Exception:
            pass

    def _session_finished(self, result: dict[str, Any]) -> None:
        stream = self.query_one("#chat-stream", ChatStream)
        self._cancel_arm.clear()
        self._pending_review = None

        if result.get("cancelled"):
            stream.write("已取消", markup=False)
            if result.get("log_path"):
                stream.write(f"[dim]log[/]: {result['log_path']}")
            self._end_running_ui()
            return

        report_path = result.get("report_path")
        if report_path:
            stream.write(f"[green]Report written:[/] {report_path}")
            try:
                body = Path(str(report_path)).read_text(encoding="utf-8")
            except OSError as exc:
                stream.write(f"[yellow]Could not read report:[/] {exc}")
            else:
                stream.write("[bold]── Report ──[/]")
                stream.write(body, markup=False)
                stream.write("[bold]── End report ──[/]")
        # Re-surface notify after the report dump (easy to miss mid-stream).
        for ev in result.get("event_log") or []:
            if isinstance(ev, dict) and ev.get("type") == "notify":
                stream.append_event(ev)
        if result.get("reject_reason"):
            stream.write(f"[red]Rejected:[/] {result['reject_reason']}")
        if result.get("log_path"):
            stream.write(f"[dim]log[/]: {result['log_path']}")

        interrupt = result.get("interrupt")
        mission = self.memory.mission
        if interrupt == "solidify" and mission is not None:
            self.push_screen(SolidifyModal(mission), self._on_solidify_result)
        else:
            stream.write("[dim]session[/]: ended")
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
                "[dim]Skipped solidify. Type /solidify later if needed.[/]"
            )
        self._end_running_ui()

    def _end_running_ui(self) -> None:
        self._session_active = False
        self._current_draft = None
        self._cancel_arm.clear()
        self._pending_review = None
        self._show_idle_sidebar()


def main() -> None:
    MaintainAllApp().run()


if __name__ == "__main__":
    main()
