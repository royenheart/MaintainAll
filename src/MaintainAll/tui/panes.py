"""Center stream/input and right sidebar panes for layout C."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Input, Label, ListItem, ListView, RichLog, Static

from MaintainAll.missions.models import Mission, TaskNode
from MaintainAll.skills.models import SkillMeta


class ChatStream(RichLog):
    """Thinking / assistant event stream."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            highlight=True,
            markup=True,
            wrap=True,
            auto_scroll=True,
            **kwargs,
        )

    def append_event(self, event: dict[str, Any]) -> None:
        etype = str(event.get("type") or "event")
        if etype == "assess":
            feasible = event.get("feasible")
            reason = event.get("reason") or ""
            mark = "ok" if feasible else "no"
            self.write(f"[bold cyan]assess[/] ({mark}): {reason}")
        elif etype == "board":
            mid = event.get("mission_id") or "?"
            n = event.get("task_count", "?")
            self.write(f"[bold magenta]board[/]: mission={mid} tasks={n}")
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
        elif etype == "react":
            bits = []
            if event.get("done"):
                bits.append("done")
            if event.get("rebuild"):
                bits.append("rebuild")
            self.write(f"[green]react[/]: {', '.join(bits) or 'step'}")
        elif etype == "finalize":
            self.write(f"[bold green]finalize[/]: {event.get('report_path', '')}")
        elif etype == "reject":
            self.write(f"[bold red]reject[/]: {event.get('reason', '')}")
        elif etype in ("thinking", "token"):
            text = event.get("text") or event.get("content") or ""
            if text:
                self.write(str(text))
        else:
            self.write(f"[dim]{etype}[/]: {event}")


class ChatInput(Input):
    """User prompt bar."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            placeholder="Ask the AIOps agent…",
            id="chat-input",
            **kwargs,
        )


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
