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


def _checkbox_images(master, size: int = 28):
    from PIL import Image, ImageDraw, ImageTk

    def draw(checked: bool):
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        pad = max(1, size // 16)
        box = (pad, pad, size - pad - 1, size - pad - 1)
        outline = (37, 99, 235, 255)
        width = max(2, size // 12)
        radius = max(3, size // 8)
        try:
            d.rounded_rectangle(box, radius=radius, outline=outline, width=width, fill=(255, 255, 255, 255))
        except Exception:  # noqa: BLE001
            d.rectangle(box, outline=outline, width=width, fill=(255, 255, 255, 255))
        if checked:
            try:
                d.rounded_rectangle(box, radius=radius, outline=outline, width=width, fill=outline)
            except Exception:  # noqa: BLE001
                d.rectangle(box, outline=outline, width=width, fill=outline)
            x0, y0, x1, y1 = box
            w, h = x1 - x0, y1 - y0
            d.line(
                [
                    (x0 + w * 0.18, y0 + h * 0.52),
                    (x0 + w * 0.42, y0 + h * 0.78),
                    (x0 + w * 0.82, y0 + h * 0.28),
                ],
                fill=(255, 255, 255, 255),
                width=max(3, size // 8),
                joint="curve",
            )
        return ImageTk.PhotoImage(img, master=master)

    return draw(True), draw(False)


SEARCH_DEBOUNCE_MS = 100
UNFILTERED_CAP = 600
FILTERED_CAP = 2500
GROUP_TITLES = ("已勾选（走代理）", "未勾选（直连）", "无法分流")


def _entry_hay(entry) -> str:
    hay = getattr(entry, "_haystack", None)
    if hay is None:
        hay = f"{entry.name} {entry.exe} {entry.path}".lower()
        entry._haystack = hay
    return hay


def _entry_checked(entry, selected: set[str]) -> bool:
    return bool(getattr(entry, "supported", True) and entry.exe and entry.key in selected)


def _entry_group(entry, selected: set[str]) -> int:
    if _entry_checked(entry, selected):
        return 0
    return 1 if getattr(entry, "supported", True) else 2


def picker_rows(entries, selected: set[str], query: str, sel_filter: str) -> list:
    """Sort checked-first, then apply search / 已勾选 / 未勾选 filters."""
    rows = list(entries)
    have = {e.key for e in rows if getattr(e, "supported", True) and e.exe}
    missing = [k for k in selected if k not in have]
    if missing:
        from win_apps import AppEntry

        rows = [AppEntry(exe=k, name=k, path="", source="saved", supported=True) for k in missing] + rows

    rows.sort(key=lambda e: (_entry_group(e, selected), e.name.lower(), e.exe.lower()))
    q = query.strip().lower()
    out = []
    for e in rows:
        checked = _entry_checked(e, selected)
        if q and q not in _entry_hay(e):
            continue
        if sel_filter == "checked" and not checked:
            continue
        if sel_filter == "unchecked" and (checked or not getattr(e, "supported", True)):
            continue
        out.append(e)
    return out


def _open_picker(root) -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk

    from verge_ctl import apply_processes, reload_verge
    from win_apps import scan_apps, scan_running

    win = tk.Toplevel(root)
    win.title("MaintainAll 分应用白名单")
    win.geometry("560x640")
    win.minsize(420, 360)

    status = tk.StringVar(value="扫描中…")
    query = tk.StringVar()
    tab = tk.StringVar(value="apps")
    sel_filter = tk.StringVar(value="all")
    selected: set[str] = _selected_from_state()
    apps: list = []
    running: list = []
    rebuild_job: str | None = None

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

    list_frame = ttk.Frame(win, padding=8)
    list_frame.pack(fill="both", expand=True)
    dpi = float(win.winfo_fpixels("1i") or 96)
    check_size = max(26, int(28 * dpi / 96))
    img_on, img_off = _checkbox_images(win, check_size)
    win._picker_check_on = img_on
    win._picker_check_off = img_off
    style = ttk.Style(win)
    style.configure("AppPicker.Treeview", rowheight=max(32, check_size + 10), indent=0)
    tree = ttk.Treeview(
        list_frame,
        columns=("name",),
        show="tree headings",
        selectmode="browse",
        takefocus=True,
        style="AppPicker.Treeview",
    )
    check_col_w = check_size + 28
    tree.heading("#0", text="勾选", anchor="center")
    tree.column("#0", width=check_col_w, minwidth=check_col_w, stretch=False, anchor="center")
    tree.heading("name", text="应用", anchor="w")
    tree.column("name", anchor="w", stretch=True, minwidth=200)
    vsb = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")
    tree.tag_configure("header", font=("", 9, "bold"))
    tree.tag_configure("unsupported", foreground="#888")
    tree.tag_configure("trunc", foreground="#666")

    foot = ttk.Frame(win, padding=8)
    foot.pack(fill="x")
    ttk.Label(foot, textvariable=status, wraplength=520).pack(fill="x", pady=(0, 6))

    action = ttk.Frame(foot)
    action.pack(fill="x")

    def current_list() -> list:
        return running if tab.get() == "running" else apps

    def rebuild(*_a) -> None:
        nonlocal rebuild_job
        rebuild_job = None
        q = query.get()
        rows = picker_rows(current_list(), selected, q, sel_filter.get())
        total = len(rows)
        cap = FILTERED_CAP if q.strip() else UNFILTERED_CAP
        truncated = total > cap
        rows = rows[:cap]

        prev = tree.selection()
        y0 = tree.yview()[0]
        kids = tree.get_children()
        if kids:
            tree.delete(*kids)

        last_group = None
        shown = 0
        seen: set[str] = set()
        for e in rows:
            group = _entry_group(e, selected)
            if group != last_group:
                last_group = group
                tree.insert(
                    "",
                    "end",
                    iid=f"_h{group}",
                    text="",
                    values=(GROUP_TITLES[group],),
                    tags=("header",),
                )
            if not e.supported:
                iid = f"_u{shown}:{e.key or e.name}"
                note = e.note or "无法分流"
                tree.insert(
                    "",
                    "end",
                    iid=iid,
                    text="",
                    values=(f"○ {e.name}  — {note}",),
                    tags=("unsupported",),
                )
                shown += 1
                continue
            key = e.key
            if not key or key in seen:
                continue
            seen.add(key)
            tree.insert(
                "",
                "end",
                iid=key,
                text="",
                image=img_on if key in selected else img_off,
                values=(f"{e.name}  ({e.exe})",),
            )
            shown += 1
        if truncated:
            tree.insert("", "end", iid="_trunc", text="", values=("列表已截断，请用搜索缩小范围。",), tags=("trunc",))

        if prev:
            keep = [i for i in prev if tree.exists(i)]
            if keep:
                tree.selection_set(keep)
                tree.see(keep[0])
            else:
                tree.yview_moveto(y0)
        extra = f" / 共 {total}" if truncated else ""
        status.set(f"显示 {shown}{extra} 项，已勾选 {len(selected)} 个进程")

    def schedule_rebuild(delay_ms: int = 0, *_a) -> None:
        nonlocal rebuild_job
        if rebuild_job is not None:
            try:
                win.after_cancel(rebuild_job)
            except tk.TclError:
                pass
            rebuild_job = None
        if delay_ms <= 0:
            rebuild()
            return
        rebuild_job = win.after(delay_ms, rebuild)

    def toggle_iid(iid: str) -> None:
        if not iid or iid.startswith("_") or not tree.exists(iid):
            return
        if iid in selected:
            selected.discard(iid)
        else:
            selected.add(iid)
        rebuild()
        if tree.exists(iid):
            tree.selection_set(iid)
            tree.see(iid)
            tree.focus(iid)

    def on_tree_click(event) -> str | None:
        if tree.identify_region(event.x, event.y) in ("heading", "separator", "nothing"):
            return None
        if tree.identify_column(event.x) != "#0":
            return None
        iid = tree.identify_row(event.y)
        if iid:
            toggle_iid(iid)
            return "break"
        return None

    def on_mousewheel(event) -> str:
        tree.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    tree.bind("<Button-1>", on_tree_click)
    tree.bind("<MouseWheel>", on_mousewheel)

    def refresh_scan() -> None:
        status.set("正在扫描开始菜单和进程…")
        win.update_idletasks()

        def work():
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

    query.trace_add("write", lambda *_a: schedule_rebuild(SEARCH_DEBOUNCE_MS))
    tab.trace_add("write", lambda *_a: schedule_rebuild(0))
    sel_filter.trace_add("write", lambda *_a: schedule_rebuild(0))

    def _on_close() -> None:
        nonlocal rebuild_job
        if rebuild_job is not None:
            try:
                win.after_cancel(rebuild_job)
            except tk.TclError:
                pass
            rebuild_job = None
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", _on_close)
    search.focus_set()
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
