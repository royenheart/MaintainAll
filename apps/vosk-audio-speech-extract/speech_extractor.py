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

import json
import os
import sys
import tempfile
import threading
import time
import uuid
import wave
from dataclasses import dataclass
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
        while not cancel_event.is_set():
            resp = http_requests.post(
                DoubaoASRBackend.QUERY_URL,
                data=json.dumps({}),
                headers=headers,
                timeout=30,
            )
            code = resp.headers.get("X-Api-Status-Code", "")
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
            presigned_url = cls._upload_r2(
                audio_path,
                r2_account_id,
                r2_access_key_id,
                r2_secret_access_key,
                r2_bucket,
                object_key,
            )
            uploaded = True

            if cancel_event.is_set():
                raise WorkerCancelled()

            # 2. 提交任务
            progress_cb(20.0, "正在提交豆包 ASR 任务...")
            task_id, logid = cls._submit_task(
                presigned_url, audio_fmt, language, app_id, access_token
            )

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
    """

    def compose(self) -> ComposeResult:
        # 输入文件
        yield Label("输入文件", classes="section_label")
        with Horizontal(classes="file_row"):
            yield Input(id="input_file", placeholder="选择或拖入音视频文件...")
            yield Button("浏览", id="btn_browse")

        # 引擎 + 后处理模式
        yield Label("识别引擎 / 后处理模式", classes="section_label")
        with Horizontal(classes="engine_modes_row"):
            with Vertical(classes="engine_box"):
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
                mode = self._get_selected_mode()
                self.query_one("#input_output", Input).value = self._auto_output_path(
                    val, mode
                )

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

    def _on_file_selected(self, path: str) -> None:
        if path:
            self.query_one("#input_file", Input).value = path
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

        # 可用性再次检查
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

    def _append_preview(self, text: str) -> None:
        """线程安全地追加预览内容（LLM 流式输出使用）。"""
        ta = self.query_one("#preview_area", TextArea)
        current = ta.text
        ta.load_text(current + text)

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

    def _run_transcribe(self) -> None:
        """在 Worker 线程中执行完整转写流程。"""
        cancel_event = self._cancel_event
        input_path = self.query_one("#input_file", Input).value.strip()
        output_path = self.query_one("#input_output", Input).value.strip()
        engine = self._get_selected_engine()
        mode = self._get_selected_mode()
        cfg = load_config()

        tmpdir = ""
        try:

            def progress_cb(pct: float, msg: str) -> None:
                self.app.call_from_thread(self._update_progress, pct, msg)

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
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="main_tabs"):
            yield RecognizeTab("识别", id="tab-1")
            yield SettingsTab("设置", id="tab-2")
        yield Footer()

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
    app = SpeechExtractorApp()
    app.run()


if __name__ == "__main__":
    main()
