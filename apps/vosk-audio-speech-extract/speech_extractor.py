#!/usr/bin/env python3
"""
Speech Extractor — Textual TUI
从本地音视频文件提取字幕，支持 Vosk / Whisper / 豆包 ASR 三种后端，
以及带时间轴字幕、段落合并、口述稿整理三种后处理模式。
"""

# =============================================================================
# Section 1: 导入与可用性检测
# =============================================================================
from __future__ import annotations

import argparse
import collections
import json
import os
import socket
import sys
import tempfile
import threading
import time
import uuid
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

# ---------- 必需第三方 ----------
try:
    import ffmpeg
except ImportError:
    print("错误：请安装 ffmpeg-python：pip install ffmpeg-python", file=sys.stderr)
    sys.exit(1)

try:
    import keyring
except ImportError:
    print("错误：请安装 keyring：pip install keyring", file=sys.stderr)
    sys.exit(1)

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, ScrollableContainer, Vertical
    from textual.screen import ModalScreen
    from textual.widgets import (
        Button,
        DirectoryTree,
        Footer,
        Header,
        Input,
        Label,
        ProgressBar,
        RadioButton,
        RadioSet,
        RichLog,
        Select,
        TabbedContent,
        TabPane,
        TextArea,
    )
    from textual.worker import WorkerCancelled
except ImportError:
    print("错误：请安装 textual：pip install textual", file=sys.stderr)
    sys.exit(1)

# ---------- 可选后端 ----------
try:
    from vosk import KaldiRecognizer
    from vosk import Model as VoskModel
    from vosk import SetLogLevel as VoskSetLogLevel

    VoskSetLogLevel(-1)
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False

try:
    import whisper as openai_whisper

    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

try:
    import boto3
    import requests as http_requests
    from botocore.config import Config as BotoConfig

    DOUBAO_AVAILABLE = True
except ImportError:
    DOUBAO_AVAILABLE = False

try:
    from openai import OpenAI

    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False


# =============================================================================
# Section 2: 配置与密钥管理
# =============================================================================

CONFIG_DIR = Path.home() / ".vosk_speech"
CONFIG_FILE = CONFIG_DIR / "config.json"
KEYRING_SVC = "vosk-speech-extractor"

DEFAULT_CONFIG: dict = {
    "default_engine": "whisper",  # vosk | whisper | doubao
    "whisper_model_size": "small",  # tiny | base | small | medium | large
    "whisper_language": "zh",
    "vosk_model_path": "models/vosk-model-small-cn-0.22",
    "r2_account_id": "",
    "r2_bucket": "",
    "llm_type": "doubao",  # doubao | openai
    "llm_base_url": "https://ark.cn-beijing.volces.com/api/v3",
    "llm_model": "doubao-seed-1-6-flash-250615",
    "output_dir": "speeches",
    "paragraph_gap": 2.0,
}


def load_config() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with CONFIG_FILE.open(encoding="utf-8") as f:
                data = json.load(f)
            # 补全缺失键
            merged = {**DEFAULT_CONFIG, **data}
            return merged
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_secret(key: str) -> str:
    val = keyring.get_password(KEYRING_SVC, key)
    return val or ""


def set_secret(key: str, value: str) -> None:
    if value:
        keyring.set_password(KEYRING_SVC, key, value)
    else:
        try:
            keyring.delete_password(KEYRING_SVC, key)
        except Exception:
            pass


# =============================================================================
# Section 2.5: 日志系统（AppLogger + LogServer）
# =============================================================================

_LOG_MAX = 1000  # 内存最多保留条数


@dataclass
class LogRecord:
    seq: int        # 全局递增序号
    ts: float       # time.time()
    level: str      # "DEBUG" | "INFO" | "WARNING" | "ERROR"
    source: str     # 调用来源，如 "Whisper" / "DoubaoASR" / "LLM" / "R2"
    message: str    # 不含任何 secret / 用户内容原文


class AppLogger:
    """
    全局单例日志收集器。线程安全，环形缓冲 1000 条。
    所有调用方只传元数据，绝不传 API Key / 原始文本内容。
    """

    _instance: AppLogger | None = None
    _lock_cls: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        self._buf: collections.deque[LogRecord] = collections.deque(maxlen=_LOG_MAX)
        self._lock = threading.Lock()
        self._seq = 0
        # 已注册的实时推送回调（LogServer 使用）
        self._listeners: list[Callable[[LogRecord], None]] = []

    @classmethod
    def get(cls) -> "AppLogger":
        if cls._instance is None:
            with cls._lock_cls:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def log(self, level: str, source: str, message: str) -> None:
        with self._lock:
            self._seq += 1
            rec = LogRecord(
                seq=self._seq,
                ts=time.time(),
                level=level,
                source=source,
                message=message,
            )
            self._buf.append(rec)
            listeners = list(self._listeners)
        for fn in listeners:
            try:
                fn(rec)
            except Exception:
                pass

    def debug(self, source: str, message: str) -> None:
        self.log("DEBUG", source, message)

    def info(self, source: str, message: str) -> None:
        self.log("INFO", source, message)

    def warning(self, source: str, message: str) -> None:
        self.log("WARNING", source, message)

    def error(self, source: str, message: str) -> None:
        self.log("ERROR", source, message)

    def get_range(self, offset: int, limit: int) -> list[LogRecord]:
        """返回 seq >= offset 的最多 limit 条记录。"""
        with self._lock:
            buf = list(self._buf)
        result = [r for r in buf if r.seq >= offset]
        return result[:limit]

    def get_tail(self, n: int) -> list[LogRecord]:
        with self._lock:
            buf = list(self._buf)
        return buf[-n:] if n < len(buf) else buf

    def count(self) -> int:
        with self._lock:
            return len(self._buf)

    def total_seq(self) -> int:
        with self._lock:
            return self._seq

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()

    def add_listener(self, fn: Callable[[LogRecord], None]) -> None:
        with self._lock:
            self._listeners.append(fn)

    def remove_listener(self, fn: Callable[[LogRecord], None]) -> None:
        with self._lock:
            try:
                self._listeners.remove(fn)
            except ValueError:
                pass


# 全局单例，供全文件直接调用
app_logger = AppLogger.get()


def _rec_to_dict(r: LogRecord) -> dict:
    return {
        "seq": r.seq,
        "ts": r.ts,
        "level": r.level,
        "source": r.source,
        "message": r.message,
    }


class LogServer:
    """
    TCP 日志服务器。每个连接支持双向 JSON Lines 请求/响应协议：

    客户端命令（每行一个 JSON）：
      {"cmd": "count"}                         → {"type":"count","value":N}
      {"cmd": "get", "offset": N, "limit": M}  → {"type":"batch","records":[...]}
      {"cmd": "tail", "n": N}                  → {"type":"batch","records":[...]}
      {"cmd": "subscribe"}                     → 之后持续推送 {"type":"record",...}
      {"cmd": "unsubscribe"}                   → 停止推送

    新连接不自动推送历史，由客户端主动请求。
    """

    def __init__(self, port: int) -> None:
        self._port = port
        self._server_sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._clients: list[_LogClientHandler] = []
        self._clients_lock = threading.Lock()

    @property
    def port(self) -> int:
        return self._port

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._serve, daemon=True, name="log_server"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
        with self._clients_lock:
            for c in list(self._clients):
                c.close()

    def actual_port(self) -> int:
        """返回实际绑定的端口（用于 port=0 自动分配时）。"""
        if self._server_sock:
            return self._server_sock.getsockname()[1]
        return self._port

    def _serve(self) -> None:
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("127.0.0.1", self._port))
            srv.listen(8)
            srv.settimeout(1.0)
            self._server_sock = srv
            app_logger.info("LogServer", f"日志服务器已启动，监听 127.0.0.1:{srv.getsockname()[1]}")

            while not self._stop_event.is_set():
                try:
                    conn, addr = srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                handler = _LogClientHandler(conn, self)
                with self._clients_lock:
                    self._clients.append(handler)
                handler.start()

        except Exception as e:
            app_logger.error("LogServer", f"服务器启动失败：{e}")
        finally:
            app_logger.info("LogServer", "日志服务器已停止")

    def remove_client(self, handler: "_LogClientHandler") -> None:
        with self._clients_lock:
            try:
                self._clients.remove(handler)
            except ValueError:
                pass


class _LogClientHandler:
    """单个 TCP 客户端的处理器，运行在独立线程中。"""

    def __init__(self, conn: socket.socket, server: LogServer) -> None:
        self._conn = conn
        self._server = server
        self._subscribed = False
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="log_client"
        )
        self._send_lock = threading.Lock()

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._subscribed = False
        try:
            self._conn.close()
        except Exception:
            pass

    def _send(self, obj: dict) -> None:
        try:
            line = json.dumps(obj, ensure_ascii=False) + "\n"
            with self._send_lock:
                self._conn.sendall(line.encode("utf-8"))
        except Exception:
            pass

    def _on_record(self, rec: LogRecord) -> None:
        """AppLogger 回调——有新日志时推送给订阅的客户端。"""
        if self._subscribed:
            self._send({"type": "record", **_rec_to_dict(rec)})

    def _run(self) -> None:
        app_logger.add_listener(self._on_record)
        try:
            buf = b""
            self._conn.settimeout(30.0)
            while True:
                try:
                    chunk = self._conn.recv(4096)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        cmd_obj = json.loads(line.decode("utf-8"))
                    except Exception:
                        self._send({"type": "error", "message": "invalid JSON"})
                        continue
                    self._handle_cmd(cmd_obj)
        except Exception:
            pass
        finally:
            self._subscribed = False
            app_logger.remove_listener(self._on_record)
            self._server.remove_client(self)
            try:
                self._conn.close()
            except Exception:
                pass

    def _handle_cmd(self, obj: dict) -> None:
        cmd = obj.get("cmd", "")
        if cmd == "count":
            self._send({"type": "count", "value": app_logger.count(), "total_seq": app_logger.total_seq()})

        elif cmd == "get":
            offset = int(obj.get("offset", 0))
            limit = int(obj.get("limit", 100))
            limit = min(limit, 500)
            records = app_logger.get_range(offset, limit)
            self._send({
                "type": "batch",
                "total": app_logger.count(),
                "records": [_rec_to_dict(r) for r in records],
            })

        elif cmd == "tail":
            n = min(int(obj.get("n", 50)), 500)
            records = app_logger.get_tail(n)
            self._send({
                "type": "batch",
                "total": app_logger.count(),
                "records": [_rec_to_dict(r) for r in records],
            })

        elif cmd == "subscribe":
            self._subscribed = True
            self._send({"type": "ok", "message": "subscribed"})

        elif cmd == "unsubscribe":
            self._subscribed = False
            self._send({"type": "ok", "message": "unsubscribed"})

        else:
            self._send({"type": "error", "message": f"unknown command: {cmd!r}"})


# =============================================================================
# Section 3: 数据结构 + 音频工具
# =============================================================================


@dataclass
class Segment:
    start: float  # 秒
    end: float  # 秒
    text: str


def convert_to_wav(input_path: str) -> tuple[str, str]:
    """
    确保音频是 16kHz 单声道 WAV PCM。
    返回 (wav_path, tmpdir)。若已符合要求则直接返回原路径，tmpdir=""。
    调用方负责清理 tmpdir（若非空）。
    """

    def _is_valid_wav(path: str) -> bool:
        try:
            wf = wave.open(path, "rb")
            ok = (
                wf.getnchannels() == 1
                and wf.getsampwidth() == 2
                and wf.getcomptype() == "NONE"
            )
            wf.close()
            return ok
        except Exception:
            return False

    if input_path.lower().endswith(".wav") and _is_valid_wav(input_path):
        return input_path, ""

    tmpdir = tempfile.mkdtemp()
    out_path = os.path.join(tmpdir, "converted.wav")
    try:
        stream = ffmpeg.input(input_path)
        stream = ffmpeg.output(stream, out_path, ac=1, ar=16000, format="wav")
        ffmpeg.run(stream, quiet=True, overwrite_output=True)
    except ffmpeg.Error as e:
        stderr_text: Optional[str]
        if e.stderr is None:
            stderr_text = None
        elif isinstance(e.stderr, (bytes, bytearray)):
            stderr_text = e.stderr.decode(errors="replace")
        else:
            stderr_text = str(e.stderr)

        base_msg = f"ffmpeg 转换失败：{e}"
        if stderr_text:
            msg = f"{base_msg} | stderr: {stderr_text}"
        else:
            msg = base_msg

        raise RuntimeError(msg) from e
    return out_path, tmpdir


def detect_format(path: str) -> str:
    """根据扩展名返回豆包 ASR audio.format 字段值。"""
    ext = Path(path).suffix.lower().lstrip(".")
    mapping = {
        "mp3": "mp3",
        "mp4": "mp4",
        "wav": "wav",
        "ogg": "ogg",
        "flac": "wav",  # 先转 wav
        "m4a": "mp4",
        "aac": "mp4",
        "webm": "mp4",
        "mkv": "mp4",
        "mov": "mp4",
        "avi": "mp4",
    }
    return mapping.get(ext, "wav")


def _is_mainly_chinese(text: str) -> bool:
    """判断文本是否以中文为主（用于段落合并时决定分隔符）。"""
    chinese = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    return chinese > len(text) * 0.3


def cleanup_tmpdir(tmpdir: str) -> None:
    if tmpdir:
        import shutil

        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


# =============================================================================
# Section 3b: 字幕文件检测与解析
# =============================================================================

# 公认的字幕/文字稿文件扩展名（.txt 永远不是音视频，也归入此类）
_SUBTITLE_EXTENSIONS = {".srt", ".vtt", ".ass", ".ssa", ".sub", ".sbv", ".txt"}


def is_subtitle_file(path: str) -> bool:
    """
    判断文件是否为字幕/文字稿文件，不需要经过 ASR 处理。
    判断逻辑：
    1. 扩展名属于已知字幕/文本格式（.srt .vtt .ass .ssa .sub .sbv .txt）→ True
    2. 其余 → False（音视频文件）
    .txt 本身不可能是音视频，因此无论内容如何都视为文字稿。
    """
    ext = Path(path).suffix.lower()
    return ext in _SUBTITLE_EXTENSIONS


class SubtitleFileParser:
    """
    解析字幕/文字稿文件，提取干净的纯文本行列表。
    支持：
    - SRT（标准序号+时间戳格式）
    - WebVTT（含 <c> 内联标签、词级时间标签、重复行）
    - 纯文本（去除分隔符行）
    """

    @classmethod
    def parse(cls, path: str) -> List[str]:
        """
        自动检测格式并解析，返回干净文本行列表（已去空行）。
        """
        p = Path(path)
        raw = p.read_text(encoding="utf-8", errors="replace")
        ext = p.suffix.lower()
        lines_count = raw.count("\n")
        app_logger.debug("Parser", f"解析字幕 ext={ext} lines={lines_count}")

        if ext == ".vtt" or raw.lstrip().upper().startswith("WEBVTT"):
            return cls._parse_vtt(raw)
        if ext == ".srt" or cls._looks_like_srt(raw):
            return cls._parse_srt(raw)
        # 兜底：纯文本
        return cls._parse_plain(raw)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _looks_like_srt(text: str) -> bool:
        """简单启发：文本中能找到 SRT 时间戳行 'HH:MM:SS,mmm --> HH:MM:SS,mmm'。"""
        import re
        return bool(re.search(r"\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}", text))

    @staticmethod
    def _parse_srt(text: str) -> List[str]:
        """
        解析标准 SRT 格式：
        - 跳过纯数字序号行
        - 跳过时间戳行（含 -->）
        - 跳过空行
        - 保留文本行
        """
        import re
        lines = text.splitlines()
        result: List[str] = []
        timestamp_re = re.compile(r"\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->")
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.isdigit():
                continue
            if timestamp_re.search(stripped):
                continue
            result.append(stripped)
        return result

    @staticmethod
    def _parse_vtt(text: str) -> List[str]:
        """
        解析 WebVTT 格式（包括 YouTube 自动字幕）：
        1. 去掉 WEBVTT / Kind: / Language: 等头部行
        2. 去掉时间戳行（含 -->）
        3. 去掉内联时间标签 <HH:MM:SS.mmm> 和 <c></c> 标签
        4. 去掉纯空白行
        5. 相邻重复行去重（YouTube WebVTT 每段会重复上一行内容）
        6. 过滤掉空行和纯标点/符号行
        """
        import re

        # 去掉头部元数据
        header_re = re.compile(r"^(WEBVTT|Kind:|Language:|NOTE\b)", re.IGNORECASE)
        # 时间戳行（VTT 格式 HH:MM:SS.mmm 或 MM:SS.mmm）
        timestamp_re = re.compile(r"[\d:\.]+\s*-->")
        # 内联时间标签 <00:00:05.200>
        inline_time_re = re.compile(r"<\d{1,2}:\d{2}:\d{2}\.\d+>")
        # <c> 和 </c> 标签
        ctag_re = re.compile(r"</?c>")
        # 其他 HTML 标签（保险）
        other_tag_re = re.compile(r"<[^>]+>")

        lines = text.splitlines()
        cleaned: List[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if header_re.match(stripped):
                continue
            if timestamp_re.search(stripped):
                continue

            # 去掉内联标记
            stripped = inline_time_re.sub("", stripped)
            stripped = ctag_re.sub("", stripped)
            stripped = other_tag_re.sub("", stripped)
            stripped = stripped.strip()

            if not stripped:
                continue
            # 过滤纯符号行（如仅含空格/标点）
            if all(not c.isalnum() and c not in "，。！？、；：""''…—" for c in stripped):
                continue

            cleaned.append(stripped)

        # 相邻重复行去重（保留最后一次出现——YouTube WebVTT 最后出现的是完整句子）
        # 策略：向前扫描，若当前行是下一行的前缀（或相同），丢弃当前行
        deduped: List[str] = []
        for i, line in enumerate(cleaned):
            if i + 1 < len(cleaned) and cleaned[i + 1].startswith(line):
                # 当前行是下一行的前缀，跳过（下一行更完整）
                continue
            deduped.append(line)

        return deduped

    @staticmethod
    def _parse_plain(text: str) -> List[str]:
        """
        解析纯文本字幕/文字稿：
        - 去掉分隔符行：'...'、'---'、纯数字行、纯符号行
        - 去掉空行
        - 保留其余文本行
        """
        import re
        separator_re = re.compile(r"^([.\-_=\s]+|\d+)$")
        lines = text.splitlines()
        result: List[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if separator_re.match(stripped):
                continue
            result.append(stripped)
        return result


def _line_is_mainly_chinese(line: str) -> bool:
    """判断单行文字是否以中文为主（>30% 汉字）。"""
    if not line:
        return False
    zh = sum(1 for c in line if "\u4e00" <= c <= "\u9fff")
    return zh > len(line) * 0.3


def detect_bilingual(lines: List[str]) -> tuple[bool, str]:
    """
    检测文本行列表是否为双语交替格式（如 EN/ZH 逐行对应）。
    返回 (is_bilingual, recommend_keep)：
      - is_bilingual: 是否检测到双语交替
      - recommend_keep: 推荐保留语言 "zh" | "en" | "both"
    判断标准：
      - 相邻行语言交替（一行中文、一行英文）的比例超过 60%
    """
    if len(lines) < 4:
        return False, "both"

    alternating = 0
    for i in range(len(lines) - 1):
        a_zh = _line_is_mainly_chinese(lines[i])
        b_zh = _line_is_mainly_chinese(lines[i + 1])
        if a_zh != b_zh:  # 语言不同 → 交替
            alternating += 1

    ratio = alternating / (len(lines) - 1)
    if ratio < 0.6:
        return False, "both"

    # 判断首行语言，推荐以中文为主（通常中文翻译更重要）
    return True, "zh"


def filter_by_language(lines: List[str], keep: str) -> List[str]:
    """
    按语言过滤文本行。
    keep: "zh" 只保留中文行 | "en" 只保留英文行 | "both" 不过滤
    """
    if keep == "both":
        return lines
    want_zh = keep == "zh"
    return [l for l in lines if _line_is_mainly_chinese(l) == want_zh]


def assess_merge_complexity(text: str) -> tuple[float, str]:
    """
    对合并后的段落文本做复杂度评分（0~1），判断是否需要 LLM 精修。
    评分越高说明纯代码合并质量越差，越建议 LLM 精修。

    指标1（权重 0.5）：无句末标点的行占比
    指标2（权重 0.3）：段落数量偏少（说明合并过于粗暴）
    指标3（权重 0.2）：段落长度方差过大
    """
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return 0.0, "内容为空"

    # 指标1：无句末标点行占比
    end_puncts = set("。！？.!?")
    no_punct = sum(1 for l in lines if l[-1] not in end_puncts)
    score1 = no_punct / len(lines)

    # 指标2：段落太少（合并后段落数 vs 行数的期望比）
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    expected_para = max(len(lines) * 0.15, 1)
    score2 = max(0.0, 1.0 - len(paragraphs) / expected_para)

    # 指标3：段落长度标准差（归一化）
    if len(paragraphs) > 1:
        lengths = [len(p) for p in paragraphs]
        avg = sum(lengths) / len(lengths)
        std = (sum((x - avg) ** 2 for x in lengths) / len(lengths)) ** 0.5
        score3 = min(std / max(avg, 1), 1.0)
    else:
        score3 = 0.8  # 只有一段，说明完全没有分段

    score = score1 * 0.5 + score2 * 0.3 + score3 * 0.2
    score = min(max(score, 0.0), 1.0)

    if score >= 0.5:
        hint = f"段落结构较复杂（评分 {score:.0%}），建议 LLM 精修"
    else:
        hint = f"段落结构尚可（评分 {score:.0%}），可选 LLM 精修"

    return score, hint


# =============================================================================
# Section 4: 识别后端
# =============================================================================


class VoskBackend:
    @staticmethod
    def transcribe(
        audio_path: str,
        model_path: str,
        progress_cb: Callable[[float, str], None],
        cancel_event: threading.Event,
    ) -> List[Segment]:
        """
        使用 Vosk 转写，返回句级 Segment 列表（含时间戳）。
        从 KaldiRecognizer.Result() JSON 的 result[] 取词级时间戳，
        合并为句级 Segment(start=第一词.start, end=最后词.end, text)。
        """
        if not VOSK_AVAILABLE:
            raise RuntimeError("Vosk 未安装，请运行：pip install vosk")

        wav_path, tmpdir = convert_to_wav(audio_path)
        try:
            wf = wave.open(wav_path, "rb")
            total_frames = wf.getnframes()
            framerate = wf.getframerate()

            app_logger.info("Vosk", "开始转写")
            model = VoskModel(model_path=model_path)
            rec = KaldiRecognizer(model, framerate)
            rec.SetWords(True)

            segments: List[Segment] = []
            processed_frames = 0
            chunk = 4000

            while not cancel_event.is_set():
                data = wf.readframes(chunk)
                if not data:
                    break
                processed_frames += chunk
                pct = min(95.0, processed_frames / max(total_frames, 1) * 100)
                progress_cb(pct, "正在转写（Vosk）...")

                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    seg = VoskBackend._parse_result(result)
                    if seg:
                        segments.append(seg)

            if cancel_event.is_set():
                raise WorkerCancelled()

            # 最后一段
            final = json.loads(rec.FinalResult())
            seg = VoskBackend._parse_result(final)
            if seg:
                segments.append(seg)

            wf.close()
            app_logger.info("Vosk", f"转写完成 segments={len(segments)}")
            progress_cb(100.0, "Vosk 转写完成")
            return segments
        finally:
            cleanup_tmpdir(tmpdir)

    @staticmethod
    def _parse_result(result: dict) -> Optional[Segment]:
        """将单条 Vosk Result JSON 转换为 Segment。"""
        words = result.get("result", [])
        text = result.get("text", "").strip()
        if not text:
            return None
        if words:
            start = words[0].get("start", 0.0)
            end = words[-1].get("end", 0.0)
        else:
            start = end = 0.0
        return Segment(start=start, end=end, text=text)


class WhisperBackend:
    @staticmethod
    def transcribe(
        audio_path: str,
        model_size: str,
        language: str,
        progress_cb: Callable[[float, str], None],
        cancel_event: threading.Event,
    ) -> List[Segment]:
        """
        使用 openai-whisper 转写。
        Whisper 无中途进度回调，用假进度（加载模型 0→10%，转写中 10→90%）。
        """
        if not WHISPER_AVAILABLE:
            raise RuntimeError(
                "openai-whisper 未安装，请运行：pip install openai-whisper"
            )

        progress_cb(5.0, f"正在加载 Whisper 模型（{model_size}）...")
        app_logger.info("Whisper", f"开始转写 model={model_size}")

        # 在独立线程中执行，同时推进假进度
        result_holder: list = []
        error_holder: list = []

        def _do_transcribe():
            try:
                model = openai_whisper.load_model(model_size)
                if cancel_event.is_set():
                    return
                kwargs: dict = {"verbose": False}
                if language and language != "auto":
                    kwargs["language"] = language
                result = model.transcribe(audio_path, **kwargs)
                result_holder.append(result)
            except Exception as e:
                error_holder.append(e)

        t = threading.Thread(target=_do_transcribe, daemon=True)
        t.start()

        # 假进度推进
        pct = 10.0
        while t.is_alive():
            if cancel_event.is_set():
                t.join(timeout=2)
                raise WorkerCancelled()
            time.sleep(0.5)
            pct = min(88.0, pct + 1.5)
            progress_cb(pct, "正在转写（Whisper）...")

        t.join()

        if error_holder:
            raise error_holder[0]
        if not result_holder:
            raise RuntimeError("Whisper 转写未返回结果")

        result = result_holder[0]
        segments: List[Segment] = []
        for seg in result.get("segments", []):
            text = seg.get("text", "").strip()
            if text:
                segments.append(
                    Segment(
                        start=float(seg.get("start", 0.0)),
                        end=float(seg.get("end", 0.0)),
                        text=text,
                    )
                )

        progress_cb(100.0, "Whisper 转写完成")
        app_logger.info("Whisper", f"转写完成 segments={len(segments)}")
        return segments


class DoubaoASRBackend:
    SUBMIT_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
    QUERY_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"

    @staticmethod
    def _upload_r2(
        local_path: str,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        object_key: str,
    ) -> str:
        """上传文件到 Cloudflare R2，返回预签名 URL（有效期 3600s）。"""
        endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=BotoConfig(signature_version="s3v4"),
            region_name="auto",
        )
        client.upload_file(local_path, bucket, object_key)
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": object_key},
            ExpiresIn=3600,
        )
        return url

    @staticmethod
    def _delete_r2(
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        object_key: str,
    ) -> None:
        """删除 R2 上的临时文件（静默失败）。"""
        try:
            endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
            client = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                config=BotoConfig(signature_version="s3v4"),
                region_name="auto",
            )
            client.delete_object(Bucket=bucket, Key=object_key)
        except Exception:
            pass

    @staticmethod
    def _submit_task(
        audio_url: str,
        audio_fmt: str,
        language: str,
        app_id: str,
        token: str,
    ) -> tuple[str, str]:
        """提交豆包 ASR 任务，返回 (task_id, x_tt_logid)。"""
        task_id = str(uuid.uuid4())
        headers = {
            "X-Api-App-Key": app_id,
            "X-Api-Access-Key": token,
            "X-Api-Resource-Id": "volc.bigasr.auc",
            "X-Api-Request-Id": task_id,
            "X-Api-Sequence": "-1",
            "Content-Type": "application/json",
        }
        body: dict = {
            "user": {"uid": "speech_extractor"},
            "audio": {
                "url": audio_url,
                "format": audio_fmt,
            },
            "request": {
                "model_name": "bigmodel",
                "enable_punc": True,
                "enable_itn": True,
                "show_utterances": True,
            },
        }
        if language and language != "auto":
            body["audio"]["language"] = language

        resp = http_requests.post(
            DoubaoASRBackend.SUBMIT_URL,
            data=json.dumps(body),
            headers=headers,
            timeout=30,
        )
        status_code = resp.headers.get("X-Api-Status-Code", "")
        if status_code != "20000000":
            msg = resp.headers.get("X-Api-Message", "unknown")
            raise RuntimeError(f"豆包 ASR 提交失败（{status_code}）：{msg}")
        logid = resp.headers.get("X-Tt-Logid", "")
        return task_id, logid

    @staticmethod
    def _poll_task(
        task_id: str,
        logid: str,
        app_id: str,
        token: str,
        progress_cb: Callable[[float, str], None],
        cancel_event: threading.Event,
    ) -> dict:
        """轮询豆包 ASR 结果，成功后返回 response body dict。"""
        headers = {
            "X-Api-App-Key": app_id,
            "X-Api-Access-Key": token,
            "X-Api-Resource-Id": "volc.bigasr.auc",
            "X-Api-Request-Id": task_id,
            "X-Tt-Logid": logid,
            "Content-Type": "application/json",
        }
        elapsed = 0.0
        pct = 30.0
        attempt = 0
        while not cancel_event.is_set():
            resp = http_requests.post(
                DoubaoASRBackend.QUERY_URL,
                data=json.dumps({}),
                headers=headers,
                timeout=30,
            )
            code = resp.headers.get("X-Api-Status-Code", "")
            attempt += 1
            app_logger.debug("DoubaoASR", f"轮询 attempt={attempt} status_code={code}")
            if code == "20000000":
                return resp.json()
            elif code in ("20000001", "20000002"):
                elapsed += 2.0
                pct = min(85.0, 30.0 + elapsed * 0.5)
                status_msg = "队列中..." if code == "20000002" else "识别中..."
                progress_cb(pct, f"豆包 ASR {status_msg}")
                time.sleep(2)
            elif code == "20000003":
                raise RuntimeError("豆包 ASR：音频为静音，请检查文件")
            else:
                msg = resp.headers.get("X-Api-Message", "unknown")
                raise RuntimeError(f"豆包 ASR 查询失败（{code}）：{msg}")

        raise WorkerCancelled()

    @classmethod
    def transcribe(
        cls,
        audio_path: str,
        app_id: str,
        access_token: str,
        r2_account_id: str,
        r2_access_key_id: str,
        r2_secret_access_key: str,
        r2_bucket: str,
        language: str,
        progress_cb: Callable[[float, str], None],
        cancel_event: threading.Event,
    ) -> List[Segment]:
        if not DOUBAO_AVAILABLE:
            raise RuntimeError(
                "boto3/requests 未安装，请运行：pip install boto3 requests"
            )

        # 生成唯一对象键
        object_key = f"speech_extractor/{uuid.uuid4()}{Path(audio_path).suffix}"
        uploaded = False

        try:
            # 1. 上传到 R2
            progress_cb(10.0, "正在上传到 Cloudflare R2...")
            audio_fmt = detect_format(audio_path)
            _r2_size = Path(audio_path).stat().st_size
            _r2_fname = Path(audio_path).name
            app_logger.info("R2", f"上传开始 filename={_r2_fname} size={_r2_size}")
            _t0 = time.time()
            presigned_url = cls._upload_r2(
                audio_path,
                r2_account_id,
                r2_access_key_id,
                r2_secret_access_key,
                r2_bucket,
                object_key,
            )
            app_logger.info("R2", f"上传完成 elapsed={time.time()-_t0:.1f}s")
            uploaded = True

            if cancel_event.is_set():
                raise WorkerCancelled()

            # 2. 提交任务
            progress_cb(20.0, "正在提交豆包 ASR 任务...")
            task_id, logid = cls._submit_task(
                presigned_url, audio_fmt, language, app_id, access_token
            )
            app_logger.info("DoubaoASR", f"任务提交 task_id={task_id} app_id={app_id}")

            if cancel_event.is_set():
                raise WorkerCancelled()

            # 3. 轮询结果
            progress_cb(25.0, "豆包 ASR 识别中...")
            body = cls._poll_task(
                task_id, logid, app_id, access_token, progress_cb, cancel_event
            )

            # 4. 解析 utterances
            progress_cb(90.0, "正在解析识别结果...")
            segments: List[Segment] = []
            utterances = body.get("result", {}).get("utterances", [])
            for utt in utterances:
                text = utt.get("text", "").strip()
                if not text:
                    continue
                start_ms = utt.get("start_time", 0)
                end_ms = utt.get("end_time", 0)
                segments.append(
                    Segment(
                        start=start_ms / 1000.0,
                        end=end_ms / 1000.0,
                        text=text,
                    )
                )

            # 若无 utterances，尝试用整体 text（无时间戳）
            if not segments:
                full_text = body.get("result", {}).get("text", "").strip()
                if full_text:
                    segments.append(Segment(start=0.0, end=0.0, text=full_text))

            app_logger.info("DoubaoASR", f"识别完成 utterances={len(segments)}")
            progress_cb(100.0, "豆包 ASR 转写完成")
            return segments

        finally:
            # 保证删除 R2 临时文件
            if uploaded:
                cls._delete_r2(
                    r2_account_id,
                    r2_access_key_id,
                    r2_secret_access_key,
                    r2_bucket,
                    object_key,
                )
                app_logger.info("R2", "临时文件已删除")


# =============================================================================
# Section 5: 字幕后处理
# =============================================================================


class SubtitleProcessor:

    @staticmethod
    def _fmt_srt_time(seconds: float) -> str:
        """将秒数格式化为 SRT 时间戳 HH:MM:SS,mmm。"""
        ms = int(round(seconds * 1000))
        s, ms = divmod(ms, 1000)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    @staticmethod
    def to_srt(segments: List[Segment]) -> str:
        """生成标准 SRT 字幕文本。"""
        lines: List[str] = []
        for i, seg in enumerate(segments, 1):
            start = SubtitleProcessor._fmt_srt_time(seg.start)
            end = SubtitleProcessor._fmt_srt_time(seg.end)
            lines.append(str(i))
            lines.append(f"{start} --> {end}")
            lines.append(seg.text)
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def merge_paragraphs(segments: List[Segment], gap: float = 2.0) -> str:
        """
        将短句合并为段落：
        - 相邻 segment 停顿 <= gap 秒则拼接（中文无空格，英文加空格）
        - 停顿 > gap 秒则换行分段
        - 不修改任何词汇
        """
        if not segments:
            return ""

        paragraphs: List[str] = []
        current_parts: List[str] = [segments[0].text]
        prev_end = segments[0].end

        for seg in segments[1:]:
            gap_actual = seg.start - prev_end
            if gap_actual <= gap:
                # 合并：中文不加空格，英文加空格
                combined_so_far = "".join(current_parts)
                sep = "" if _is_mainly_chinese(combined_so_far + seg.text) else " "
                current_parts.append(sep + seg.text)
            else:
                paragraphs.append("".join(current_parts))
                current_parts = [seg.text]
            prev_end = seg.end

        if current_parts:
            paragraphs.append("".join(current_parts))

        return "\n\n".join(paragraphs)

    @staticmethod
    def polish_script(
        raw_text: str,
        llm_type: str,
        api_key: str,
        base_url: str,
        model: str,
        stream_cb: Callable[[str], None],
        cancel_event: threading.Event,
    ) -> str:
        """
        调用 LLM（豆包/OpenAI 兼容）将原始转写整理为口述稿。
        stream=True，每收到 token 调用 stream_cb。
        """
        if not LLM_AVAILABLE:
            raise RuntimeError("openai 未安装，请运行：pip install 'openai>=1.0'")

        client = OpenAI(api_key=api_key, base_url=base_url)

        system_prompt = "你是一个专业的文字整理助手。"
        user_prompt = (
            "以下是从音视频中提取的原始转写文字。"
            "请整理成一篇逻辑通顺的口述稿：保留核心内容，"
            "修正明显语病和口语化重复，不要添加原文没有的信息。\n\n"
            f"原文：\n{raw_text}"
        )

        app_logger.debug("LLM", f"model={model} base_url={base_url} prompt_chars={len(user_prompt)}")
        full_text = ""
        stream = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=True,
        )

        for chunk in stream:
            if cancel_event.is_set():
                break
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                full_text += delta.content
                stream_cb(delta.content)

        app_logger.info("LLM", f"polish_script 完成 chars={len(full_text)}")
        return full_text


# =============================================================================
# Section 6: Textual TUI
# =============================================================================

# ---------- 文件浏览 Modal ----------


class FileBrowserModal(ModalScreen[str]):
    """文件选择弹窗，使用 Textual 内置 DirectoryTree。"""

    CSS = """
    FileBrowserModal {
        align: center middle;
    }
    FileBrowserModal > Vertical {
        width: 70%;
        height: 70%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    FileBrowserModal DirectoryTree {
        height: 1fr;
    }
    FileBrowserModal #browser_path {
        height: 3;
        border: tall $accent;
        margin: 1 0;
    }
    FileBrowserModal .btn_row {
        height: 3;
        align: right middle;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("选择文件（双击或选中后点击确认）")
            yield DirectoryTree(str(Path.home()), id="dir_tree")
            yield Input(placeholder="文件路径...", id="browser_path")
            with Horizontal(classes="btn_row"):
                yield Button("确认", id="btn_confirm", variant="primary")
                yield Button("取消", id="btn_cancel")

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        self.query_one("#browser_path", Input).value = str(event.path)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_confirm":
            path = self.query_one("#browser_path", Input).value.strip()
            if path:
                self.dismiss(path)
            else:
                self.dismiss("")
        elif event.button.id == "btn_cancel":
            self.dismiss("")


# ---------- 设置 Tab ----------


class SettingsTab(TabPane):
    CSS = """
    SettingsTab {
        padding: 1 2;
    }
    SettingsTab .section_label {
        color: $accent;
        text-style: bold;
        margin-top: 1;
    }
    SettingsTab .field_row {
        height: 3;
        margin-bottom: 1;
        align: left middle;
    }
    SettingsTab .field_label {
        width: 20;
        text-align: right;
        padding-right: 1;
    }
    SettingsTab .field_input {
        width: 40;
    }
    SettingsTab .toggle_btn {
        width: 6;
        min-width: 6;
        margin-left: 1;
    }
    SettingsTab .action_row {
        height: 3;
        margin-top: 2;
        align: right middle;
    }
    """

    def compose(self) -> ComposeResult:
        with ScrollableContainer():
            # Vosk
            yield Label(
                "── Vosk 设置 ──────────────────────────────", classes="section_label"
            )
            with Horizontal(classes="field_row"):
                yield Label("模型路径:", classes="field_label")
                yield Input(
                    id="cfg_vosk_model_path",
                    classes="field_input",
                    placeholder="models/vosk-model-small-cn-0.22",
                )

            # 豆包 ASR
            yield Label(
                "── 豆包 ASR 设置 ───────────────────────────", classes="section_label"
            )
            with Horizontal(classes="field_row"):
                yield Label("App ID:", classes="field_label")
                yield Input(
                    id="cfg_doubao_app_id",
                    classes="field_input",
                    placeholder="控制台获取的 APP ID",
                )
            with Horizontal(classes="field_row"):
                yield Label("Access Token:", classes="field_label")
                yield Input(
                    id="cfg_doubao_token",
                    password=True,
                    classes="field_input",
                    placeholder="控制台获取的 Access Token",
                )
                yield Button("显示", id="toggle_doubao_token", classes="toggle_btn")

            # Cloudflare R2
            yield Label(
                "── Cloudflare R2 设置 ──────────────────────", classes="section_label"
            )
            with Horizontal(classes="field_row"):
                yield Label("Account ID:", classes="field_label")
                yield Input(
                    id="cfg_r2_account_id",
                    classes="field_input",
                    placeholder="Cloudflare Account ID",
                )
            with Horizontal(classes="field_row"):
                yield Label("Access Key ID:", classes="field_label")
                yield Input(
                    id="cfg_r2_access_key_id",
                    classes="field_input",
                    placeholder="R2 Access Key ID",
                )
            with Horizontal(classes="field_row"):
                yield Label("Secret Access Key:", classes="field_label")
                yield Input(
                    id="cfg_r2_secret_key",
                    password=True,
                    classes="field_input",
                    placeholder="R2 Secret Access Key",
                )
                yield Button("显示", id="toggle_r2_secret", classes="toggle_btn")
            with Horizontal(classes="field_row"):
                yield Label("Bucket 名称:", classes="field_label")
                yield Input(
                    id="cfg_r2_bucket", classes="field_input", placeholder="bucket-name"
                )

            # LLM
            yield Label(
                "── LLM 设置 ────────────────────────────────", classes="section_label"
            )
            with Horizontal(classes="field_row"):
                yield Label("LLM 类型:", classes="field_label")
                with RadioSet(id="cfg_llm_type"):
                    yield RadioButton("豆包 LLM", id="llm_doubao", value=True)
                    yield RadioButton("OpenAI 兼容", id="llm_openai")
            with Horizontal(classes="field_row"):
                yield Label("API Key:", classes="field_label")
                yield Input(
                    id="cfg_llm_api_key",
                    password=True,
                    classes="field_input",
                    placeholder="API Key",
                )
                yield Button("显示", id="toggle_llm_key", classes="toggle_btn")
            with Horizontal(classes="field_row"):
                yield Label("Base URL:", classes="field_label")
                yield Input(
                    id="cfg_llm_base_url",
                    classes="field_input",
                    placeholder="https://ark.cn-beijing.volces.com/api/v3",
                )
            with Horizontal(classes="field_row"):
                yield Label("Model ID:", classes="field_label")
                yield Input(
                    id="cfg_llm_model",
                    classes="field_input",
                    placeholder="doubao-seed-1-6-flash-250615",
                )

            with Horizontal(classes="action_row"):
                yield Button("测试 ASR 连接", id="btn_test_asr", variant="default")
                yield Button("保存设置", id="btn_save_settings", variant="primary")

    def on_mount(self) -> None:
        self._load_values()

    def _load_values(self) -> None:
        cfg = load_config()
        self.query_one("#cfg_vosk_model_path", Input).value = cfg.get(
            "vosk_model_path", ""
        )
        self.query_one("#cfg_doubao_app_id", Input).value = get_secret(
            "doubao_asr_app_id"
        )
        self.query_one("#cfg_doubao_token", Input).value = get_secret(
            "doubao_asr_access_token"
        )
        self.query_one("#cfg_r2_account_id", Input).value = cfg.get("r2_account_id", "")
        self.query_one("#cfg_r2_access_key_id", Input).value = get_secret(
            "r2_access_key_id"
        )
        self.query_one("#cfg_r2_secret_key", Input).value = get_secret(
            "r2_secret_access_key"
        )
        self.query_one("#cfg_r2_bucket", Input).value = cfg.get("r2_bucket", "")
        llm_type = cfg.get("llm_type", "doubao")
        if llm_type == "openai":
            self.query_one("#llm_openai", RadioButton).value = True
        llm_key = (
            get_secret("doubao_llm_api_key")
            if llm_type == "doubao"
            else get_secret("openai_api_key")
        )
        self.query_one("#cfg_llm_api_key", Input).value = llm_key
        self.query_one("#cfg_llm_base_url", Input).value = cfg.get("llm_base_url", "")
        self.query_one("#cfg_llm_model", Input).value = cfg.get("llm_model", "")

    def _save_values(self) -> None:
        cfg = load_config()
        cfg["vosk_model_path"] = self.query_one(
            "#cfg_vosk_model_path", Input
        ).value.strip()
        cfg["r2_account_id"] = self.query_one("#cfg_r2_account_id", Input).value.strip()
        cfg["r2_bucket"] = self.query_one("#cfg_r2_bucket", Input).value.strip()
        # LLM type
        llm_set = self.query_one("#cfg_llm_type", RadioSet)
        llm_type = (
            "openai"
            if (llm_set.pressed_button and llm_set.pressed_button.id == "llm_openai")
            else "doubao"
        )
        cfg["llm_type"] = llm_type
        cfg["llm_base_url"] = self.query_one("#cfg_llm_base_url", Input).value.strip()
        cfg["llm_model"] = self.query_one("#cfg_llm_model", Input).value.strip()
        save_config(cfg)

        # 密钥写入 keyring
        set_secret(
            "doubao_asr_app_id",
            self.query_one("#cfg_doubao_app_id", Input).value.strip(),
        )
        set_secret(
            "doubao_asr_access_token",
            self.query_one("#cfg_doubao_token", Input).value.strip(),
        )
        set_secret(
            "r2_access_key_id",
            self.query_one("#cfg_r2_access_key_id", Input).value.strip(),
        )
        set_secret(
            "r2_secret_access_key",
            self.query_one("#cfg_r2_secret_key", Input).value.strip(),
        )
        llm_key = self.query_one("#cfg_llm_api_key", Input).value.strip()
        if llm_type == "doubao":
            set_secret("doubao_llm_api_key", llm_key)
        else:
            set_secret("openai_api_key", llm_key)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id

        # 密码显示/隐藏切换
        toggle_map = {
            "toggle_doubao_token": "#cfg_doubao_token",
            "toggle_r2_secret": "#cfg_r2_secret_key",
            "toggle_llm_key": "#cfg_llm_api_key",
        }
        if btn_id in toggle_map:
            inp = self.query_one(toggle_map[btn_id], Input)
            inp.password = not inp.password
            event.button.label = "隐藏" if not inp.password else "显示"
            return

        if btn_id == "btn_save_settings":
            self._save_values()
            self.app.notify("设置已保存", severity="information")

        elif btn_id == "btn_test_asr":
            self._save_values()
            self.app.notify("正在测试 R2 连接...", severity="information")
            self.run_worker(self._test_asr_connection, thread=True, exclusive=True)

    def _test_asr_connection(self) -> None:
        """测试 R2 上传是否可用（上传一个微小的测试文件后立即删除）。"""
        cfg = load_config()
        account_id = cfg.get("r2_account_id", "")
        bucket = cfg.get("r2_bucket", "")
        access_key_id = get_secret("r2_access_key_id")
        secret_key = get_secret("r2_secret_access_key")

        if not all([account_id, bucket, access_key_id, secret_key]):
            self.app.call_from_thread(
                self.app.notify, "R2 配置不完整，请先填写全部 R2 字段", severity="error"
            )
            return

        try:
            import io

            object_key = f"speech_extractor_test/{uuid.uuid4()}.txt"
            endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
            client = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_key,
                config=BotoConfig(signature_version="s3v4"),
                region_name="auto",
            )
            client.put_object(Bucket=bucket, Key=object_key, Body=b"test")
            client.delete_object(Bucket=bucket, Key=object_key)
            self.app.call_from_thread(
                self.app.notify, "R2 连接测试成功！", severity="information"
            )
        except Exception as e:
            self.app.call_from_thread(
                self.app.notify, f"R2 连接测试失败：{e}", severity="error"
            )


# ---------- 识别 Tab ----------

WHISPER_SIZES = ["tiny", "base", "small", "medium", "large"]
WHISPER_LANGUAGES = [
    ("zh", "中文"),
    ("en", "英语"),
    ("ja", "日语"),
    ("ko", "韩语"),
    ("de", "德语"),
    ("fr", "法语"),
    ("es", "西班牙语"),
    ("ru", "俄语"),
    ("auto", "自动检测"),
]
DOUBAO_LANGUAGES = [
    ("", "自动（中英文/方言）"),
    ("zh-CN", "中文普通话"),
    ("en-US", "英语"),
    ("ja-JP", "日语"),
    ("ko-KR", "韩语"),
    ("de-DE", "德语"),
    ("fr-FR", "法语"),
    ("es-MX", "西班牙语"),
    ("ru-RU", "俄语"),
    ("yue-CN", "粤语"),
]


class RecognizeTab(TabPane):
    CSS = """
    RecognizeTab {
        padding: 1 2;
    }
    RecognizeTab .section_label {
        color: $accent;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 0;
    }
    RecognizeTab .file_row {
        height: 3;
        align: left middle;
        margin-bottom: 1;
    }
    RecognizeTab #input_file {
        width: 1fr;
    }
    RecognizeTab #btn_browse {
        width: 8;
        min-width: 8;
        margin-left: 1;
    }
    RecognizeTab .engine_modes_row {
        height: auto;
        margin-bottom: 1;
    }
    RecognizeTab .engine_box {
        width: 1fr;
        border: round $panel;
        padding: 0 1;
    }
    RecognizeTab .mode_box {
        width: 1fr;
        border: round $panel;
        padding: 0 1;
        margin-left: 2;
    }
    RecognizeTab #engine_options {
        height: auto;
        margin-bottom: 1;
    }
    RecognizeTab .options_row {
        height: 3;
        align: left middle;
    }
    RecognizeTab .options_label {
        width: 14;
        text-align: right;
        padding-right: 1;
    }
    RecognizeTab .options_select {
        width: 24;
    }
    RecognizeTab .output_row {
        height: 3;
        align: left middle;
        margin-bottom: 1;
    }
    RecognizeTab #input_output {
        width: 1fr;
    }
    RecognizeTab .control_row {
        height: 3;
        align: right middle;
        margin-bottom: 1;
    }
    RecognizeTab #btn_start {
        min-width: 12;
        margin-left: 1;
    }
    RecognizeTab #btn_cancel_run {
        min-width: 8;
        margin-left: 1;
    }
    RecognizeTab #progress_bar {
        margin-bottom: 0;
    }
    RecognizeTab #status_label {
        height: 1;
        color: $text-muted;
        margin-bottom: 1;
    }
    RecognizeTab .preview_header {
        height: 3;
        align: left middle;
    }
    RecognizeTab .preview_label {
        width: 1fr;
        text-style: bold;
        color: $accent;
    }
    RecognizeTab #btn_copy {
        min-width: 8;
        margin-left: 1;
    }
    RecognizeTab #btn_save_output {
        min-width: 8;
        margin-left: 1;
    }
    RecognizeTab #preview_area {
        height: 1fr;
        border: round $panel;
    }
    RecognizeTab #subtitle_mode_notice {
        color: $success;
        text-style: bold;
        padding: 1;
        display: none;
    }
    RecognizeTab #subtitle_options {
        height: auto;
        margin-bottom: 1;
        display: none;
    }
    RecognizeTab #subtitle_options .options_row {
        height: 3;
        align: left middle;
    }
    RecognizeTab #lang_select_row {
        display: none;
    }
    RecognizeTab #polish_hint_row {
        height: 3;
        align: left middle;
        margin-bottom: 0;
        display: none;
    }
    RecognizeTab #complexity_hint {
        width: 1fr;
        color: $text-muted;
    }
    RecognizeTab #complexity_hint.suggest {
        color: $warning;
        text-style: bold;
    }
    RecognizeTab #btn_llm_refine {
        min-width: 14;
        margin-left: 1;
    }
    """

    def compose(self) -> ComposeResult:
        # 输入文件
        yield Label("输入文件", classes="section_label")
        with Horizontal(classes="file_row"):
            yield Input(id="input_file", placeholder="选择或拖入音视频 / 字幕文件...")
            yield Button("浏览", id="btn_browse")

        # 引擎 + 后处理模式
        yield Label("识别引擎 / 后处理模式", classes="section_label")
        with Horizontal(classes="engine_modes_row"):
            with Vertical(classes="engine_box"):
                # 字幕文件模式提示（正常情况下隐藏）
                yield Label("字幕文件模式\n（跳过 ASR，直接后处理）", id="subtitle_mode_notice")
                with RadioSet(id="engine_set"):
                    yield RadioButton(
                        f"Vosk（本地）{'  ✓' if VOSK_AVAILABLE else '  [未安装]'}",
                        id="engine_vosk",
                        disabled=not VOSK_AVAILABLE,
                    )
                    yield RadioButton(
                        f"Whisper（本地）{'  ✓' if WHISPER_AVAILABLE else '  [未安装]'}",
                        id="engine_whisper",
                        value=WHISPER_AVAILABLE,
                        disabled=not WHISPER_AVAILABLE,
                    )
                    yield RadioButton(
                        f"豆包 ASR（云端）{'  ✓' if DOUBAO_AVAILABLE else '  [未安装]'}",
                        id="engine_doubao",
                        disabled=not DOUBAO_AVAILABLE,
                    )
            with Vertical(classes="mode_box"):
                with RadioSet(id="mode_set"):
                    yield RadioButton("带时间轴字幕（SRT）", id="mode_srt", value=True)
                    yield RadioButton("合并段落（纯文本）", id="mode_merge")
                    yield RadioButton(
                        f"整理口述稿（需 LLM）{'  ✓' if LLM_AVAILABLE else '  [未安装]'}",
                        id="mode_polish",
                        disabled=not LLM_AVAILABLE,
                    )

        # 引擎动态选项
        with Vertical(id="engine_options"):
            yield Label("引擎选项", classes="section_label")
            with Horizontal(classes="options_row", id="whisper_options"):
                yield Label("模型大小:", classes="options_label")
                yield Select(
                    [(s, s) for s in WHISPER_SIZES],
                    value="small",
                    id="sel_whisper_size",
                    classes="options_select",
                )
                yield Label("  语言:", classes="options_label")
                yield Select(
                    [(f"{code} — {name}", code) for code, name in WHISPER_LANGUAGES],
                    value="zh",
                    id="sel_whisper_lang",
                    classes="options_select",
                )
            with Horizontal(classes="options_row", id="vosk_options"):
                yield Label("模型路径:", classes="options_label")
                yield Input(
                    id="vosk_model_input",
                    placeholder="models/vosk-model-small-cn-0.22",
                    classes="options_select",
                )
            with Horizontal(classes="options_row", id="doubao_options"):
                yield Label("语言:", classes="options_label")
                yield Select(
                    [(name, code) for code, name in DOUBAO_LANGUAGES],
                    value="",
                    id="sel_doubao_lang",
                    classes="options_select",
                )

        # 字幕文件专用选项（字幕模式下替代引擎选项显示）
        with Vertical(id="subtitle_options"):
            yield Label("字幕选项", classes="section_label")
            with Horizontal(classes="options_row", id="lang_select_row"):
                yield Label("保留语言:", classes="options_label")
                yield Select(
                    [("中文", "zh"), ("英文", "en"), ("双语保留", "both")],
                    value="zh",
                    id="sel_keep_lang",
                    classes="options_select",
                )

        # 输出文件
        yield Label("输出文件", classes="section_label")
        with Horizontal(classes="output_row"):
            yield Input(id="input_output", placeholder="speeches/output.srt")

        # 控制按钮
        with Horizontal(classes="control_row"):
            yield Button("开始识别", id="btn_start", variant="primary")
            yield Button("取消", id="btn_cancel_run", variant="error")

        # 进度
        yield ProgressBar(id="progress_bar", total=100, show_eta=False)
        yield Label("", id="status_label")

        # LLM 精修提示行（合并段落完成后显示）
        with Horizontal(id="polish_hint_row"):
            yield Label("", id="complexity_hint")
            yield Button(
                f"LLM 精修{'  ✓' if LLM_AVAILABLE else '  [未安装]'}",
                id="btn_llm_refine",
                variant="warning",
                disabled=not LLM_AVAILABLE,
            )

        # 预览
        with Horizontal(classes="preview_header"):
            yield Label("输出预览", classes="preview_label")
            yield Button("复制", id="btn_copy")
            yield Button("保存", id="btn_save_output")
        yield TextArea(id="preview_area", read_only=True)

    def on_mount(self) -> None:
        cfg = load_config()
        # 加载配置到输入框
        self.query_one("#vosk_model_input", Input).value = cfg.get(
            "vosk_model_path", ""
        )
        # 默认引擎选择
        engine = cfg.get("default_engine", "whisper")
        engine_map = {
            "vosk": "engine_vosk",
            "whisper": "engine_whisper",
            "doubao": "engine_doubao",
        }
        btn_id = engine_map.get(engine, "engine_whisper")
        try:
            btn = self.query_one(f"#{btn_id}", RadioButton)
            if not btn.disabled:
                btn.value = True
        except Exception:
            pass
        # 初始化引擎选项可见性
        self._update_engine_options()
        # 取消按钮初始禁用
        self.query_one("#btn_cancel_run", Button).disabled = True

    def _update_engine_options(self) -> None:
        """根据当前选中引擎显示/隐藏对应选项行。"""
        engine = self._get_selected_engine()
        self.query_one("#whisper_options").display = engine == "whisper"
        self.query_one("#vosk_options").display = engine == "vosk"
        self.query_one("#doubao_options").display = engine == "doubao"

    def _update_subtitle_mode(self, is_subtitle: bool, input_path: str = "") -> None:
        """
        当输入文件是字幕文件时切换 UI：
        - 隐藏引擎 RadioSet + 引擎选项，显示字幕模式提示 + 字幕选项
        - 禁用「SRT」输出模式，若已选中则自动切换到「合并段落」
        - 字幕模式下检测双语，决定是否显示「保留语言」下拉框
        """
        engine_set = self.query_one("#engine_set", RadioSet)
        notice = self.query_one("#subtitle_mode_notice", Label)
        engine_options = self.query_one("#engine_options")
        subtitle_options = self.query_one("#subtitle_options")
        lang_select_row = self.query_one("#lang_select_row")
        srt_btn = self.query_one("#mode_srt", RadioButton)
        polish_hint_row = self.query_one("#polish_hint_row")

        if is_subtitle:
            engine_set.display = False
            notice.display = True
            engine_options.display = False
            subtitle_options.display = True
            srt_btn.disabled = True
            polish_hint_row.display = False  # 每次切换文件时隐藏，等处理完再显示
            # 若当前是 SRT 模式，自动切换到合并段落
            if self._get_selected_mode() == "srt":
                self.query_one("#mode_merge", RadioButton).value = True
            # 双语检测：若有文件路径则尝试解析
            show_lang = False
            if input_path:
                try:
                    lines = SubtitleFileParser.parse(input_path)
                    is_bilingual, recommend = detect_bilingual(lines)
                    if is_bilingual:
                        show_lang = True
                        # 自动设置推荐语言
                        sel = self.query_one("#sel_keep_lang", Select)
                        sel.value = recommend
                except Exception:
                    pass
            lang_select_row.display = show_lang
        else:
            engine_set.display = True
            notice.display = False
            engine_options.display = True
            subtitle_options.display = False
            lang_select_row.display = False
            srt_btn.disabled = False
            polish_hint_row.display = False
            self._update_engine_options()

    def _get_selected_engine(self) -> str:
        rs = self.query_one("#engine_set", RadioSet)
        if rs.pressed_button:
            bid = rs.pressed_button.id
            if bid == "engine_vosk":
                return "vosk"
            if bid == "engine_doubao":
                return "doubao"
        return "whisper"

    def _get_selected_mode(self) -> str:
        rs = self.query_one("#mode_set", RadioSet)
        if rs.pressed_button:
            bid = rs.pressed_button.id
            if bid == "mode_merge":
                return "merge"
            if bid == "mode_polish":
                return "polish"
        return "srt"

    def _auto_output_path(self, input_path: str, mode: str) -> str:
        cfg = load_config()
        out_dir = cfg.get("output_dir", "speeches")
        stem = Path(input_path).stem
        suffix_map = {"srt": ".srt", "merge": ".txt", "polish": ".txt"}
        mode_suffix_map = {"srt": "_srt", "merge": "_merged", "polish": "_script"}
        fname = f"{stem}{mode_suffix_map[mode]}{suffix_map[mode]}"
        return str(Path(out_dir) / fname)

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        if event.radio_set.id == "engine_set":
            self._update_engine_options()
            # 更新输出文件名后缀
            inp = self.query_one("#input_file", Input).value.strip()
            if inp:
                mode = self._get_selected_mode()
                self.query_one("#input_output", Input).value = self._auto_output_path(
                    inp, mode
                )
        elif event.radio_set.id == "mode_set":
            inp = self.query_one("#input_file", Input).value.strip()
            if inp:
                mode = self._get_selected_mode()
                self.query_one("#input_output", Input).value = self._auto_output_path(
                    inp, mode
                )

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "input_file":
            val = event.value.strip()
            if val and Path(val).exists():
                # 检测字幕文件并切换 UI 模式
                subtitle = is_subtitle_file(val)
                self._update_subtitle_mode(subtitle, val)
                mode = self._get_selected_mode()
                self.query_one("#input_output", Input).value = self._auto_output_path(
                    val, mode
                )
            else:
                # 文件路径不存在或已清空，恢复正常模式
                self._update_subtitle_mode(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id

        if btn_id == "btn_browse":
            self.app.push_screen(FileBrowserModal(), self._on_file_selected)

        elif btn_id == "btn_start":
            self._start_transcribe()

        elif btn_id == "btn_cancel_run":
            self._do_cancel()

        elif btn_id == "btn_copy":
            content = self.query_one("#preview_area", TextArea).text
            if content:
                import subprocess

                try:
                    if sys.platform == "win32":
                        subprocess.run(
                            ["clip"], input=content.encode("utf-16"), check=True
                        )
                    elif sys.platform == "darwin":
                        subprocess.run(
                            ["pbcopy"], input=content.encode("utf-8"), check=True
                        )
                    else:
                        subprocess.run(
                            ["xclip", "-selection", "clipboard"],
                            input=content.encode("utf-8"),
                            check=True,
                        )
                    self.app.notify("已复制到剪贴板", severity="information")
                except Exception as e:
                    self.app.notify(f"复制失败：{e}", severity="warning")

        elif btn_id == "btn_save_output":
            out_path = self.query_one("#input_output", Input).value.strip()
            content = self.query_one("#preview_area", TextArea).text
            if out_path and content:
                try:
                    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
                    Path(out_path).write_text(content, encoding="utf-8")
                    self.app.notify(f"已保存到 {out_path}", severity="information")
                except Exception as e:
                    self.app.notify(f"保存失败：{e}", severity="error")

        elif btn_id == "btn_llm_refine":
            self._do_llm_refine()

    def _on_file_selected(self, path: str) -> None:
        if path:
            self.query_one("#input_file", Input).value = path
            subtitle = is_subtitle_file(path)
            self._update_subtitle_mode(subtitle, path)
            mode = self._get_selected_mode()
            self.query_one("#input_output", Input).value = self._auto_output_path(
                path, mode
            )

    def _start_transcribe(self) -> None:
        """验证输入并启动后台 Worker。"""
        input_path = self.query_one("#input_file", Input).value.strip()
        if not input_path:
            self.app.notify("请先选择输入文件", severity="warning")
            return
        if not Path(input_path).exists():
            self.app.notify(f"文件不存在：{input_path}", severity="error")
            return

        output_path = self.query_one("#input_output", Input).value.strip()
        if not output_path:
            self.app.notify("请指定输出文件路径", severity="warning")
            return

        engine = self._get_selected_engine()
        mode = self._get_selected_mode()

        # 可用性再次检查（字幕文件不需要 ASR 引擎，跳过引擎检查）
        if not is_subtitle_file(input_path):
            if engine == "vosk" and not VOSK_AVAILABLE:
                self.app.notify("Vosk 未安装：pip install vosk", severity="error")
                return
            if engine == "whisper" and not WHISPER_AVAILABLE:
                self.app.notify(
                    "openai-whisper 未安装：pip install openai-whisper", severity="error"
                )
                return
            if engine == "doubao" and not DOUBAO_AVAILABLE:
                self.app.notify(
                    "boto3/requests 未安装：pip install boto3 requests", severity="error"
                )
                return
        if mode == "polish" and not LLM_AVAILABLE:
            self.app.notify(
                "openai 未安装：pip install 'openai>=1.0'", severity="error"
            )
            return

        # 重置 UI 状态
        self._cancel_event = threading.Event()
        self.query_one("#preview_area", TextArea).load_text("")
        self.query_one(ProgressBar).update(progress=0)
        self.query_one("#status_label", Label).update("准备中...")
        self.query_one("#btn_start", Button).disabled = True
        self.query_one("#btn_cancel_run", Button).disabled = False

        self.run_worker(
            self._run_transcribe,
            thread=True,
            exclusive=True,
            name="transcribe_worker",
        )

    def _do_cancel(self) -> None:
        if hasattr(self, "_cancel_event"):
            self._cancel_event.set()
        self.app.notify("正在取消...", severity="warning")

    def _update_progress(self, pct: float, msg: str) -> None:
        """线程安全的进度更新（由 call_from_thread 调用）。"""
        self.query_one(ProgressBar).update(progress=int(pct))
        self.query_one("#status_label", Label).update(msg)

    def _update_status_only(self, msg: str) -> None:
        """只更新状态标签，不碰 ProgressBar（indeterminate 模式下使用）。"""
        self.query_one("#status_label", Label).update(msg)

    def _append_preview(self, text: str) -> None:
        """线程安全地追加预览内容（LLM 流式输出使用）。"""
        ta = self.query_one("#preview_area", TextArea)
        ta.move_cursor(ta.document.end)
        ta.insert(text)

    def _set_preview(self, text: str) -> None:
        self.query_one("#preview_area", TextArea).load_text(text)

    def _finish_ui(self, output_path: str, succeeded: bool) -> None:
        self.query_one("#btn_start", Button).disabled = False
        self.query_one("#btn_cancel_run", Button).disabled = True
        if succeeded:
            self.query_one(ProgressBar).update(progress=100)
            self.app.notify(f"完成！已保存到 {output_path}", severity="information")
        else:
            self.query_one("#status_label", Label).update("已取消或发生错误")

    def _show_polish_hint(self, hint: str, score: float) -> None:
        """主线程：更新复杂度提示并显示 LLM 精修行。"""
        lbl = self.query_one("#complexity_hint", Label)
        lbl.update(hint)
        if score >= 0.5:
            lbl.add_class("suggest")
        else:
            lbl.remove_class("suggest")
        self.query_one("#polish_hint_row").display = True

    def _do_llm_refine(self) -> None:
        """触发 LLM 精修（在 Worker 线程中运行）。"""
        if not LLM_AVAILABLE:
            self.app.notify("openai 未安装：pip install 'openai>=1.0'", severity="error")
            return

        raw_text = self.query_one("#preview_area", TextArea).text
        if not raw_text.strip():
            self.app.notify("预览区内容为空，无法精修", severity="warning")
            return

        output_path = self.query_one("#input_output", Input).value.strip()

        # 禁用精修按钮，切换进度条为不定模式
        self.query_one("#btn_llm_refine", Button).disabled = True
        self.query_one("#complexity_hint", Label).update("正在连接 LLM，请稍候...")
        pb = self.query_one(ProgressBar)
        pb.update(total=None)  # indeterminate

        def _do_refine_worker() -> None:
            cfg = load_config()
            _succeeded = False
            llm_type = cfg.get("llm_type", "doubao")
            if llm_type == "doubao":
                api_key = get_secret("doubao_llm_api_key")
            else:
                api_key = get_secret("openai_api_key")
            base_url = cfg.get("llm_base_url", "")
            model = cfg.get("llm_model", "")

            if not api_key:
                self.app.call_from_thread(
                    lambda: self.app.notify(
                        "LLM API Key 未配置，请在「设置」Tab 中填写", severity="error"
                    )
                )
                self.app.call_from_thread(
                    lambda: self.query_one("#btn_llm_refine", Button).__setattr__(
                        "disabled", False
                    )
                )
                self.app.call_from_thread(
                    lambda: self.query_one(ProgressBar).update(total=100, progress=0)
                )
                return

            try:
                from openai import OpenAI as _OpenAI  # type: ignore

                client = _OpenAI(api_key=api_key, base_url=base_url or None)
                self.app.call_from_thread(self._set_preview, "")
                self.app.call_from_thread(
                    self._update_status_only, "正在向 LLM 发送请求..."
                )

                system_prompt = "你是一个专业的文字整理助手。"
                user_prompt = (
                    "以下是从字幕文件提取并经过初步整理的文字。"
                    "请将其合并为自然段落：保持原文语言和措辞完全不变，"
                    "不要翻译、不要增删内容，只合并属于同一语义单元的短句，"
                    "并在自然停顿处分段。\n\n原文：\n" + raw_text
                )

                app_logger.debug("LLM", f"model={model} base_url={base_url} prompt_chars={len(user_prompt)}")
                refined_text = ""
                buffer = ""
                token_count = 0
                _first_token_logged = False

                with client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    stream=True,
                ) as stream:
                    for chunk in stream:
                        token = chunk.choices[0].delta.content or ""
                        if token:
                            if not _first_token_logged:
                                app_logger.debug("LLM", "收到首个 token，开始流式接收")
                                _first_token_logged = True
                            refined_text += token
                            buffer += token
                            token_count += 1
                            # 每积累 8 个 token 才刷新一次 UI，减少渲染压力
                            if len(buffer) >= 8:
                                _buf = buffer
                                buffer = ""
                                self.app.call_from_thread(self._append_preview, _buf)
                            # 每 20 个 token 更新一次状态标签
                            if token_count % 20 == 0:
                                _n = token_count
                                self.app.call_from_thread(
                                    self._update_status_only,
                                    f"LLM 精修中... 已生成 {_n} 个词",
                                )

                # 冲刷剩余缓冲
                if buffer:
                    self.app.call_from_thread(self._append_preview, buffer)

                self.app.call_from_thread(
                    self._update_status_only, f"LLM 精修完成，共 {token_count} 个词"
                )
                app_logger.info("LLM", f"精修完成 token_count={token_count}")

                # 保存精修结果
                if output_path and refined_text:
                    try:
                        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                        Path(output_path).write_text(refined_text, encoding="utf-8")
                        self.app.call_from_thread(
                            lambda: self.app.notify(
                                f"精修结果已保存到 {output_path}",
                                severity="information",
                            )
                        )
                    except Exception as save_err:
                        self.app.call_from_thread(
                            lambda: self.app.notify(
                                f"保存失败：{save_err}", severity="warning"
                            )
                        )

                self.app.call_from_thread(self._show_polish_hint, "LLM 精修完成", 0.0)
                _succeeded = True

            except Exception as e:
                _succeeded = False
                _err = str(e)
                app_logger.error("LLM", _err)
                self.app.call_from_thread(
                    lambda: self.app.notify(f"LLM 精修失败：{_err}", severity="error")
                )
                self.app.call_from_thread(
                    self._update_status_only, f"LLM 精修失败：{_err}"
                )
            finally:
                # 先恢复进度条为确定模式，再设置最终进度值
                def _restore_pb() -> None:
                    pb = self.query_one(ProgressBar)
                    pb.update(total=100)
                    pb.update(progress=100 if _succeeded else 0)
                    self.query_one("#btn_llm_refine", Button).disabled = False

                self.app.call_from_thread(_restore_pb)

        self.run_worker(_do_refine_worker, thread=True, name="llm_refine_worker")

    def _run_transcribe(self) -> None:
        """在 Worker 线程中执行完整转写流程。"""
        cancel_event = self._cancel_event
        input_path = self.query_one("#input_file", Input).value.strip()
        output_path = self.query_one("#input_output", Input).value.strip()
        engine = self._get_selected_engine()
        mode = self._get_selected_mode()
        cfg = load_config()

        app_logger.info("App", f"开始识别 engine={engine} mode={mode}")
        tmpdir = ""
        try:

            def progress_cb(pct: float, msg: str) -> None:
                self.app.call_from_thread(self._update_progress, pct, msg)

            # ---- 字幕文件直通路径（跳过 ASR）----
            if is_subtitle_file(input_path):
                progress_cb(10.0, "正在解析字幕文件...")
                text_lines = SubtitleFileParser.parse(input_path)
                if not text_lines:
                    raise RuntimeError("字幕文件解析结果为空，请检查文件格式")

                progress_cb(50.0, "字幕解析完成，正在后处理...")

                if cancel_event.is_set():
                    raise WorkerCancelled()

                # 字幕文件模式下只支持 merge / polish
                if mode == "merge":
                    # 双语检测 + 语言过滤
                    is_bilingual, recommended_lang = detect_bilingual(text_lines)
                    if is_bilingual:
                        _raw_keep = self.query_one("#sel_keep_lang", Select).value
                        keep_lang: str = recommended_lang if _raw_keep == Select.BLANK else str(_raw_keep)
                        filtered_lines = filter_by_language(text_lines, keep_lang)
                    else:
                        filtered_lines = text_lines

                    # 将过滤后的行合并为段落
                    joined = ""
                    for line in filtered_lines:
                        if not joined:
                            joined = line
                        else:
                            sep = "" if _line_is_mainly_chinese(line) else " "
                            joined += sep + line

                    output_text = joined

                    # 复杂度评分 + 精修提示
                    score, hint = assess_merge_complexity(output_text)
                    self.app.call_from_thread(self._show_polish_hint, hint, score)
                    self.app.call_from_thread(self._set_preview, output_text)

                elif mode == "polish":
                    progress_cb(60.0, "正在调用 LLM 整理口述稿（流式输出）...")
                    self.app.call_from_thread(self._set_preview, "")

                    # 先将所有行拼成原始文本供 LLM 处理
                    sep_all = "" if _is_mainly_chinese("".join(text_lines)) else " "
                    raw_text = sep_all.join(text_lines)

                    llm_type = cfg.get("llm_type", "doubao")
                    if llm_type == "doubao":
                        api_key = get_secret("doubao_llm_api_key")
                    else:
                        api_key = get_secret("openai_api_key")
                    base_url = cfg.get("llm_base_url", "")
                    model = cfg.get("llm_model", "")

                    if not api_key:
                        raise RuntimeError("LLM API Key 未配置，请在「设置」Tab 中填写")

                    def stream_cb_sub(token: str) -> None:
                        self.app.call_from_thread(self._append_preview, token)

                    output_text = SubtitleProcessor.polish_script(
                        raw_text,
                        llm_type,
                        api_key,
                        base_url,
                        model,
                        stream_cb_sub,
                        cancel_event,
                    )
                else:
                    # SRT 模式对字幕文件输入无意义（UI 已禁用，但防御性处理）
                    raise RuntimeError(
                        "字幕文件输入不支持 SRT 输出模式，请选择「合并段落」或「整理口述稿」"
                    )

                if cancel_event.is_set():
                    raise WorkerCancelled()

                # 写文件
                progress_cb(99.0, "正在写入输出文件...")
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_path).write_text(output_text, encoding="utf-8")
                progress_cb(100.0, f"完成！→ {output_path}")
                self.app.call_from_thread(self._finish_ui, output_path, True)
                return

            # ---- 音频预处理 ----
            progress_cb(2.0, "正在检查音频格式...")
            if engine in ("vosk",):
                wav_path, tmpdir = convert_to_wav(input_path)
            else:
                wav_path = input_path

            if cancel_event.is_set():
                raise WorkerCancelled()

            # ---- 识别 ----
            segments: List[Segment] = []

            if engine == "vosk":
                model_path = self.query_one("#vosk_model_input", Input).value.strip()
                if not model_path:
                    model_path = cfg.get("vosk_model_path", "")
                segments = VoskBackend.transcribe(
                    wav_path, model_path, progress_cb, cancel_event
                )

            elif engine == "whisper":
                model_size = str(self.query_one("#sel_whisper_size", Select).value)
                language = str(self.query_one("#sel_whisper_lang", Select).value)
                if language == "auto":
                    language = ""
                segments = WhisperBackend.transcribe(
                    input_path, model_size, language, progress_cb, cancel_event
                )

            elif engine == "doubao":
                app_id = get_secret("doubao_asr_app_id")
                access_token = get_secret("doubao_asr_access_token")
                r2_account_id = cfg.get("r2_account_id", "")
                r2_access_key_id = get_secret("r2_access_key_id")
                r2_secret_key = get_secret("r2_secret_access_key")
                r2_bucket = cfg.get("r2_bucket", "")

                if not all(
                    [
                        app_id,
                        access_token,
                        r2_account_id,
                        r2_access_key_id,
                        r2_secret_key,
                        r2_bucket,
                    ]
                ):
                    raise RuntimeError(
                        "豆包 ASR 或 R2 凭证不完整，请在「设置」Tab 中配置"
                    )

                language = self.query_one("#sel_doubao_lang", Select).value
                if language is Select.BLANK or language is False:
                    language = ""
                else:
                    language = str(language)
                segments = DoubaoASRBackend.transcribe(
                    input_path,
                    app_id,
                    access_token,
                    r2_account_id,
                    r2_access_key_id,
                    r2_secret_key,
                    r2_bucket,
                    language,
                    progress_cb,
                    cancel_event,
                )

            if cancel_event.is_set():
                raise WorkerCancelled()

            if not segments:
                raise RuntimeError("未识别到任何内容，请检查音频文件或模型配置")

            # ---- 后处理 ----
            progress_cb(92.0, "正在后处理...")
            output_text = ""

            if mode == "srt":
                output_text = SubtitleProcessor.to_srt(segments)
                self.app.call_from_thread(self._set_preview, output_text)

            elif mode == "merge":
                gap = float(cfg.get("paragraph_gap", 2.0))
                output_text = SubtitleProcessor.merge_paragraphs(segments, gap)
                self.app.call_from_thread(self._set_preview, output_text)

            elif mode == "polish":
                progress_cb(93.0, "正在合并段落...")
                gap = float(cfg.get("paragraph_gap", 2.0))
                raw_text = SubtitleProcessor.merge_paragraphs(segments, gap)

                progress_cb(95.0, "正在调用 LLM 整理口述稿（流式输出）...")
                self.app.call_from_thread(self._set_preview, "")

                llm_type = cfg.get("llm_type", "doubao")
                if llm_type == "doubao":
                    api_key = get_secret("doubao_llm_api_key")
                else:
                    api_key = get_secret("openai_api_key")
                base_url = cfg.get("llm_base_url", "")
                model = cfg.get("llm_model", "")

                if not api_key:
                    raise RuntimeError("LLM API Key 未配置，请在「设置」Tab 中填写")

                def stream_cb(token: str) -> None:
                    self.app.call_from_thread(self._append_preview, token)

                output_text = SubtitleProcessor.polish_script(
                    raw_text,
                    llm_type,
                    api_key,
                    base_url,
                    model,
                    stream_cb,
                    cancel_event,
                )

            if cancel_event.is_set():
                raise WorkerCancelled()

            # ---- 写文件 ----
            progress_cb(99.0, "正在写入输出文件...")
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text(output_text, encoding="utf-8")

            progress_cb(100.0, f"完成！→ {output_path}")
            self.app.call_from_thread(self._finish_ui, output_path, True)

        except WorkerCancelled:
            self.app.call_from_thread(self.app.notify, "识别已取消", severity="warning")
            self.app.call_from_thread(self._finish_ui, output_path, False)
        except Exception as e:
            self.app.call_from_thread(self.app.notify, f"错误：{e}", severity="error")
            self.app.call_from_thread(self._finish_ui, output_path, False)
            self.app.call_from_thread(
                self.query_one("#status_label", Label).update, f"错误：{e}"
            )
        finally:
            cleanup_tmpdir(tmpdir)


# ---------- 日志 Tab ----------


_LEVEL_COLORS = {
    "DEBUG": "dim white",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "bold red",
}

_LEVEL_OPTIONS = [
    ("全部", "ALL"),
    ("INFO", "INFO"),
    ("WARNING", "WARNING"),
    ("ERROR", "ERROR"),
    ("DEBUG", "DEBUG"),
]


class LogTab(TabPane):
    """日志面板：实时显示运行日志，支持等级过滤与关键字搜索。"""

    CSS = """
    LogTab {
        padding: 1 2;
    }
    LogTab .log_toolbar {
        height: 3;
        align: left middle;
        margin-bottom: 1;
    }
    LogTab #log_level_select {
        width: 14;
        margin-right: 1;
    }
    LogTab #log_search {
        width: 1fr;
        margin-right: 1;
    }
    LogTab #btn_log_clear {
        width: 8;
        margin-right: 1;
    }
    LogTab #btn_log_copy {
        width: 10;
    }
    LogTab #log_view {
        height: 1fr;
        border: solid $panel;
    }
    LogTab .log_status_row {
        height: 2;
        align: left middle;
        margin-top: 1;
    }
    LogTab #log_server_status {
        width: 1fr;
        color: $text-muted;
    }
    LogTab #btn_log_server_toggle {
        width: 10;
    }
    """

    def __init__(self, *args, log_server: LogServer | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._log_server = log_server
        # 保存初始端口，以便停止后可重启
        self._original_port: int = log_server.port if log_server is not None else 9876
        self._filter_level = "ALL"
        self._filter_text = ""
        # 用于过滤时重建视图的缓存（最多 _LOG_MAX 条）
        self._all_records: list[LogRecord] = []
        self._all_records_lock = threading.Lock()

    def compose(self) -> ComposeResult:
        with Horizontal(classes="log_toolbar"):
            yield Select(
                _LEVEL_OPTIONS,
                value="ALL",
                id="log_level_select",
            )
            yield Input(placeholder="关键字过滤...", id="log_search")
            yield Button("清空", id="btn_log_clear", variant="warning")
            yield Button("复制全部", id="btn_log_copy")
        yield RichLog(id="log_view", highlight=True, markup=True, wrap=True)
        with Horizontal(classes="log_status_row"):
            yield Label("", id="log_server_status")
            yield Button("停止", id="btn_log_server_toggle", variant="error")

    def on_mount(self) -> None:
        self._update_server_status()
        # 注册到 AppLogger，实时接收新日志
        app_logger.add_listener(self._on_new_record_thread)

    def on_unmount(self) -> None:
        app_logger.remove_listener(self._on_new_record_thread)

    # ---- 实时日志接收 ----

    def _on_new_record_thread(self, rec: LogRecord) -> None:
        """AppLogger 回调，在任意线程中调用——调度到主线程处理。"""
        self.app.call_from_thread(self._on_new_record_main, rec)

    def _on_new_record_main(self, rec: LogRecord) -> None:
        """主线程：缓存记录，按当前过滤条件决定是否追加到 RichLog。"""
        with self._all_records_lock:
            self._all_records.append(rec)
            # 同步环形缓冲上限
            if len(self._all_records) > _LOG_MAX:
                self._all_records = self._all_records[-_LOG_MAX:]
        if self._matches(rec):
            self._append_to_view(rec)

    def _matches(self, rec: LogRecord) -> bool:
        if self._filter_level != "ALL" and rec.level != self._filter_level:
            return False
        if self._filter_text and self._filter_text.lower() not in (
            rec.source + " " + rec.message
        ).lower():
            return False
        return True

    def _append_to_view(self, rec: LogRecord) -> None:
        import datetime
        ts = datetime.datetime.fromtimestamp(rec.ts).strftime("%H:%M:%S")
        color = _LEVEL_COLORS.get(rec.level, "white")
        log_view = self.query_one("#log_view", RichLog)
        log_view.write(
            f"[dim]{ts}[/dim]  [{color}]{rec.level:<7}[/{color}]  "
            f"[cyan]{rec.source:<14}[/cyan]  {rec.message}"
        )

    def _rebuild_view(self) -> None:
        """按当前过滤条件重建整个日志视图。"""
        log_view = self.query_one("#log_view", RichLog)
        log_view.clear()
        with self._all_records_lock:
            records = list(self._all_records)
        for rec in records:
            if self._matches(rec):
                self._append_to_view(rec)

    # ---- 事件处理 ----

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "log_level_select":
            self._filter_level = str(event.value) if event.value != Select.BLANK else "ALL"
            self._rebuild_view()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "log_search":
            self._filter_text = event.value
            self._rebuild_view()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id

        if btn_id == "btn_log_clear":
            app_logger.clear()
            with self._all_records_lock:
                self._all_records.clear()
            self.query_one("#log_view", RichLog).clear()

        elif btn_id == "btn_log_copy":
            with self._all_records_lock:
                records = [r for r in self._all_records if self._matches(r)]
            import datetime, subprocess
            lines = []
            for r in records:
                ts = datetime.datetime.fromtimestamp(r.ts).strftime("%H:%M:%S")
                lines.append(f"{ts}  {r.level:<7}  {r.source:<14}  {r.message}")
            content = "\n".join(lines)
            if content:
                try:
                    if sys.platform == "win32":
                        subprocess.run(["clip"], input=content.encode("utf-16"), check=True)
                    elif sys.platform == "darwin":
                        subprocess.run(["pbcopy"], input=content.encode("utf-8"), check=True)
                    else:
                        subprocess.run(["xclip", "-selection", "clipboard"],
                                       input=content.encode("utf-8"), check=True)
                    self.app.notify("日志已复制到剪贴板", severity="information")
                except Exception as e:
                    self.app.notify(f"复制失败：{e}", severity="warning")

        elif btn_id == "btn_log_server_toggle":
            self._toggle_server()

    def _toggle_server(self) -> None:
        if self._log_server is None:
            # 尝试重启（使用保存的原始端口）
            new_server = LogServer(self._original_port)
            try:
                new_server.start()
                self._log_server = new_server
                self.app.notify(f"日志服务器已重启，端口 {new_server.actual_port()}", severity="information")
            except Exception as e:
                self.app.notify(f"日志服务器启动失败：{e}", severity="error")
            self._update_server_status()
            return
        btn = self.query_one("#btn_log_server_toggle", Button)
        if str(btn.label) == "停止":
            self._original_port = self._log_server.actual_port()
            self._log_server.stop()
            self._log_server = None
            self.app.notify("日志服务器已停止", severity="information")
        else:
            # 重新启动（使用相同端口）
            self._log_server.start()
            self.app.notify(f"日志服务器已重启，端口 {self._log_server.actual_port()}", severity="information")
        self._update_server_status()

    def _update_server_status(self) -> None:
        lbl = self.query_one("#log_server_status", Label)
        btn = self.query_one("#btn_log_server_toggle", Button)
        if self._log_server is not None:
            port = self._log_server.actual_port()
            lbl.update(f"● 日志服务器监听 127.0.0.1:{port}  （JSON Lines 协议）")
            btn.label = "停止"
            btn.variant = "error"
        else:
            lbl.update("○ 日志服务器未运行  （--log-port N 启动）")
            btn.label = "启动"
            btn.variant = "success"


# ---------- 主 App ----------


class SpeechExtractorApp(App):
    TITLE = "Speech Extractor"
    CSS = """
    Screen {
        background: $surface;
    }
    TabbedContent {
        height: 1fr;
    }
    TabPane {
        height: 1fr;
        overflow-y: auto;
    }
    """
    BINDINGS = [
        Binding("ctrl+q", "quit", "退出"),
        Binding("ctrl+s", "save_settings", "保存设置"),
        Binding("f1", "switch_tab('tab-1')", "识别"),
        Binding("f2", "switch_tab('tab-2')", "设置"),
        Binding("f3", "switch_tab('tab-3')", "日志"),
    ]

    def __init__(self, *args, log_server: LogServer | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._log_server = log_server

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="main_tabs"):
            yield RecognizeTab("识别", id="tab-1")
            yield SettingsTab("设置", id="tab-2")
            yield LogTab("日志", id="tab-3", log_server=self._log_server)
        yield Footer()

    def on_mount(self) -> None:
        if self._log_server is not None:
            self._log_server.start()

    def on_unmount(self) -> None:
        if self._log_server is not None:
            self._log_server.stop()

    def action_save_settings(self) -> None:
        try:
            settings_tab = self.query_one(SettingsTab)
            settings_tab._save_values()
            self.notify("设置已保存", severity="information")
        except Exception:
            pass

    def action_switch_tab(self, tab_id: str) -> None:
        tabs = self.query_one("#main_tabs", TabbedContent)
        tabs.active = tab_id


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="speech-extract",
        description="Speech Extractor — 音视频字幕提取 TUI",
    )
    parser.add_argument(
        "--log-port",
        type=int,
        default=9876,
        metavar="N",
        help="日志 TCP 服务器端口（默认 9876；传 0 则禁用）",
    )
    args = parser.parse_args()

    log_server: LogServer | None = None
    if args.log_port != 0:
        log_server = LogServer(args.log_port)

    app = SpeechExtractorApp(log_server=log_server)
    app.run()


if __name__ == "__main__":
    main()
