"""Center stream/input and right sidebar panes for layout C."""

from __future__ import annotations

from time import monotonic
from typing import Any, Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.suggester import Suggester
from textual.widgets import Input, Label, ListItem, ListView, OptionList, Static
from textual.widgets.option_list import Option

from MaintainAll.missions.models import Mission, TaskNode
from MaintainAll.missions.resolve import (
    format_mission_candidate,
    is_run_command_prefix,
    parse_run_command,
    resolve_mission,
)
from MaintainAll.skills.models import SkillMeta


class ThinkingBodyScroll(VerticalScroll):
    """Fixed-height scroll area for thinking text; stick-to-bottom via anchor."""

    def on_mount(self) -> None:
        self.anchor(True)


class ThinkingBlock(Vertical):
    """Lighter box for streamed model thinking; collapses when done; click header to expand.

    Body is a fixed-height ``VerticalScroll`` + ``Static`` so soft-wrap uses the full
    panel width. (RichLog.write per token starts a new line — looks like narrow wrap.)
    """

    DEFAULT_CSS = """
    ThinkingBlock {
        background: $boost;
        border: solid $panel;
        margin: 0 0 1 0;
        height: auto;
        width: 100%;
    }
    ThinkingBlock.-collapsed .thinking-body {
        display: none;
    }
    ThinkingBlock .thinking-header {
        height: 1;
        padding: 0 1;
        text-style: italic;
        color: $text-muted;
    }
    ThinkingBlock .thinking-body {
        /* Fixed height → inner vertical scrollbar, no parent reflow per token. */
        height: 16;
        max-height: 16;
        width: 100%;
        padding: 0 1 1 1;
        overflow-y: auto;
        overflow-x: hidden;
        color: $text-muted;
        background: transparent;
        border: none;
        scrollbar-size-vertical: 1;
    }
    ThinkingBlock .thinking-body-text {
        width: 100%;
        height: auto;
        color: $text-muted;
    }
    """

    _FLUSH_INTERVAL = 0.08

    def __init__(self, phase: str, block_id: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._phase = phase or "?"
        self._block_id = block_id
        self._finished = False
        self._expanded = True
        self._body_text = ""
        self._dirty = False
        self._flush_scheduled = False

    def compose(self) -> ComposeResult:
        yield Static(self._header_text(), classes="thinking-header")
        yield ThinkingBodyScroll(
            Static("", classes="thinking-body-text", markup=False),
            classes="thinking-body",
        )

    def _header_text(self) -> str:
        phase = self._phase
        if not self._finished:
            return f"▾ Thinking ({phase})…"
        if self._expanded:
            return f"▾ Thought ({phase}) — click to collapse"
        return f"▸ Thought ({phase}) — click to expand"

    def _refresh_header(self) -> None:
        try:
            self.query_one(".thinking-header", Static).update(self._header_text())
        except Exception:
            pass

    def _body_scroll(self) -> ThinkingBodyScroll | None:
        try:
            return self.query_one(".thinking-body", ThinkingBodyScroll)
        except Exception:
            return None

    def _body_static(self) -> Static | None:
        try:
            return self.query_one(".thinking-body-text", Static)
        except Exception:
            return None

    def _flush_body(self) -> None:
        self._flush_scheduled = False
        if not self._dirty:
            return
        self._dirty = False
        text_widget = self._body_static()
        scroll = self._body_scroll()
        if text_widget is None:
            return
        try:
            follow = True
            if scroll is not None:
                follow = scroll.is_vertical_scroll_end or (
                    scroll.is_anchored and not getattr(scroll, "_anchor_released", False)
                )
            # Full-buffer update: one continuous string → wrap at real widget width.
            text_widget.update(self._body_text)
            if scroll is not None and follow:
                scroll.scroll_end(animate=False)
        except Exception:
            pass

    def _schedule_flush(self) -> None:
        if self._flush_scheduled:
            return
        if not self.is_mounted:
            self._flush_body()
            return
        self._flush_scheduled = True
        try:
            self.set_timer(self._FLUSH_INTERVAL, self._flush_body)
        except Exception:
            self._flush_scheduled = False
            self._flush_body()

    def append_text(self, text: str) -> None:
        if not text:
            return
        self._body_text += text
        self._dirty = True
        self._schedule_flush()

    def finish(self) -> None:
        self._finished = True
        self._expanded = False
        self._flush_scheduled = False
        self._dirty = True
        self._flush_body()
        self.add_class("-collapsed")
        self._refresh_header()

    def on_click(self) -> None:
        if not self._finished:
            return
        self._expanded = not self._expanded
        if self._expanded:
            self.remove_class("-collapsed")
        else:
            self.add_class("-collapsed")
        self._refresh_header()


class ChatStream(VerticalScroll):
    """Thinking / assistant event stream with collapsible thinking blocks."""

    DEFAULT_CSS = """
    ChatStream {
        height: 1fr;
        border: solid $primary;
        margin: 0 1 0 0;
        padding: 0 1;
    }
    ChatStream .chat-line {
        height: auto;
        margin-bottom: 1;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._blocks: dict[str, ThinkingBlock] = {}
        self._active_id: str | None = None
        self._last_think_scroll = 0.0

    def on_mount(self) -> None:
        # Built-in stick-to-bottom; user scroll releases anchor (scrollbar stays intact).
        self.anchor(True)

    def _scroll_to_latest(self) -> None:
        # Do not call scroll_end while the user has released the anchor — Textual's
        # scroll_end() would re-engage anchoring and yank the view back down.
        if self.is_anchored and getattr(self, "_anchor_released", False):
            return
        try:
            self.scroll_end(animate=False)
        except Exception:
            pass

    def write(self, message: str, *, markup: bool = True) -> None:
        line = Static(message, markup=markup, classes="chat-line")
        self.mount(line)
        self._scroll_to_latest()

    def _get_or_create_block(self, block_id: str, phase: str) -> ThinkingBlock:
        block = self._blocks.get(block_id)
        if block is None:
            block = ThinkingBlock(phase=phase, block_id=block_id, classes="thinking-block")
            self.mount(block)
            self._blocks[block_id] = block
            self._scroll_to_latest()
        return block

    def _maybe_scroll_for_thinking(self, *, force: bool = False) -> None:
        # ``force`` only bypasses the throttle — never overrides user scroll-away.
        now = monotonic()
        if not force and (now - self._last_think_scroll) < 0.05:
            return
        self._last_think_scroll = now
        self._scroll_to_latest()

    def append_event(self, event: dict[str, Any]) -> None:
        etype = str(event.get("type") or "event")
        if etype == "thinking_start":
            block_id = str(event.get("id") or "")
            phase = str(event.get("phase") or "")
            self._active_id = block_id
            self._get_or_create_block(block_id, phase)
            return
        if etype == "thinking_delta":
            block_id = str(event.get("id") or self._active_id or "")
            text = str(event.get("text") or "")
            block = self._blocks.get(block_id)
            if block is not None:
                block.append_text(text)
                self._maybe_scroll_for_thinking()
            elif text:
                phase = event.get("phase")
                if phase:
                    self.write(f"[dim]thinking[/] ({phase}): {text}")
                else:
                    self.write(f"[dim]thinking[/]: {text}")
            return
        if etype == "thinking_end":
            block_id = str(event.get("id") or self._active_id or "")
            block = self._blocks.get(block_id)
            if block is not None:
                block.finish()
            self._active_id = None
            self._maybe_scroll_for_thinking(force=True)
            return

        if etype == "assess":
            feasible = event.get("feasible")
            reason = event.get("reason") or ""
            mark = "ok" if feasible else "no"
            self.write(f"[bold cyan]assess[/] ({mark}): {reason}")
        elif etype == "board":
            mid = event.get("mission_id") or "?"
            n = event.get("task_count", "?")
            self.write(f"[bold magenta]board[/]: mission={mid} tasks={n}")
        elif etype == "board_warning":
            self.write(f"[yellow]board_warning[/]: {event.get('message','')}")
        elif etype == "review":
            if event.get("waiting"):
                self.write("[bold yellow]review[/]: waiting for approval…")
            elif event.get("auto"):
                self.write("[bold yellow]review[/]: auto-approved")
            else:
                self.write(f"[bold yellow]review[/]: {event.get('action')}")
        elif etype == "task_status":
            tid = event.get("id") or ""
            status = event.get("status") or ""
            if tid:
                self.write(f"[blue]task[/] {tid}: {status}")
            else:
                self.write(f"[blue]task[/]: {status}")
        elif etype == "cmd_count":
            pattern = event.get("pattern") or "*"
            count = event.get("count", 0)
            self.write(f"[dim]cmd[/] {pattern} ×{count}")
        elif etype == "cmd_skipped":
            reason = event.get("reason") or "skipped"
            cmd = event.get("cmd") or ""
            self.write(f"[yellow]cmd_skipped[/] ({reason}): {cmd}")
        elif etype == "react":
            bits = []
            if event.get("done"):
                bits.append("done")
            if event.get("rebuild"):
                bits.append("rebuild")
            self.write(f"[green]react[/]: {', '.join(bits) or 'step'}")
        elif etype == "react_nudge":
            missing = event.get("missing_sections") or []
            if missing:
                heads = ", ".join(f"## {n}" for n in missing)
                self.write(f"[yellow]react_nudge[/]: need OBSERVE {heads}")
            else:
                self.write("[yellow]react_nudge[/]: continue")
        elif etype == "validate":
            ok = event.get("ok")
            errors = event.get("errors") or []
            if ok:
                self.write("[green]validate[/]: ok")
            elif errors:
                self.write(f"[red]validate[/]: failed — {'; '.join(str(e) for e in errors)}")
            else:
                self.write("[red]validate[/]: failed")
        elif etype in ("revise_mission", "revise"):
            action = event.get("action") or "?"
            detail = event.get("feedback") or event.get("reason") or ""
            if detail:
                self.write(f"[bold orange1]revise[/]: {action} — {detail}")
            else:
                self.write(f"[bold orange1]revise[/]: {action}")
        elif etype == "finalize":
            self.write(f"[bold green]finalize[/]: {event.get('report_path', '')}")
        elif etype == "notify":
            ok = event.get("ok", True)
            ch = event.get("channel", "?")
            err = event.get("error")
            if ok and ch not in (None, "none", "skipped"):
                self.write(f"[bold green]notify[/]: sent via {ch}")
            elif ch == "skipped" or ch in (None, ""):
                detail = f" — {err}" if err else ""
                self.write(f"[yellow]notify[/]: skipped{detail}")
            else:
                self.write(f"[bold red]notify[/]: {err or ch}")
        elif etype == "reject":
            self.write(f"[bold red]reject[/]: {event.get('reason', '')}")
        elif etype == "session_cancelled":
            self.write("[yellow]session[/]: cancel acknowledged")
        elif etype in ("thinking", "token"):
            text = (
                event.get("message")
                or event.get("text")
                or event.get("content")
                or ""
            )
            phase = event.get("phase")
            if self._active_id and self._active_id in self._blocks:
                if text:
                    self._blocks[self._active_id].append_text(text)
                    self._maybe_scroll_for_thinking()
            elif phase and text:
                self.write(f"[dim]thinking[/] ({phase}): {text}")
            elif text:
                self.write(f"[dim]thinking[/]: {text}")
            elif phase:
                self.write(f"[dim]thinking[/]: {phase}…")
        else:
            self.write(f"[dim]{etype}[/]: {event}")


class PromptHistory:
    """Shell-like prompt recall (newest at the end)."""

    def __init__(
        self,
        *,
        max_size: int = 100,
        on_push: Callable[[str], None] | None = None,
    ) -> None:
        self.entries: list[str] = []
        self.index: int | None = None
        self.draft: str = ""
        self.max_size = max(1, max_size)
        self._on_push = on_push

    def load(self, entries: list[str]) -> None:
        self.entries = [e for e in entries if (e or "").strip()][-self.max_size :]
        self.index = None
        self.draft = ""

    def push(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        if not self.entries or self.entries[-1] != text:
            self.entries.append(text)
            if len(self.entries) > self.max_size:
                self.entries = self.entries[-self.max_size :]
            if self._on_push is not None:
                self._on_push(text)
        self.index = None
        self.draft = ""

    def older(self, current: str) -> str | None:
        """Move toward older entries. Returns new value, or None if unchanged."""
        if not self.entries:
            return None
        if self.index is None:
            self.draft = current
            self.index = len(self.entries) - 1
            return self.entries[self.index]
        if self.index <= 0:
            return None
        self.index -= 1
        return self.entries[self.index]

    def newer(self, current: str) -> str | None:
        """Move toward newer entries / restore draft. Returns new value, or None."""
        if self.index is None:
            return None
        if self.index < len(self.entries) - 1:
            self.index += 1
            return self.entries[self.index]
        self.index = None
        return self.draft


class CompletionItem:
    """One completion candidate: display label + value inserted into the input."""

    __slots__ = ("label", "value")

    def __init__(self, label: str, value: str) -> None:
        self.label = label
        self.value = value


def run_completion_items(
    query: str,
    missions: list[Mission],
) -> list[CompletionItem]:
    """Build ``/run`` completion items for an empty or partial query."""
    if not query:
        pool = list(missions)
    else:
        match, cands = resolve_mission(query, missions)
        if match is not None:
            pool = [match]
        else:
            pool = list(cands)
    return [
        CompletionItem(format_mission_candidate(m), f"/run {m.id}")
        for m in sorted(pool, key=lambda m: m.id.casefold())
    ]


class CompletionPopup(Vertical):
    """Floating candidate list shown just above the chat input."""

    can_focus = False

    DEFAULT_CSS = """
    CompletionPopup {
        display: none;
        height: auto;
        max-height: 10;
        border: solid $accent;
        background: $surface;
        padding: 0 0;
        margin: 0 1 0 0;
        layer: overlay;
    }
    CompletionPopup.-open {
        display: block;
    }
    CompletionPopup OptionList {
        height: auto;
        max-height: 9;
        background: $surface;
        border: none;
        padding: 0;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._items: list[CompletionItem] = []

    def compose(self) -> ComposeResult:
        options = OptionList(id="completion-options")
        options.can_focus = False
        yield options

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        try:
            chat = self.screen.query_one("#chat-input", ChatInput)
        except Exception:
            self.close()
            return
        chat._accept_completion()

    @property
    def is_open(self) -> bool:
        return self.has_class("-open")

    def open_items(self, items: list[CompletionItem], *, cursor_col: int = 0) -> None:
        self._items = list(items)
        options = self.query_one("#completion-options", OptionList)
        options.clear_options()
        for idx, item in enumerate(self._items):
            options.add_option(Option(item.label, id=f"c{idx}"))
        if self._items:
            options.highlighted = 0
        # Approximate alignment under the caret (cell ≈ column).
        left = max(0, min(int(cursor_col), 48))
        self.styles.margin = (0, 1, 0, left)
        self.add_class("-open")
        self.display = True

    def close(self) -> None:
        self._items = []
        try:
            self.query_one("#completion-options", OptionList).clear_options()
        except Exception:
            pass
        self.remove_class("-open")
        self.display = False
        self.styles.margin = (0, 1, 0, 0)

    def move(self, delta: int) -> None:
        if not self._items:
            return
        options = self.query_one("#completion-options", OptionList)
        cur = options.highlighted
        if cur is None:
            cur = 0
        options.highlighted = (cur + delta) % len(self._items)

    def selected(self) -> CompletionItem | None:
        if not self._items:
            return None
        options = self.query_one("#completion-options", OptionList)
        idx = options.highlighted
        if idx is None or idx < 0 or idx >= len(self._items):
            return self._items[0]
        return self._items[idx]


class ChatSlashSuggester(Suggester):
    """Inline grey suggestions for slash commands (not the candidate popup)."""

    def __init__(
        self,
        get_options: Callable[[], list[str]],
        get_missions: Callable[[], list[Mission]] | None = None,
    ) -> None:
        super().__init__(use_cache=False, case_sensitive=False)
        self._get_options = get_options
        self._get_missions = get_missions

    async def get_suggestion(self, value: str) -> str | None:
        if not value:
            return None
        # Do not grey-suggest a specific mission id — popup handles that.
        if value.startswith("/run"):
            if value in {"/r", "/ru", "/run"} or value == "/run":
                return "/run " if value != "/run " else None
            # "/run " with trailing space: no inline suggestion
            if value.startswith("/run "):
                return None
            if "/run ".startswith(value):
                return "/run "
            return None
        for option in self._get_options():
            folded = option.casefold()
            if folded.startswith(value) and folded != value:
                return option
        return None


def slash_completion_options(missions: list[Mission]) -> list[str]:
    """Ordered completion strings for non-popup slash suggestions."""
    from MaintainAll.tui.slash import completion_strings

    # missions unused — kept for call-site compatibility; /run popup uses get_missions.
    _ = missions
    return completion_strings()


class ChatInput(Input):
    """User prompt bar with history + slash completion popup."""

    BINDINGS = [
        Binding("up", "history_older", "History older", show=False),
        Binding("down", "history_newer", "History newer", show=False),
        Binding("tab", "tab_complete", "Complete", show=False),
        Binding("escape", "completion_dismiss", "Dismiss completion", show=False),
    ]

    def __init__(
        self,
        *,
        get_slash_options: Callable[[], list[str]] | None = None,
        get_missions: Callable[[], list[Mission]] | None = None,
        **kwargs: Any,
    ) -> None:
        suggester = None
        if get_slash_options is not None:
            suggester = ChatSlashSuggester(get_slash_options, get_missions=get_missions)
        super().__init__(
            placeholder="Ask the AIOps agent…  (/run <id|name>, Tab for candidates)",
            id="chat-input",
            suggester=suggester,
            **kwargs,
        )
        self._prompt_history = PromptHistory()
        self._get_slash_options = get_slash_options
        self._get_missions = get_missions

    def set_slash_providers(
        self,
        get_slash_options: Callable[[], list[str]],
        get_missions: Callable[[], list[Mission]] | None = None,
    ) -> None:
        self._get_slash_options = get_slash_options
        self._get_missions = get_missions
        self.suggester = ChatSlashSuggester(get_slash_options, get_missions=get_missions)

    def bind_history(
        self,
        entries: list[str],
        *,
        on_push: Callable[[str], None] | None = None,
        max_size: int = 100,
    ) -> None:
        self._prompt_history = PromptHistory(max_size=max_size, on_push=on_push)
        self._prompt_history.load(entries)

    def push_history(self, text: str) -> None:
        self._prompt_history.push(text)

    def _popup(self) -> CompletionPopup | None:
        try:
            return self.screen.query_one("#completion-popup", CompletionPopup)
        except Exception:
            return None

    def _popup_open(self) -> bool:
        popup = self._popup()
        return bool(popup is not None and popup.is_open)

    def _close_popup(self) -> None:
        popup = self._popup()
        if popup is not None:
            popup.close()

    def _accept_completion(self) -> bool:
        popup = self._popup()
        if popup is None or not popup.is_open:
            return False
        item = popup.selected()
        popup.close()
        if item is None:
            return False
        self.value = item.value
        self.cursor_position = len(self.value)
        return True

    def _show_run_candidates(self, query: str) -> None:
        missions = self._get_missions() if self._get_missions is not None else []
        popup = self._popup()
        if popup is None:
            return
        if query:
            match, cands = resolve_mission(query, missions)
            if match is not None:
                popup.close()
                self.value = f"/run {match.id}"
                self.cursor_position = len(self.value)
                return
            items = [
                CompletionItem(format_mission_candidate(m), f"/run {m.id}")
                for m in sorted(cands, key=lambda m: m.id.casefold())
            ]
        else:
            items = run_completion_items("", missions)
        if not items:
            popup.close()
            return
        popup.open_items(items, cursor_col=self.cursor_position)

    def action_history_older(self) -> None:
        if self._popup_open():
            popup = self._popup()
            if popup is not None:
                popup.move(-1)
            return
        if self.cursor_position != 0:
            return
        nxt = self._prompt_history.older(self.value)
        if nxt is None:
            return
        self.value = nxt
        self.cursor_position = 0

    def action_history_newer(self) -> None:
        if self._popup_open():
            popup = self._popup()
            if popup is not None:
                popup.move(1)
            return
        if self.cursor_position != 0:
            return
        nxt = self._prompt_history.newer(self.value)
        if nxt is None:
            return
        self.value = nxt
        self.cursor_position = 0

    def action_tab_complete(self) -> None:
        if self._popup_open():
            self._accept_completion()
            return
        raw = self.value
        stripped = raw.strip()
        if is_run_command_prefix(stripped):
            query = parse_run_command(stripped)
            if query is None:
                self.value = "/run "
                self.cursor_position = len(self.value)
                self._show_run_candidates("")
                return
            if not stripped.endswith(" ") and stripped.casefold() in {"/run"}:
                self.value = "/run "
                self.cursor_position = len(self.value)
            self._show_run_candidates(query or "")
            return
        # Non-/run: accept grey suggestion if present
        self.action_cursor_right()

    def action_completion_dismiss(self) -> None:
        if self._popup_open():
            self._close_popup()
            return
        # Bubble: let app handle escape (close modal) if any
        self.app.action_close_modal()

    async def action_submit(self) -> None:
        if self._popup_open():
            self._accept_completion()
            return
        await super().action_submit()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input is not self:
            return
        if not self._popup_open():
            return
        stripped = self.value.strip()
        if not is_run_command_prefix(stripped):
            self._close_popup()
            return
        query = parse_run_command(stripped)
        if query is None:
            self._close_popup()
            return
        self._show_run_candidates(query)


class IdleSidebar(Vertical):
    """Missions then Skills lists (idle state)."""

    def __init__(
        self,
        missions: list[Mission] | None = None,
        skills: list[SkillMeta] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._missions = missions or []
        self._skills = skills or []

    def compose(self) -> ComposeResult:
        yield Label("Missions", classes="sidebar-heading")
        mission_items: list[ListItem] = []
        for m in self._missions:
            item = ListItem(Label(m.name or m.id))
            item.data = ("mission", m)  # type: ignore[attr-defined]
            mission_items.append(item)
        if not mission_items:
            empty = ListItem(Label("(none)"))
            empty.data = None  # type: ignore[attr-defined]
            mission_items.append(empty)
        yield ListView(*mission_items, id="missions-list")

        yield Label("Skills", classes="sidebar-heading")
        skill_items: list[ListItem] = []
        for s in self._skills:
            item = ListItem(Label(s.name))
            item.data = ("skill", s)  # type: ignore[attr-defined]
            skill_items.append(item)
        if not skill_items:
            empty = ListItem(Label("(none)"))
            empty.data = None  # type: ignore[attr-defined]
            skill_items.append(empty)
        yield ListView(*skill_items, id="skills-list")

    def set_data(self, missions: list[Mission], skills: list[SkillMeta]) -> None:
        self._missions = missions
        self._skills = skills


class RunStatePane(VerticalScroll):
    """Live run state: description, allowed cmds ×N, task board."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._description = ""
        self._cmd_counts: dict[str, int] = {}
        self._allowed: list[str] = []
        self._tasks: list[tuple[str, str, str, int]] = []  # id, name, status, depth

    def compose(self) -> ComposeResult:
        yield Label("Running", classes="sidebar-heading")
        yield Static("(starting…)", id="run-desc")
        yield Label("Allowed commands", classes="sidebar-heading")
        yield Static("(none yet)", id="run-cmds")
        yield Label("Task board", classes="sidebar-heading")
        yield Static("(no tasks)", id="run-tasks")

    def load_mission(self, mission: Mission | dict[str, Any] | None) -> None:
        if mission is None:
            return
        if isinstance(mission, Mission):
            self._description = mission.description or mission.name or mission.id
            self._allowed = [c.pattern for c in mission.allowed_commands]
            for p in self._allowed:
                self._cmd_counts.setdefault(p, 0)
            self._tasks = list(self._walk_tasks(mission.tasks, 0))
        else:
            self._description = str(
                mission.get("description") or mission.get("name") or mission.get("id") or ""
            )
            cmds = mission.get("allowed_commands") or []
            self._allowed = []
            for c in cmds:
                if isinstance(c, dict):
                    pat = str(c.get("pattern") or "")
                else:
                    pat = str(getattr(c, "pattern", c))
                if pat:
                    self._allowed.append(pat)
                    self._cmd_counts.setdefault(pat, 0)
            self._tasks = list(self._walk_tasks_dict(mission.get("tasks") or [], 0))
        self.refresh_view()

    @staticmethod
    def _walk_tasks(tasks: list[TaskNode], depth: int) -> list[tuple[str, str, str, int]]:
        out: list[tuple[str, str, str, int]] = []
        for t in tasks:
            out.append((t.id, t.name, t.status, depth))
            if t.tasks:
                out.extend(RunStatePane._walk_tasks(t.tasks, depth + 1))
        return out

    @staticmethod
    def _walk_tasks_dict(tasks: list[dict], depth: int) -> list[tuple[str, str, str, int]]:
        out: list[tuple[str, str, str, int]] = []
        for t in tasks:
            tid = str(t.get("id") or "")
            name = str(t.get("name") or tid)
            status = str(t.get("status") or "pending")
            out.append((tid, name, status, depth))
            children = t.get("tasks") or []
            if children:
                out.extend(RunStatePane._walk_tasks_dict(children, depth + 1))
        return out

    def update_task_status(self, task_id: str | None, status: str) -> None:
        if not task_id:
            if status == "blocked":
                self._tasks = [
                    (tid, name, "blocked" if st == "pending" else st, d)
                    for tid, name, st, d in self._tasks
                ]
            self.refresh_view()
            return
        updated: list[tuple[str, str, str, int]] = []
        for tid, name, st, d in self._tasks:
            if tid == task_id:
                updated.append((tid, name, status, d))
            else:
                updated.append((tid, name, st, d))
        self._tasks = updated
        self.refresh_view()

    def update_cmd_count(self, pattern: str, count: int) -> None:
        self._cmd_counts[pattern] = count
        if pattern not in self._allowed:
            self._allowed.append(pattern)
        self.refresh_view()

    def set_cmd_counts(self, counts: dict[str, int]) -> None:
        self._cmd_counts.update(counts)
        self.refresh_view()

    def refresh_view(self) -> None:
        try:
            self.query_one("#run-desc", Static).update(self._description or "(no description)")
            if self._allowed:
                lines = [
                    f"{p} ×{self._cmd_counts.get(p, 0)}" for p in self._allowed
                ]
                self.query_one("#run-cmds", Static).update("\n".join(lines))
            else:
                self.query_one("#run-cmds", Static).update("(none yet)")
            if self._tasks:
                lines = [
                    f"{'  ' * d}[{st}] {name} ({tid})"
                    for tid, name, st, d in self._tasks
                ]
                self.query_one("#run-tasks", Static).update("\n".join(lines))
            else:
                self.query_one("#run-tasks", Static).update("(no tasks)")
        except Exception:
            pass
