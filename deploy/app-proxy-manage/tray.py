"""MaintainAll 分应用白名单托盘（Windows）。

  python tray.py              # 托盘 + 勾选窗口
  python tray.py --scan       # 打印检测到的应用
  python tray.py --apply a.exe,b.exe
  python tray.py --reload
  python tray.py --ping

Linux / macOS: unimplemented.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

UNIMPL = "unimplemented: 分应用托盘目前只支持 Windows（linux / macos 未实现）"


def _die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def ensure_gui_deps() -> None:
    try:
        import PIL  # noqa: F401
        import pystray  # noqa: F401
        import yaml  # noqa: F401
    except ImportError:
        req = ROOT / "requirements.txt"
        print(f"安装依赖: {sys.executable} -m pip install -r {req}")
        import subprocess

        r = subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(req)], check=False)
        if r.returncode != 0:
            _die("无法安装 pystray / Pillow / PyYAML")


def _selected_from_state() -> set[str]:
    from install import load_state
    from profile_rules import unique_exes

    st = load_state()
    return {p.lower() for p in unique_exes(st.processes)}


def cmd_scan() -> int:
    from win_apps import scan_apps, scan_running

    apps = scan_apps()
    running = scan_running()
    print(f"应用（开始菜单 + 有窗口进程）: {len(apps)}")
    for a in apps[:80]:
        flag = "" if a.supported else f"  [{a.note or '不支持'}]"
        print(f"  {a.name}  ({a.exe or '-'})  {a.source}{flag}")
    if len(apps) > 80:
        print(f"  ... 还有 {len(apps) - 80} 个")
    print(f"正在运行（含无窗口）: {len(running)}")
    for a in running[:40]:
        print(f"  {a.name}  ({a.exe})  {a.source}")
    return 0


def cmd_apply(raw: str) -> int:
    from verge_ctl import apply_processes, reload_verge

    names = [p.strip() for p in raw.replace("，", ",").split(",") if p.strip()]
    dest, rt = apply_processes(names)
    print(f"已写入 {dest}")
    if rt:
        print(f"已同步运行时 {rt}")
    print(reload_verge())
    return 0


def cmd_reload() -> int:
    from verge_ctl import reload_verge

    print(reload_verge())
    return 0


def cmd_ping() -> int:
    from verge_ctl import ping_verge

    print(ping_verge())
    return 0


def _make_icon():
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, 62, 62), fill=(37, 99, 235, 255))
    d.polygon([(18, 20), (46, 32), (18, 44)], fill=(255, 255, 255, 255))
    return img


def _open_picker(root) -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk

    from verge_ctl import apply_processes, reload_verge
    from win_apps import AppEntry, scan_apps, scan_running

    win = tk.Toplevel(root)
    win.title("MaintainAll 分应用白名单")
    win.geometry("560x640")
    win.minsize(420, 360)

    status = tk.StringVar(value="扫描中…")
    query = tk.StringVar()
    tab = tk.StringVar(value="apps")
    sel_filter = tk.StringVar(value="all")
    selected: set[str] = _selected_from_state()
    apps: list[AppEntry] = []
    running: list[AppEntry] = []
    vars_by_key: dict[str, tk.BooleanVar] = {}

    top = ttk.Frame(win, padding=8)
    top.pack(fill="x")
    ttk.Label(top, text="搜索").pack(side="left")
    search = ttk.Entry(top, textvariable=query)
    search.pack(side="left", fill="x", expand=True, padx=8)

    btns = ttk.Frame(win, padding=(8, 0))
    btns.pack(fill="x")
    ttk.Radiobutton(btns, text="应用", variable=tab, value="apps").pack(side="left")
    ttk.Radiobutton(btns, text="正在运行", variable=tab, value="running").pack(side="left", padx=(8, 0))
    ttk.Separator(btns, orient="vertical").pack(side="left", fill="y", padx=10, pady=2)
    ttk.Radiobutton(btns, text="全部", variable=sel_filter, value="all").pack(side="left")
    ttk.Radiobutton(btns, text="已勾选", variable=sel_filter, value="checked").pack(side="left", padx=(8, 0))
    ttk.Radiobutton(btns, text="未勾选", variable=sel_filter, value="unchecked").pack(side="left", padx=(8, 0))

    canvas_frame = ttk.Frame(win, padding=8)
    canvas_frame.pack(fill="both", expand=True)
    canvas = tk.Canvas(canvas_frame, highlightthickness=0)
    vsb = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
    inner = ttk.Frame(canvas)
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=vsb.set)
    canvas.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")

    def _on_mousewheel(event):
        canvas.yview_scroll(int(-event.delta / 120), "units")

    canvas.bind("<MouseWheel>", _on_mousewheel)
    inner.bind("<MouseWheel>", _on_mousewheel)

    foot = ttk.Frame(win, padding=8)
    foot.pack(fill="x")
    ttk.Label(foot, textvariable=status, wraplength=520).pack(fill="x", pady=(0, 6))

    action = ttk.Frame(foot)
    action.pack(fill="x")

    def current_list() -> list[AppEntry]:
        return running if tab.get() == "running" else apps

    def rows_for_display() -> list[AppEntry]:
        rows = list(current_list())
        have = {e.key for e in rows if e.supported and e.exe}
        ghosts: list[AppEntry] = []
        for key in selected:
            if key in have:
                continue
            ghosts.append(
                AppEntry(exe=key, name=key, path="", source="saved", supported=True)
            )
        rows = ghosts + rows

        def sort_key(e: AppEntry) -> tuple:
            checked = bool(e.supported and e.exe and e.key in selected)
            if checked:
                group = 0
            elif e.supported:
                group = 1
            else:
                group = 2
            return (group, e.name.lower(), e.exe.lower())

        rows.sort(key=sort_key)
        q = query.get().strip().lower()
        filt = sel_filter.get()
        out: list[AppEntry] = []
        for e in rows:
            hay = f"{e.name} {e.exe} {e.path}".lower()
            if q and q not in hay:
                continue
            checked = bool(e.supported and e.exe and e.key in selected)
            if filt == "checked" and not checked:
                continue
            if filt == "unchecked" and (checked or not e.supported):
                continue
            out.append(e)
        return out

    def rebuild(*_a) -> None:
        for child in inner.winfo_children():
            child.destroy()
        rows = rows_for_display()
        shown = 0
        last_group = None
        for e in rows:
            checked = bool(e.supported and e.exe and e.key in selected)
            group = 0 if checked else (1 if e.supported else 2)
            if group != last_group:
                last_group = group
                title = {0: "已勾选（走代理）", 1: "未勾选（直连）", 2: "无法分流"}[group]
                ttk.Label(inner, text=title, font=("", 9, "bold")).pack(anchor="w", pady=(8 if shown else 0, 2))
            if not e.supported:
                ttk.Label(inner, text=f"○ {e.name}  — {e.note}", foreground="#888").pack(anchor="w")
                shown += 1
                continue
            key = e.key
            if key not in vars_by_key:
                vars_by_key[key] = tk.BooleanVar(value=key in selected)
            else:
                vars_by_key[key].set(key in selected)

            def _toggle(k=key, var=vars_by_key[key]) -> None:
                if var.get():
                    selected.add(k)
                else:
                    selected.discard(k)
                win.after_idle(rebuild)

            cb = ttk.Checkbutton(
                inner,
                text=f"{e.name}  ({e.exe})",
                variable=vars_by_key[key],
                command=_toggle,
            )
            cb.pack(anchor="w")
            shown += 1
            if shown >= 400:
                ttk.Label(inner, text="列表已截断，请用搜索缩小范围。").pack(anchor="w")
                break
        status.set(f"显示 {shown} 项，已勾选 {len(selected)} 个进程")

    def refresh_scan() -> None:
        status.set("正在扫描开始菜单和进程…")
        win.update_idletasks()

        def work():
            nonlocal apps, running
            try:
                a = scan_apps()
                r = scan_running()
            except Exception as ex:  # noqa: BLE001
                win.after(0, lambda: status.set(f"扫描失败: {ex}"))
                return

            def done():
                nonlocal apps, running
                apps, running = a, r
                rebuild()

            win.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def do_apply(also_reload: bool) -> None:
        names = sorted(selected)
        if not names:
            if not messagebox.askyesno("确认", "未勾选任何应用，将全部直连。继续？"):
                return
        try:
            dest, rt = apply_processes(names)
            msg = f"已写入 {dest.name}"
            if rt:
                msg += f"，并同步 {rt.name}"
            if also_reload:
                msg += "\n" + reload_verge()
            status.set(msg.replace("\n", " · "))
            messagebox.showinfo("完成", msg)
        except Exception as ex:  # noqa: BLE001
            status.set(str(ex))
            messagebox.showerror("失败", str(ex))

    ttk.Button(btns, text="刷新列表", command=refresh_scan).pack(side="right")
    ttk.Button(action, text="应用到 Verge 并重载", command=lambda: do_apply(True)).pack(side="left")
    ttk.Button(action, text="仅写入", command=lambda: do_apply(False)).pack(side="left", padx=8)
    ttk.Button(action, text="只重载 Verge", command=lambda: do_apply_reload_only()).pack(side="left")

    def do_apply_reload_only() -> None:
        try:
            from verge_ctl import reload_verge as _rl

            status.set(_rl())
        except Exception as ex:  # noqa: BLE001
            messagebox.showerror("重载失败", str(ex))

    query.trace_add("write", rebuild)
    tab.trace_add("write", rebuild)
    sel_filter.trace_add("write", rebuild)
    def _on_close() -> None:
        try:
            canvas.unbind("<MouseWheel>")
            inner.unbind("<MouseWheel>")
        except tk.TclError:
            pass
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", _on_close)
    refresh_scan()


def run_tray(*, silent: bool = False) -> int:
    ensure_gui_deps()
    import tkinter as tk

    import pystray
    from pystray import MenuItem as Item

    root = tk.Tk()
    root.withdraw()
    root.title("MaintainAll 分应用代理")
    picker_lock = threading.Lock()

    def show_picker(icon=None, item=None) -> None:
        def _go():
            with picker_lock:
                _open_picker(root)

        root.after(0, _go)

    def do_reload(icon=None, item=None) -> None:
        def _go():
            from tkinter import messagebox

            try:
                from verge_ctl import reload_verge

                messagebox.showinfo("Clash Verge", reload_verge())
            except Exception as ex:  # noqa: BLE001
                messagebox.showerror("重载失败", str(ex))

        root.after(0, _go)

    def quit_app(icon, item) -> None:
        icon.stop()
        root.after(0, root.destroy)

    icon = pystray.Icon(
        "maintainall-app-proxy",
        _make_icon(),
        "MaintainAll 分应用代理",
        menu=pystray.Menu(
            Item("应用白名单…", show_picker, default=True),
            Item("刷新 Clash Verge", do_reload),
            Item("退出", quit_app),
        ),
    )
    threading.Thread(target=icon.run, daemon=True).start()
    if not silent:
        show_picker()
    root.mainloop()
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MaintainAll 分应用白名单托盘（Windows）")
    p.add_argument("--scan", action="store_true", help="扫描应用/进程并打印")
    p.add_argument("--apply", default="", help="逗号分隔 exe，写入 profile 并重载")
    p.add_argument("--reload", action="store_true", help="只重载 Clash Verge")
    p.add_argument("--ping", action="store_true", help="探测 mihomo 控制器")
    p.add_argument("--silent", action="store_true", help="只挂托盘，不弹出勾选窗口（开机启动用）")
    return p.parse_args()


def main() -> None:
    if os.name != "nt":
        _die(UNIMPL, 2)
    args = parse_args()
    if args.scan:
        raise SystemExit(cmd_scan())
    if args.ping:
        raise SystemExit(cmd_ping())
    if args.reload:
        raise SystemExit(cmd_reload())
    if args.apply:
        raise SystemExit(cmd_apply(args.apply))
    raise SystemExit(run_tray(silent=args.silent))


if __name__ == "__main__":
    main()
