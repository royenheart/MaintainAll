"""Enumerate Windows Start Menu apps and running processes.

Linux / macOS: not implemented here; callers must not import this module.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from profile_rules import normalize_exe

SKIP_EXES = {
    "applicationframehost.exe",
    "explorer.exe",
    "dwm.exe",
    "sihost.exe",
    "ctfmon.exe",
    "runtimebroker.exe",
    "searchhost.exe",
    "searchapp.exe",
    "startmenuexperiencehost.exe",
    "shellexperiencehost.exe",
    "textinputhost.exe",
    "systemsettings.exe",
    "taskmgr.exe",
    "securityhealthsystray.exe",
    "securityhealthservice.exe",
    "lockapp.exe",
    "logonui.exe",
    "conhost.exe",
    "dllhost.exe",
    "svchost.exe",
    "services.exe",
    "lsass.exe",
    "csrss.exe",
    "smss.exe",
    "winlogon.exe",
    "wininit.exe",
    "fontdrvhost.exe",
    "chxsmartui.exe",
    "widgetservice.exe",
    "widgets.exe",
    "phoneexperiencehost.exe",
    "crashpad_handler.exe",
    "update.exe",
    "unins000.exe",
}

SKIP_NAME_RE = re.compile(r"(卸载|uninstall|help|readme|website|license|setup)", re.I)

# System32 根目录有几百个系统工具；真正给用户用的 CLI 在子目录（OpenSSH）或 PATH 里的非根路径。
SYSTEM32_SUBDIR_SKIP = {
    "applocker",
    "apppatch",
    "catroot",
    "catroot2",
    "com",
    "config",
    "dism",
    "downlevel",
    "drivers",
    "driverstore",
    "fxstmp",
    "ias",
    "inetsrv",
    "logfiles",
    "migration",
    "msdtc",
    "restoration",
    "setup",
    "spart",
    "spp",
    "sru",
    "tasks",
    "wbem",
    "wdi",
    "winevt",
    "winbiodatabase",
}

SKIP_PATH_DIR_RE = re.compile(
    r"(miniconda|anaconda|\\python\d+|\\scripts$|\\library\\bin|node_modules|\\npm\\)",
    re.I,
)


@dataclass
class AppEntry:
    exe: str
    name: str
    path: str = ""
    source: str = ""
    supported: bool = True
    note: str = ""

    @property
    def key(self) -> str:
        return self.exe.lower()


def _user32():
    import ctypes

    return ctypes.windll.user32


def _kernel32():
    import ctypes

    return ctypes.windll.kernel32


def _shortcut_dirs() -> list[Path]:
    appdata = os.environ.get("APPDATA", "")
    programdata = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    dirs = []
    if appdata:
        dirs.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    dirs.append(Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return [d for d in dirs if d.is_dir()]


def _read_shortcuts() -> list[AppEntry]:
    dirs = _shortcut_dirs()
    if not dirs:
        return []
    dir_json = json.dumps([str(d) for d in dirs], ensure_ascii=False).replace("'", "''")
    tmp = Path(os.environ.get("TEMP", ".")) / f"maintainall-startmenu-{os.getpid()}.json"
    tmp_ps = str(tmp).replace("'", "''")
    script = f"""
$ErrorActionPreference = 'SilentlyContinue'
$dirs = '{dir_json}' | ConvertFrom-Json
$shell = New-Object -ComObject WScript.Shell
$rows = [System.Collections.Generic.List[object]]::new()
foreach ($d in $dirs) {{
  if (-not (Test-Path -LiteralPath $d)) {{ continue }}
  Get-ChildItem -LiteralPath $d -Recurse -Filter *.lnk | ForEach-Object {{
    try {{
      $s = $shell.CreateShortcut($_.FullName)
      $rows.Add([pscustomobject]@{{
        name = $_.BaseName
        target = [string]$s.TargetPath
      }}) | Out-Null
    }} catch {{}}
  }}
}}
$rows | ConvertTo-Json -Compress -Depth 3 | Set-Content -LiteralPath '{tmp_ps}' -Encoding utf8
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-STA", "-Command", script],
        capture_output=True,
        timeout=60,
        check=False,
    )
    if not tmp.is_file():
        return []
    try:
        raw = tmp.read_text(encoding="utf-8-sig").strip()
    finally:
        tmp.unlink(missing_ok=True)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    out: list[AppEntry] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        target = str(row.get("target") or "").strip().strip('"')
        if not name or SKIP_NAME_RE.search(name):
            continue
        if not target.lower().endswith(".exe"):
            if target:
                out.append(
                    AppEntry(
                        exe="",
                        name=name,
                        path=target,
                        source="shortcut",
                        supported=False,
                        note="无 Win32 exe（商店/UWP 快捷方式）",
                    )
                )
            continue
        exe = normalize_exe(target)
        if not exe or exe.lower() in SKIP_EXES:
            continue
        if _is_system32_root_exe(target):
            continue
        out.append(AppEntry(exe=exe, name=name, path=target, source="shortcut"))
    return out


def _pid_image_path(pid: int) -> str:
    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    k32 = _kernel32()
    handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(32768)
        ok = k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
        return buf.value if ok else ""
    finally:
        k32.CloseHandle(handle)


def _window_titles_by_pid() -> dict[int, str]:
    import ctypes
    from ctypes import wintypes

    user32 = _user32()
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindow.argtypes = [wintypes.HWND, ctypes.c_uint]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL

    titles: dict[int, str] = {}
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    GW_OWNER = 4

    @WNDENUMPROC
    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetWindow(hwnd, GW_OWNER):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if not title:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value and pid.value not in titles:
            titles[pid.value] = title
        return True

    user32.EnumWindows(callback, 0)
    return titles


def _iter_process_ids() -> list[int]:
    import ctypes
    from ctypes import wintypes

    TH32CS_SNAPPROCESS = 0x00000002
    INVALID = 0xFFFFFFFF

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    k32 = _kernel32()
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID:
        return []
    pids: list[int] = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if not k32.Process32FirstW(snap, ctypes.byref(entry)):
            return []
        while True:
            if entry.th32ProcessID:
                pids.append(int(entry.th32ProcessID))
            if not k32.Process32NextW(snap, ctypes.byref(entry)):
                break
        return pids
    finally:
        k32.CloseHandle(snap)


def _running_entries(*, windowed_only: bool) -> list[AppEntry]:
    titles = _window_titles_by_pid()
    out: list[AppEntry] = []
    seen: set[str] = set()
    pids = list(titles) if windowed_only else _iter_process_ids()
    if not windowed_only:
        # Prefer PIDs that have a window, then the rest.
        extra = [p for p in pids if p not in titles]
        pids = list(titles) + extra
    for pid in pids:
        path = _pid_image_path(pid)
        if not path.lower().endswith(".exe"):
            continue
        exe = normalize_exe(path)
        if not exe or exe.lower() in SKIP_EXES:
            continue
        if re.search(r"(setup|crashhelper|unins\d+)", exe, re.I):
            continue
        if windowed_only and pid not in titles:
            continue
        if not windowed_only and pid not in titles and _is_system32_root_exe(path):
            continue
        key = exe.lower()
        if key in seen:
            continue
        seen.add(key)
        title = titles.get(pid, "")
        name = title.split(" - ")[-1].strip() if title else Path(path).stem
        if exe.lower() == "applicationframehost.exe":
            continue
        src = "window" if pid in titles else "process"
        out.append(AppEntry(exe=exe, name=name or exe, path=path, source=src))
    return out


def merge_entries(groups: list[list[AppEntry]]) -> list[AppEntry]:
    """Dedupe by exe; prefer shortcut names, then window titles. Drop unsupported without exe."""
    by_key: dict[str, AppEntry] = {}
    rank = {"shortcut": 0, "component": 1, "apppath": 1, "path": 2, "window": 3, "process": 4}
    unsupported: list[AppEntry] = []
    for group in groups:
        for e in group:
            if not e.supported or not e.exe:
                if e.name:
                    unsupported.append(e)
                continue
            prev = by_key.get(e.key)
            if prev is None:
                by_key[e.key] = e
                continue
            if rank.get(e.source, 9) < rank.get(prev.source, 9):
                by_key[e.key] = AppEntry(
                    exe=e.exe,
                    name=e.name or prev.name,
                    path=e.path or prev.path,
                    source=e.source,
                )
            elif not prev.name and e.name:
                by_key[e.key] = AppEntry(
                    exe=prev.exe,
                    name=e.name,
                    path=prev.path or e.path,
                    source=prev.source,
                )
    apps = sorted(by_key.values(), key=lambda a: a.name.lower())
    # Keep a short unsupported hint list (dedupe by name), after supported apps.
    seen_u: set[str] = set()
    hints: list[AppEntry] = []
    for e in unsupported:
        k = e.name.lower()
        if k in seen_u:
            continue
        seen_u.add(k)
        hints.append(e)
        if len(hints) >= 40:
            break
    return apps + hints


def _win_dir() -> Path:
    return Path(os.environ.get("WINDIR", r"C:\Windows"))


def _system32_roots() -> list[Path]:
    win = _win_dir()
    out: list[Path] = []
    seen: set[str] = set()
    for p in (win / "System32", win / "SysWOW64", win / "Sysnative"):
        if not p.is_dir():
            continue
        try:
            key = str(p.resolve()).lower()
        except OSError:
            key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _is_system32_root_dir(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    for root in _system32_roots():
        try:
            if resolved == root.resolve():
                return True
        except OSError:
            continue
    return False


def _is_system32_root_exe(path: str) -> bool:
    try:
        parent = Path(path).parent.resolve()
    except OSError:
        parent = Path(path).parent
    return _is_system32_root_dir(parent)


def _entry_from_exe_file(file: Path, source: str) -> AppEntry | None:
    if not file.is_file() or file.suffix.lower() != ".exe":
        return None
    exe = normalize_exe(file.name)
    if not exe or exe.lower() in SKIP_EXES:
        return None
    if re.search(r"(setup|crashhelper|unins\d+)", exe, re.I):
        return None
    folder = file.parent.name
    if folder.lower() in {"cmd", "bin", "usr", "system32", "syswow64"}:
        name = Path(exe).stem
    else:
        name = f"{folder} ({exe})"
    return AppEntry(exe=exe, name=name, path=str(file), source=source)


def _system_component_entries() -> list[AppEntry]:
    """Windows optional components live in System32 subfolders (OpenSSH), not the root."""
    out: list[AppEntry] = []
    for root in _system32_roots():
        try:
            subs = list(root.iterdir())
        except OSError:
            continue
        for sub in subs:
            if not sub.is_dir() or sub.name.lower() in SYSTEM32_SUBDIR_SKIP:
                continue
            files: list[Path] = []
            try:
                files.extend(p for p in sub.glob("*.exe") if p.is_file())
                for nested in sub.iterdir():
                    if nested.is_dir() and nested.name.lower() not in SYSTEM32_SUBDIR_SKIP:
                        files.extend(p for p in nested.glob("*.exe") if p.is_file())
            except OSError:
                continue
            if len(files) > 24:
                continue
            for f in files:
                e = _entry_from_exe_file(f, "component")
                if e:
                    out.append(e)
    return out


def _path_cli_entries() -> list[AppEntry]:
    out: list[AppEntry] = []
    seen_dir: set[str] = set()
    for raw in os.environ.get("PATH", "").split(os.pathsep):
        d = Path(raw.strip().strip('"'))
        if not d.is_dir():
            continue
        try:
            key = str(d.resolve()).lower()
        except OSError:
            key = str(d).lower()
        if key in seen_dir:
            continue
        seen_dir.add(key)
        if _is_system32_root_dir(d):
            continue
        if SKIP_PATH_DIR_RE.search(str(d)):
            continue
        try:
            files = [p for p in d.glob("*.exe") if p.is_file()]
        except OSError:
            continue
        if len(files) > 40:
            continue
        for f in files:
            e = _entry_from_exe_file(f, "path")
            if e:
                out.append(e)
    return out


def _app_path_entries() -> list[AppEntry]:
    import winreg

    out: list[AppEntry] = []
    roots = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
    ]
    for hive, sub in roots:
        try:
            key = winreg.OpenKey(hive, sub)
        except OSError:
            continue
        try:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(key, i)
                except OSError:
                    break
                i += 1
                if not name.lower().endswith(".exe"):
                    continue
                try:
                    with winreg.OpenKey(key, name) as item:
                        target, _typ = winreg.QueryValueEx(item, "")
                except OSError:
                    continue
                target = str(target or "").strip().strip('"')
                if not target.lower().endswith(".exe") or _is_system32_root_exe(target):
                    continue
                p = Path(os.path.expandvars(target))
                e = _entry_from_exe_file(p, "apppath")
                if e:
                    out.append(e)
        finally:
            winreg.CloseKey(key)
    return out


def scan_apps() -> list[AppEntry]:
    return merge_entries(
        [
            _read_shortcuts(),
            _system_component_entries(),
            _path_cli_entries(),
            _app_path_entries(),
            _running_entries(windowed_only=True),
        ]
    )


def scan_running() -> list[AppEntry]:
    return merge_entries(
        [
            _system_component_entries(),
            _running_entries(windowed_only=False),
        ]
    )
