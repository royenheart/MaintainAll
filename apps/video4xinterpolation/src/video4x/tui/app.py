"""Simple Textual TUI for Video4x enhance jobs."""

from __future__ import annotations

import threading
from pathlib import Path

from video4x.inference.progress import ProgressEvent, format_progress_line
from video4x.job import EnhanceJob, EnhanceJobConfig, parse_order
from video4x.ops.base import OpSpec
from video4x.ops.superresolve.export import default_onnx_root
from video4x.ops.superresolve.model import MODEL_PRESETS

try:
    from textual import on
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.widgets import (
        Button,
        Checkbox,
        Footer,
        Header,
        Input,
        Label,
        ProgressBar,
        RichLog,
        Select,
        Static,
    )
except ImportError as exc:  # pragma: no cover
    raise ImportError("Install textual: pip install 'video4x[tui]' or pip install textual") from exc


class Video4xApp(App[None]):
    """Single-screen enhance form."""

    CSS = """
    Screen { layout: vertical; }
    #form { height: auto; padding: 1; }
    #row { height: auto; }
    Input { width: 1fr; }
    #log { height: 1fr; border: solid $accent; }
    #status { height: 3; }
    ProgressBar { width: 1fr; }
    """

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+r", "run", "Run"),
    ]

    TITLE = "Video4x"
    SUB_TITLE = "Super-resolve + Interpolate (AMD GPU+NPU)"

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="form"):
            yield Label("Input video (paste path)")
            yield Input(placeholder="D:\\videos\\in.mp4", id="input")
            yield Label("Output")
            yield Input(placeholder="D:\\videos\\out.mp4", id="output")
            with Horizontal(id="row"):
                yield Checkbox("Interpolate (RIFE)", value=True, id="op_fi")
                yield Checkbox("Super-resolve (Real-ESRGAN)", value=False, id="op_sr")
            yield Label("Order (when both enabled)")
            yield Select(
                [
                    ("Interpolate → Super-resolve", "interpolate,superresolve"),
                    ("Super-resolve → Interpolate", "superresolve,interpolate"),
                ],
                value="interpolate,superresolve",
                id="order",
            )
            with Horizontal(id="row"):
                yield Label("SR model")
                yield Select(
                    [(k, k) for k in MODEL_PRESETS],
                    value="x4plus",
                    id="sr_model",
                )
                yield Label("SR backend")
                yield Select(
                    [("split-pipeline", "split-pipeline"), ("single-ep", "single-ep")],
                    value="split-pipeline",
                    id="sr_backend",
                )
            with Horizontal(id="row"):
                yield Label("FI backend")
                yield Select(
                    [
                        ("split-pipeline", "split-pipeline"),
                        ("single-ep", "single-ep"),
                        ("cpu-baseline", "cpu-baseline"),
                    ],
                    value="split-pipeline",
                    id="fi_backend",
                )
                yield Label("Platform")
                yield Select(
                    [("auto", "auto"), ("windows", "windows"), ("wsl", "wsl"), ("linux", "linux")],
                    value="auto",
                    id="platform",
                )
            with Horizontal(id="row"):
                yield Button("Start", variant="success", id="btn_run")
                yield Button("Cancel", variant="error", id="btn_cancel", disabled=True)
        with Vertical(id="status"):
            yield Static("Idle", id="status_line")
            yield ProgressBar(total=100, id="progress", show_eta=False)
        yield RichLog(id="log", highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self._cancel = threading.Event()
        self._running = False
        self._thread: threading.Thread | None = None
        self.query_one("#input", Input).focus()

    def action_run(self) -> None:
        self._start_job()

    @on(Button.Pressed, "#btn_run")
    def on_run_pressed(self) -> None:
        self._start_job()

    @on(Button.Pressed, "#btn_cancel")
    def on_cancel_pressed(self) -> None:
        self._cancel.set()
        self.query_one("#status_line", Static).update("Cancel requested…")

    def _start_job(self) -> None:
        if self._running:
            return
        inp = self.query_one("#input", Input).value.strip().strip('"')
        out = self.query_one("#output", Input).value.strip().strip('"')
        log = self.query_one("#log", RichLog)
        if not inp or not out:
            log.write("[red]Need input and output paths[/red]")
            return
        if not Path(inp).is_file():
            log.write(f"[red]Input not found: {inp}[/red]")
            return
        use_fi = self.query_one("#op_fi", Checkbox).value
        use_sr = self.query_one("#op_sr", Checkbox).value
        if not use_fi and not use_sr:
            log.write("[red]Select at least one feature[/red]")
            return
        ops: list[str] = []
        if use_fi:
            ops.append("interpolate")
        if use_sr:
            ops.append("superresolve")
        order_val = self.query_one("#order", Select).value
        if isinstance(order_val, str) and use_fi and use_sr:
            order = parse_order(ops, order_val)
        else:
            order = ops

        cfg = EnhanceJobConfig(
            input_path=Path(inp),
            output_path=Path(out),
            order=order,
            interpolate=OpSpec(
                op="interpolate",
                backend=str(self.query_one("#fi_backend", Select).value),
                platform=str(self.query_one("#platform", Select).value),
            )
            if use_fi
            else None,
            superresolve=OpSpec(
                op="superresolve",
                model=str(self.query_one("#sr_model", Select).value),
                backend=str(self.query_one("#sr_backend", Select).value),
                platform=str(self.query_one("#platform", Select).value),
                onnx_dir=default_onnx_root(),
            )
            if use_sr
            else None,
        )
        self._cancel.clear()
        self._running = True
        self.query_one("#btn_run", Button).disabled = True
        self.query_one("#btn_cancel", Button).disabled = False
        log.write(f"[cyan]Starting[/cyan] order={order}")
        self._thread = threading.Thread(target=self._run_job, args=(cfg,), daemon=True)
        self._thread.start()

    def _run_job(self, cfg: EnhanceJobConfig) -> None:
        def on_progress(ev: ProgressEvent) -> None:
            if self._cancel.is_set():
                raise RuntimeError("cancelled")
            line = format_progress_line(ev)
            self.call_from_thread(self._ui_progress, line, ev.pct if ev.total else None)

        try:
            result = EnhanceJob(cfg, on_progress=on_progress).run()
            self.call_from_thread(self._ui_done, str(result.output_path), None)
        except Exception as exc:
            self.call_from_thread(self._ui_done, None, str(exc))

    def _ui_progress(self, line: str, pct: float | None) -> None:
        self.query_one("#log", RichLog).write(line)
        self.query_one("#status_line", Static).update(line[:120])
        if pct is not None:
            self.query_one("#progress", ProgressBar).update(progress=pct)

    def _ui_done(self, path: str | None, err: str | None) -> None:
        log = self.query_one("#log", RichLog)
        status = self.query_one("#status_line", Static)
        if err:
            log.write(f"[red]Error: {err}[/red]")
            status.update(f"Error: {err}")
        else:
            log.write(f"[green]Done[/green] {path}")
            status.update(f"Done → {path}")
        self._running = False
        self.query_one("#btn_run", Button).disabled = False
        self.query_one("#btn_cancel", Button).disabled = True


def run_tui() -> None:
    Video4xApp().run()


if __name__ == "__main__":
    run_tui()
