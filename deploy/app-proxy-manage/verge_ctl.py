"""Write whitelist PROCESS-NAME rules and reload Clash Verge's mihomo core."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from profile_rules import replace_process_rules, unique_exes  # noqa: E402

try:
    from install import PROFILE_FILE, STATE_PATH, load_state, save_state, verge_config_dir
except ImportError:  # pragma: no cover
    PROFILE_FILE = "LMaintainAll.yaml"
    STATE_PATH = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "MaintainAll" / "app-proxy" / "wizard.json"

    def verge_config_dir() -> Path:
        return Path(os.environ.get("APPDATA", "")) / "io.github.clash-verge-rev.clash-verge-rev"

    def load_state():
        return None

    def save_state(_st) -> None:
        return None


def _load_yaml(path: Path) -> dict:
    import yaml

    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"不是 YAML 对象: {path}")
    return loaded


def _dump_yaml(path: Path, data: dict, header: str = "") -> None:
    import yaml

    body = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    text = f"{header}{body}" if header else body
    path.write_text(text, encoding="utf-8")


def profile_path() -> Path:
    return verge_config_dir() / "profiles" / PROFILE_FILE


def runtime_path() -> Path:
    return verge_config_dir() / "clash-verge.yaml"


def patch_yaml_file(path: Path, processes: list[str], *, header: str = "") -> None:
    data = _load_yaml(path)
    replace_process_rules(data, processes)
    existing = path.read_text(encoding="utf-8")
    if not header and existing.startswith("#"):
        first = existing.splitlines()[0]
        if first.startswith("#"):
            header = first + "\n"
    _dump_yaml(path, data, header=header)


def save_wizard_processes(processes: list[str]) -> None:
    procs = unique_exes(processes)
    st = load_state()
    if st is None:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(
            json.dumps({"processes": procs}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return
    st.processes = procs
    save_state(st)


def apply_processes(processes: list[str]) -> tuple[Path, Path | None]:
    procs = unique_exes(processes)
    dest = profile_path()
    if not dest.is_file():
        raise FileNotFoundError(
            f"未找到 {dest}。请先运行 python install.py 生成 MaintainAll profile。"
        )
    patch_yaml_file(dest, procs)
    save_wizard_processes(procs)
    rt = runtime_path()
    if rt.is_file():
        patch_yaml_file(rt, procs)
        return dest, rt
    return dest, None


def _controller_from_runtime() -> tuple[str, str, str]:
    """Return (tcp_url_or_empty, pipe_name, secret)."""
    rt = runtime_path()
    secret = "set-your-secret"
    tcp = ""
    pipe = r"\\.\pipe\verge-mihomo"
    if not rt.is_file():
        return tcp, pipe, secret
    data = _load_yaml(rt)
    secret = str(data.get("secret") or secret)
    ext = str(data.get("external-controller") or "").strip()
    if ext and ext not in ("", "''"):
        if not ext.startswith("http"):
            tcp = f"http://{ext}"
        else:
            tcp = ext
    p = str(data.get("external-controller-pipe") or "").strip()
    if p:
        p = p.replace("\0", "")
        if p.startswith("\\\\.\\pipe\\"):
            pipe = p
        elif p.startswith("\\.\\pipe\\"):
            pipe = "\\" + p
        elif "verge-mihomo" in p:
            pipe = r"\\.\pipe\verge-mihomo"
        else:
            pipe = p
    return tcp, pipe, secret


def _http_request(url: str, method: str, body: bytes, secret: str, timeout: float = 8.0) -> tuple[int, bytes]:
    req = Request(url, data=body if method != "GET" else None, method=method)
    req.add_header("Authorization", f"Bearer {secret}")
    if method != "GET":
        req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except HTTPError as e:
        return e.code, e.read() if e.fp else b""


def _pipe_request(pipe: str, method: str, path: str, body: bytes, secret: str) -> tuple[int, bytes]:
    import ctypes
    from ctypes import wintypes

    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    OPEN_EXISTING = 3
    FILE_SHARE_READ = 1
    FILE_SHARE_WRITE = 2
    INVALID = wintypes.HANDLE(-1).value

    k32 = ctypes.windll.kernel32
    handle = k32.CreateFileW(
        pipe,
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        0,
        None,
    )
    if handle == INVALID or handle == -1:
        raise FileNotFoundError(f"无法打开 {pipe}")
    try:
        payload = body if method != "GET" else b""
        req = (
            f"{method} {path} HTTP/1.1\r\n"
            f"Host: localhost\r\n"
            f"Authorization: Bearer {secret}\r\n"
            "Connection: close\r\n"
        )
        if method != "GET":
            req += "Content-Type: application/json\r\n"
            req += f"Content-Length: {len(payload)}\r\n"
        req += "\r\n"
        data = req.encode("ascii") + payload

        written = wintypes.DWORD()
        if not k32.WriteFile(handle, data, len(data), ctypes.byref(written), None):
            raise OSError("named pipe WriteFile 失败")

        chunks: list[bytes] = []
        buf = ctypes.create_string_buffer(16384)
        nread = wintypes.DWORD()
        deadline = time.time() + 8
        while time.time() < deadline:
            ok = k32.ReadFile(handle, buf, 16384, ctypes.byref(nread), None)
            if not ok or nread.value == 0:
                break
            chunks.append(buf.raw[: nread.value])
            joined = b"".join(chunks)
            header_end = joined.find(b"\r\n\r\n")
            if header_end == -1:
                continue
            headers, rest = joined[:header_end], joined[header_end + 4 :]
            clen = None
            for line in headers.split(b"\r\n")[1:]:
                if line.lower().startswith(b"content-length:"):
                    clen = int(line.split(b":", 1)[1].strip() or 0)
            if clen is not None and len(rest) >= clen:
                break
            if clen is None and len(rest) > 0:
                # no content-length; stop after first successful body read
                break
        raw = b"".join(chunks)
        if not raw:
            return 0, b""
        status_line = raw.split(b"\r\n", 1)[0].decode("latin-1", errors="replace")
        parts = status_line.split()
        code = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
        idx = raw.find(b"\r\n\r\n")
        body_out = raw[idx + 4 :] if idx != -1 else b""
        return code, body_out
    finally:
        k32.CloseHandle(handle)


def mihomo_call(method: str, api_path: str, payload: dict | None = None) -> tuple[str, int, bytes]:
    tcp, pipe, secret = _controller_from_runtime()
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    errors: list[str] = []
    if tcp:
        url = tcp.rstrip("/") + api_path
        try:
            code, resp = _http_request(url, method, body, secret)
            return f"tcp:{tcp}", code, resp
        except (URLError, OSError, TimeoutError) as e:
            errors.append(f"TCP {e}")
    try:
        code, resp = _pipe_request(pipe, method, api_path, body, secret)
        return f"pipe:{pipe}", code, resp
    except OSError as e:
        errors.append(f"pipe {e}")
    raise RuntimeError("无法连接 Clash Verge 控制器: " + "; ".join(errors) or "未知错误")


def reload_verge() -> str:
    rt = runtime_path()
    payload = {"path": str(rt) if rt.is_file() else "", "payload": ""}
    via, code, resp = mihomo_call("PUT", "/configs?force=true", payload)
    if code in (200, 204):
        return f"已重载 ({via}, HTTP {code})"
    # Fallback: send file contents as payload (SAFE_PATHS)
    if rt.is_file() and code in (0, 400, 403, 404):
        via2, code2, resp2 = mihomo_call(
            "PUT",
            "/configs?force=true",
            {"path": "", "payload": rt.read_text(encoding="utf-8")},
        )
        if code2 in (200, 204):
            return f"已重载 ({via2}, payload, HTTP {code2})"
        resp, code, via = resp2, code2, via2
    snippet = (resp or b"").decode("utf-8", errors="replace")[:300]
    raise RuntimeError(f"重载失败 {via} HTTP {code}: {snippet or '空响应'}。可在 Verge 配置文件页手动点重载。")


def ping_verge() -> str:
    via, code, resp = mihomo_call("GET", "/version")
    if code == 200:
        return f"{via} {resp.decode('utf-8', errors='replace').strip()}"
    raise RuntimeError(f"控制器无响应 {via} HTTP {code}")
