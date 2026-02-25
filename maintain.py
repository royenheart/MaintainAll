#!/usr/bin/env python3
"""
MaintainAll TUI — 单文件 Python TUI
帮助用户快速浏览/引用仓库中的配置模板、部署脚本和运维命令。

依赖：
    pip install textual          # 必需
    pip install openai           # 可选，AI 对话功能

运行：
    python maintain.py
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import subprocess
import sys
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any, Generator

# ──────────────────────────────────────────────────────────────
# 可选依赖检测
# ──────────────────────────────────────────────────────────────
try:
    import openai as _openai_mod  # noqa: F401
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from textual import on, work
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import (
        Container,
        Horizontal,
        ScrollableContainer,
        Vertical,
        VerticalScroll,
    )
    from textual.css.query import NoMatches
    from textual.reactive import reactive
    from textual.screen import ModalScreen, Screen
    from textual.widget import Widget
    from textual.widgets import (
        Button,
        ContentSwitcher,
        Footer,
        Header,
        Input,
        Label,
        ListItem,
        ListView,
        Markdown,
        RichLog,
        Static,
        Tab,
        TabbedContent,
        TabPane,
        TextArea,
        Tree,
    )
    from textual.widgets.tree import TreeNode
except ImportError:
    print("错误：缺少 textual 库，请先安装：pip install textual")
    sys.exit(1)

# ──────────────────────────────────────────────────────────────
# 常量与忽略规则
# ──────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.resolve()
CONFIG_PATH = Path.home() / ".maintainall.json"

# 跳过不需要显示的目录/文件
IGNORE_DIRS = {
    ".git", ".venv", "__pycache__", "node_modules", ".idea",
    ".vscode", ".mypy_cache", ".pytest_cache",
}

# RAG 索引和模板扫描中排除这些文件（文档/工具本身）
RAG_EXCLUDE_FILES = {"maintain.py", "AGENTS.md"}
IGNORE_SUFFIXES = {
    ".pyc", ".pyo", ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".ico", ".woff", ".woff2", ".ttf", ".eot", ".bin", ".so",
    ".a", ".o", ".exe", ".dll", ".zip", ".tar", ".gz", ".xz",
    ".bz2", ".rar", ".7z", ".pdf", ".mp3", ".mp4", ".avi",
    ".mkv", ".wav",
}
TEXT_SUFFIXES = {
    ".sh", ".py", ".yml", ".yaml", ".toml", ".conf", ".json",
    ".md", ".txt", ".j2", ".service", ".timer", ".env", ".cfg",
    ".ini", ".xml", ".html", ".css", ".js", ".ts", ".go", ".rs",
    ".c", ".cpp", ".h", ".hpp", ".java", ".rb", ".pl", ".lua",
    ".sql", ".tf", ".hcl", ".tcl",
}

# 关键命令关键词（用于命令参考提取）
CMD_KEYWORDS = [
    "docker", "docker-compose", "ansible", "ansible-playbook",
    "systemctl", "kubectl", "helm", "terraform", "git",
    "pip", "conda", "apt", "yum", "dnf", "pacman",
    "ssh", "scp", "rsync", "curl", "wget", "make",
    "cmake", "gcc", "g++", "python", "python3", "bash",
    "cbatch", "squeue", "sbatch", "srun", "stow",
]

# 占位符检测模式
PLACEHOLDER_PATTERNS = [
    re.compile(r"\{\{\s*(\w+)\s*\}\}"),                    # Jinja2 {{ var }}
    re.compile(r"\{%.*?%\}"),                              # Jinja2 {% block %}
    re.compile(r"\b(xxx+)\b", re.IGNORECASE),              # xxx
    re.compile(r"\b(your_\w+)\b", re.IGNORECASE),          # your_xxx
    re.compile(r"<([A-Z_][A-Z0-9_]*)>"),                   # <PLACEHOLDER>
    re.compile(r"\b(CHANGE_ME|REPLACE_ME|FILL_IN)\b"),     # CHANGE_ME
    re.compile(r"\b(TODO|FIXME)\b"),                       # TODO/FIXME
]

# Jinja2 变量提取
JINJA2_VAR_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")

# ──────────────────────────────────────────────────────────────
# 配置管理
# ──────────────────────────────────────────────────────────────

DEFAULT_CONFIG: dict[str, Any] = {
    "api_base": "",
    "api_key": "",
    "model": "gpt-4o-mini",
    "repo_path": str(REPO_ROOT),
    "rag_top_k": 5,
    "rag_chunk_size": 100,
}


def load_config() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                data = json.load(f)
            cfg = {**DEFAULT_CONFIG, **data}
            return cfg
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict[str, Any]) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ──────────────────────────────────────────────────────────────
# 仓库文件扫描工具
# ──────────────────────────────────────────────────────────────

def iter_repo_files(repo: Path) -> Generator[Path, None, None]:
    """递归产出仓库中所有文本文件路径。"""
    for root, dirs, files in os.walk(repo):
        # 原地修改 dirs 以剪枝
        dirs[:] = [
            d for d in dirs
            if d not in IGNORE_DIRS and not d.startswith(".")
        ]
        for fname in files:
            if fname in RAG_EXCLUDE_FILES:
                continue
            p = Path(root) / fname
            if p.suffix.lower() in IGNORE_SUFFIXES:
                continue
            yield p


def read_text_safe(path: Path, max_bytes: int = 200_000) -> str | None:
    """安全读取文本文件，遇到二进制文件返回 None。"""
    try:
        raw = path.read_bytes()
        if b"\x00" in raw[:8000]:
            return None
        text = raw[:max_bytes].decode("utf-8", errors="replace")
        return text
    except Exception:
        return None


def get_file_lang(path: Path) -> str:
    """根据后缀返回 Textual/Rich 语法高亮语言名。"""
    mapping = {
        ".py": "python",
        ".sh": "bash",
        ".bash": "bash",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".toml": "toml",
        ".json": "json",
        ".md": "markdown",
        ".j2": "jinja2",
        ".service": "ini",
        ".conf": "ini",
        ".cfg": "ini",
        ".ini": "ini",
        ".xml": "xml",
        ".html": "html",
        ".css": "css",
        ".js": "javascript",
        ".ts": "typescript",
        ".go": "go",
        ".rs": "rust",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".hpp": "cpp",
        ".sql": "sql",
        ".tf": "hcl",
        ".hcl": "hcl",
        ".tcl": "tcl",
    }
    return mapping.get(path.suffix.lower(), "text")


# ──────────────────────────────────────────────────────────────
# 纯 Python TF-IDF RAG
# ──────────────────────────────────────────────────────────────

def tokenize(text: str) -> list[str]:
    """简单分词：小写化 + 按非字母数字切分，保留长度 >= 2 的词。"""
    tokens = re.findall(r"[a-zA-Z0-9_\-\.]+", text.lower())
    return [t for t in tokens if len(t) >= 2]


class TFIDFIndex:
    """轻量 TF-IDF 索引，支持 RAG 检索。"""

    def __init__(self) -> None:
        self.chunks: list[tuple[str, str]] = []   # (file_path, chunk_text)
        self.tfidf_matrix: list[dict[str, float]] = []
        self.idf: dict[str, float] = {}
        self._built = False

    def build(self, repo: Path, chunk_size: int = 100) -> None:
        """扫描仓库，构建 TF-IDF 索引。"""
        self.chunks = []
        all_token_sets: list[list[str]] = []

        for fpath in iter_repo_files(repo):
            if fpath.suffix.lower() not in TEXT_SUFFIXES:
                continue
            text = read_text_safe(fpath)
            if not text:
                continue
            lines = text.splitlines()
            # 按 chunk_size 行分块
            for i in range(0, max(1, len(lines)), chunk_size):
                chunk = "\n".join(lines[i: i + chunk_size])
                rel = str(fpath.relative_to(repo))
                self.chunks.append((rel, chunk))
                all_token_sets.append(tokenize(chunk))

        if not self.chunks:
            return

        # 计算 IDF
        n = len(all_token_sets)
        df: dict[str, int] = defaultdict(int)
        for tokens in all_token_sets:
            for t in set(tokens):
                df[t] += 1
        self.idf = {t: math.log((n + 1) / (cnt + 1)) + 1 for t, cnt in df.items()}

        # 计算每个 chunk 的 TF-IDF 向量（归一化）
        self.tfidf_matrix = []
        for tokens in all_token_sets:
            tf: dict[str, float] = defaultdict(float)
            for t in tokens:
                tf[t] += 1.0
            total = max(len(tokens), 1)
            vec: dict[str, float] = {}
            for t, cnt in tf.items():
                if t in self.idf:
                    vec[t] = (cnt / total) * self.idf[t]
            # L2 归一化
            norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
            self.tfidf_matrix.append({t: v / norm for t, v in vec.items()})

        self._built = True

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, str, float]]:
        """检索 Top-K 相关片段，返回 [(file_path, chunk_text, score)]。"""
        if not self._built:
            return []

        q_tokens = tokenize(query)
        q_tf: dict[str, float] = defaultdict(float)
        for t in q_tokens:
            q_tf[t] += 1.0
        total = max(len(q_tokens), 1)
        q_vec: dict[str, float] = {}
        for t, cnt in q_tf.items():
            if t in self.idf:
                q_vec[t] = (cnt / total) * self.idf[t]
        norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0
        q_vec = {t: v / norm for t, v in q_vec.items()}

        scores: list[tuple[int, float]] = []
        for idx, doc_vec in enumerate(self.tfidf_matrix):
            score = sum(q_vec.get(t, 0.0) * doc_vec.get(t, 0.0) for t in q_vec)
            if score > 0:
                scores.append((idx, score))

        scores.sort(key=lambda x: -x[1])
        results = []
        seen_paths: set[str] = set()
        for idx, score in scores[:top_k * 3]:
            path, chunk = self.chunks[idx]
            # 同一个文件只取最高分片段
            if path not in seen_paths:
                results.append((path, chunk, score))
                seen_paths.add(path)
            if len(results) >= top_k:
                break
        return results


# ──────────────────────────────────────────────────────────────
# 命令参考提取
# ──────────────────────────────────────────────────────────────

def extract_script_info(path: Path, repo: Path) -> dict[str, Any] | None:
    """从脚本文件提取：路径、说明注释、关键命令。"""
    if path.suffix.lower() not in {".sh", ".bash", ".py"}:
        return None
    text = read_text_safe(path)
    if not text:
        return None

    lines = text.splitlines()
    # 提取头部注释（前 20 行）
    header_comments: list[str] = []
    for line in lines[:20]:
        stripped = line.strip()
        if stripped.startswith("#"):
            comment = stripped.lstrip("#").strip()
            if comment and not comment.startswith("!"):
                header_comments.append(comment)
        elif stripped and not stripped.startswith("#"):
            break

    # 提取关键命令行
    key_cmds: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        first_word = re.split(r"[\s|&;]", stripped)[0].lstrip("$").strip()
        # 处理 sudo xxx 之类
        if first_word in ("sudo", "env", "exec", "nohup"):
            parts = stripped.split()
            first_word = parts[1] if len(parts) > 1 else first_word
        if any(kw in first_word or first_word.endswith(kw) for kw in CMD_KEYWORDS):
            key_cmds.append(stripped)

    if not header_comments and not key_cmds:
        return None

    rel = str(path.relative_to(repo))
    return {
        "path": rel,
        "name": path.name,
        "description": " | ".join(header_comments[:3]) if header_comments else "",
        "key_cmds": key_cmds[:15],
        "full_text": text,
    }


def scan_scripts(repo: Path) -> list[dict[str, Any]]:
    """扫描仓库所有脚本文件。"""
    results = []
    for fpath in iter_repo_files(repo):
        info = extract_script_info(fpath, repo)
        if info:
            results.append(info)
    return sorted(results, key=lambda x: x["path"])


# ──────────────────────────────────────────────────────────────
# 模板检测与占位符解析
# ──────────────────────────────────────────────────────────────

def is_template_file(path: Path, text: str) -> bool:
    """判断文件是否为可填充的模板。"""
    name_lower = path.name.lower()
    # 文件名特征
    if ".example" in name_lower:
        return True
    if path.suffix.lower() == ".j2":
        return True
    # 内容特征
    for pattern in PLACEHOLDER_PATTERNS:
        if pattern.search(text):
            return True
    return False


def extract_placeholders(text: str) -> list[str]:
    """从模板文本中提取所有唯一占位符变量名。"""
    found: list[str] = []
    seen: set[str] = set()

    # Jinja2 变量 {{ var }}
    for m in JINJA2_VAR_RE.finditer(text):
        var = m.group(1)
        if var not in seen:
            found.append(var)
            seen.add(var)

    # xxx 类占位符
    for m in re.finditer(r"\b(xxx+)\b", text, re.IGNORECASE):
        var = m.group(1)
        if var not in seen:
            found.append(var)
            seen.add(var)

    # your_xxx 类占位符
    for m in re.finditer(r"\b(your_\w+)\b", text, re.IGNORECASE):
        var = m.group(1)
        if var not in seen:
            found.append(var)
            seen.add(var)

    # <PLACEHOLDER> 类
    for m in re.finditer(r"<([A-Z_][A-Z0-9_]*)>", text):
        var = m.group(1)
        if var not in seen:
            found.append(var)
            seen.add(var)

    # CHANGE_ME / REPLACE_ME
    for m in re.finditer(r"\b(CHANGE_ME|REPLACE_ME|FILL_IN)\b", text):
        var = m.group(0)
        if var not in seen:
            found.append(var)
            seen.add(var)

    return found


TEMPLATE_SCAN_EXCLUDES = RAG_EXCLUDE_FILES | {"README.md"}


def scan_templates(repo: Path) -> list[dict[str, Any]]:
    """扫描仓库中所有模板文件。"""
    results = []
    for fpath in iter_repo_files(repo):
        if fpath.suffix.lower() in IGNORE_SUFFIXES:
            continue
        if fpath.name in TEMPLATE_SCAN_EXCLUDES:
            continue
        # 跳过 dotfiles（如 .bashrc），它们不是部署模板
        if fpath.name.startswith("."):
            continue
        text = read_text_safe(fpath)
        if not text:
            continue
        if is_template_file(fpath, text):
            placeholders = extract_placeholders(text)
            rel = str(fpath.relative_to(repo))
            results.append({
                "path": rel,
                "name": fpath.name,
                "placeholders": placeholders,
                "full_text": text,
                "fpath": fpath,
            })
    return sorted(results, key=lambda x: x["path"])


# ──────────────────────────────────────────────────────────────
# LLM 客户端包装
# ──────────────────────────────────────────────────────────────

class LLMClient:
    """封装 OpenAI 兼容 API 调用，支持流式输出。"""

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import openai
            kwargs: dict[str, Any] = {"api_key": self.cfg.get("api_key") or "sk-none"}
            base = self.cfg.get("api_base", "").strip()
            if base:
                kwargs["base_url"] = base
            self._client = openai.OpenAI(**kwargs)
        return self._client

    def is_available(self) -> bool:
        if not OPENAI_AVAILABLE:
            return False
        if not self.cfg.get("api_key"):
            return False
        return True

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
    ) -> Generator[str, None, None]:
        """流式返回 token 文本。"""
        client = self._get_client()
        model = model or self.cfg.get("model", "gpt-4o-mini")
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            max_tokens=4096,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content


# ──────────────────────────────────────────────────────────────
# ── TUI 组件 ──────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────
# 设置面板（ModalScreen）
# ──────────────────────────────────────────────────────────────

class SettingsScreen(ModalScreen[dict[str, Any] | None]):
    """设置弹窗：编辑 ~/.maintainall.json 中的配置项。"""

    DEFAULT_CSS = """
    SettingsScreen {
        align: center middle;
    }
    #settings-dialog {
        width: 70;
        height: auto;
        max-height: 90%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #settings-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: $primary;
    }
    .settings-label {
        margin-top: 1;
        color: $text-muted;
    }
    #settings-buttons {
        margin-top: 1;
        height: auto;
        align: right middle;
    }
    #btn-save {
        margin-right: 1;
    }
    """

    def __init__(self, cfg: dict[str, Any]) -> None:
        super().__init__()
        self._cfg = cfg

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-dialog"):
            yield Label("⚙  设置", id="settings-title")
            yield Label("API Base URL（留空则降级为纯检索模式）", classes="settings-label")
            yield Input(
                value=self._cfg.get("api_base", ""),
                placeholder="https://api.deepseek.com/v1",
                id="input-api-base",
            )
            yield Label("API Key", classes="settings-label")
            yield Input(
                value=self._cfg.get("api_key", ""),
                placeholder="sk-...",
                id="input-api-key",
                password=True,
            )
            yield Label("模型名称", classes="settings-label")
            yield Input(
                value=self._cfg.get("model", "gpt-4o-mini"),
                placeholder="deepseek-chat / gpt-4o-mini",
                id="input-model",
            )
            yield Label("RAG 返回片段数（rag_top_k）", classes="settings-label")
            yield Input(
                value=str(self._cfg.get("rag_top_k", 5)),
                placeholder="5",
                id="input-rag-top-k",
            )
            yield Label("RAG 分块大小（行数，rag_chunk_size）", classes="settings-label")
            yield Input(
                value=str(self._cfg.get("rag_chunk_size", 100)),
                placeholder="100",
                id="input-rag-chunk-size",
            )
            with Horizontal(id="settings-buttons"):
                yield Button("保存", variant="primary", id="btn-save")
                yield Button("取消", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
            return

        new_cfg = dict(self._cfg)
        new_cfg["api_base"] = self.query_one("#input-api-base", Input).value.strip()
        new_cfg["api_key"] = self.query_one("#input-api-key", Input).value.strip()
        new_cfg["model"] = self.query_one("#input-model", Input).value.strip() or "gpt-4o-mini"
        try:
            new_cfg["rag_top_k"] = int(self.query_one("#input-rag-top-k", Input).value)
        except ValueError:
            new_cfg["rag_top_k"] = 5
        try:
            new_cfg["rag_chunk_size"] = int(self.query_one("#input-rag-chunk-size", Input).value)
        except ValueError:
            new_cfg["rag_chunk_size"] = 100

        self.dismiss(new_cfg)

    def on_key(self, event: Any) -> None:
        if event.key == "escape":
            self.dismiss(None)


# ──────────────────────────────────────────────────────────────
# 浏览面板
# ──────────────────────────────────────────────────────────────

class BrowsePane(Widget):
    """左侧文件树 + 右侧文件内容预览。"""

    DEFAULT_CSS = """
    BrowsePane {
        layout: horizontal;
        height: 1fr;
    }
    #file-tree-container {
        width: 30;
        min-width: 20;
        border-right: solid $primary-darken-2;
        height: 1fr;
        overflow-y: auto;
    }
    #file-content {
        width: 1fr;
        height: 1fr;
        overflow-y: auto;
        overflow-x: auto;
    }
    #browse-placeholder {
        padding: 2 4;
        color: $text-muted;
    }
    """

    def __init__(self, repo: Path) -> None:
        super().__init__()
        self._repo = repo

    def compose(self) -> ComposeResult:
        with Vertical(id="file-tree-container"):
            tree: Tree[Path] = Tree("📁 " + self._repo.name)
            tree.id = "repo-tree"
            self._populate_tree(tree.root, self._repo)
            tree.root.expand()
            yield tree
        with VerticalScroll(id="file-content"):
            yield Static(
                "← 点击左侧文件查看内容",
                id="browse-placeholder",
            )

    def _populate_tree(self, node: TreeNode[Path], path: Path) -> None:
        """递归填充文件树。"""
        try:
            entries = sorted(
                path.iterdir(),
                key=lambda p: (p.is_file(), p.name.lower()),
            )
        except PermissionError:
            return
        for entry in entries:
            if entry.name in IGNORE_DIRS or entry.name.startswith("."):
                continue
            if entry.is_dir():
                child = node.add(f"📁 {entry.name}", data=entry, expand=False)
                self._populate_tree(child, entry)
            elif entry.suffix.lower() not in IGNORE_SUFFIXES:
                node.add_leaf(f"📄 {entry.name}", data=entry)

    @on(Tree.NodeSelected)
    def on_tree_node_selected(self, event: Tree.NodeSelected[Path]) -> None:
        path: Path | None = event.node.data
        if path is None or path.is_dir():
            return
        self._show_file(path)

    def _show_file(self, path: Path) -> None:
        text = read_text_safe(path)
        content_area = self.query_one("#file-content", VerticalScroll)
        content_area.remove_children()

        if text is None:
            content_area.mount(Static("（二进制文件，无法预览）"))
            return

        lang = get_file_lang(path)
        rel = str(path.relative_to(self._repo))
        header = Static(f"[bold cyan]{rel}[/bold cyan]  [dim]{lang}[/dim]")

        # 使用 TextArea 展示（只读）
        ta = TextArea(text, language=lang if lang != "text" else None, read_only=True)
        ta.styles.height = max(len(text.splitlines()) + 2, 20)

        content_area.mount(header)
        content_area.mount(ta)


# ──────────────────────────────────────────────────────────────
# AI 对话面板
# ──────────────────────────────────────────────────────────────

class ChatMessage(Static):
    """单条对话气泡。"""

    DEFAULT_CSS = """
    ChatMessage {
        margin: 0 1;
        padding: 0 1;
    }
    ChatMessage.user-msg {
        background: $primary-darken-3;
        border-left: solid $primary;
        margin-left: 4;
    }
    ChatMessage.assistant-msg {
        background: $surface-darken-1;
        border-left: solid $accent;
        margin-right: 4;
    }
    ChatMessage.system-msg {
        color: $text-muted;
        text-style: italic;
    }
    """


class ChatPane(Widget):
    """AI 对话功能面板。"""

    DEFAULT_CSS = """
    ChatPane {
        layout: vertical;
        height: 1fr;
    }
    #chat-log {
        height: 1fr;
        overflow-y: auto;
        padding: 1;
    }
    #chat-input-bar {
        height: auto;
        min-height: 3;
        max-height: 6;
        border-top: solid $primary-darken-2;
        layout: horizontal;
        padding: 0 1;
    }
    #chat-input {
        width: 1fr;
    }
    #btn-send {
        width: 10;
        min-width: 8;
        margin-left: 1;
    }
    #chat-status {
        height: 1;
        padding: 0 2;
        color: $text-muted;
    }
    """

    def __init__(
        self,
        rag_index: TFIDFIndex,
        llm: LLMClient,
        cfg: dict[str, Any],
    ) -> None:
        super().__init__()
        self._rag = rag_index
        self._llm = llm
        self._cfg = cfg
        self._history: list[dict[str, str]] = []
        self._thinking = False

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="chat-log")
        yield Static("", id="chat-status")
        with Horizontal(id="chat-input-bar"):
            yield Input(
                placeholder="输入问题，例如：如何部署 SLURM 集群？（Enter 发送，Ctrl+L 清空）",
                id="chat-input",
            )
            yield Button("发送", variant="primary", id="btn-send")

    def on_mount(self) -> None:
        mode = "AI 对话模式" if self._llm.is_available() else "纯检索模式（未配置 API Key）"
        self._append_system(f"欢迎使用 MaintainAll TUI！当前为 {mode}。\n"
                            "RAG 索引构建中，请稍候……")

    def _append_system(self, text: str) -> None:
        msg = ChatMessage(text, classes="system-msg")
        log = self.query_one("#chat-log", VerticalScroll)
        log.mount(msg)
        log.scroll_end(animate=False)

    def _append_msg(self, role: str, text: str) -> ChatMessage:
        css_class = "user-msg" if role == "user" else "assistant-msg"
        prefix = "🧑 你：\n" if role == "user" else "🤖 助手：\n"
        msg = ChatMessage(prefix + text, classes=css_class)
        log = self.query_one("#chat-log", VerticalScroll)
        log.mount(msg)
        log.scroll_end(animate=False)
        return msg

    def _set_status(self, text: str) -> None:
        self.query_one("#chat-status", Static).update(text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-send":
            self._send()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "chat-input":
            self._send()

    def _send(self) -> None:
        if self._thinking:
            return
        inp = self.query_one("#chat-input", Input)
        query = inp.value.strip()
        if not query:
            return
        inp.value = ""
        self._append_msg("user", query)
        self._thinking = True
        self._set_status("⏳ 思考中……")
        self._do_chat(query)

    @work(thread=True)
    def _do_chat(self, query: str) -> None:
        """后台线程：RAG 检索 + LLM 调用。"""
        top_k = self._cfg.get("rag_top_k", 5)
        results = self._rag.search(query, top_k=top_k)

        if not self._llm.is_available():
            # 降级：只展示检索结果
            if results:
                lines = ["📂 找到以下相关文件，请在 **浏览** 面板中查看：\n"]
                for path, chunk, score in results:
                    lines.append(f"• `{path}`（相关度 {score:.3f}）")
                    # 显示片段前几行
                    preview = "\n".join(chunk.splitlines()[:5])
                    lines.append(f"  ```\n  {preview}\n  ```")
                reply = "\n".join(lines)
            else:
                reply = "未检索到相关内容，请尝试换个关键词。"
            self.app.call_from_thread(self._finish_chat, reply)
            return

        # 构造 RAG system prompt
        if results:
            ctx_parts = []
            for path, chunk, score in results:
                ctx_parts.append(f"--- 文件：{path} ---\n{chunk}")
            context = "\n\n".join(ctx_parts)
            system_prompt = (
                "你是一个运维助手，专门帮助用户理解和使用 MaintainAll 仓库中的配置模板、"
                "部署脚本和运维工具。\n\n"
                "以下是仓库中与用户问题最相关的文件片段，请基于这些内容回答用户问题。\n"
                "回答时请：\n"
                "1. 优先引用仓库中实际存在的文件路径\n"
                "2. 给出具体可执行的命令或配置步骤\n"
                "3. 如果内容不足以回答，请说明需要查看哪些文件\n\n"
                f"=== 相关文件内容 ===\n{context}"
            )
        else:
            system_prompt = (
                "你是一个运维助手，帮助用户理解部署脚本和配置模板。"
                "请基于你的知识回答用户问题，并提示用户可以在仓库中查找相关文件。"
            )

        messages = [{"role": "system", "content": system_prompt}]
        # 加入对话历史（最多保留最近 8 轮）
        messages.extend(self._history[-16:])
        messages.append({"role": "user", "content": query})

        # 流式输出
        full_reply = ""
        msg_widget: ChatMessage | None = None

        try:
            for token in self._llm.chat_stream(messages):
                full_reply += token
                if msg_widget is None:
                    msg_widget = self.app.call_from_thread(
                        self._create_assistant_msg
                    )
                else:
                    self.app.call_from_thread(
                        self._update_assistant_msg, msg_widget, full_reply
                    )
        except Exception as e:
            full_reply = f"调用 API 出错：{e}"

        self._history.append({"role": "user", "content": query})
        self._history.append({"role": "assistant", "content": full_reply})
        self.app.call_from_thread(self._finish_chat, full_reply, msg_widget)

    def _create_assistant_msg(self) -> ChatMessage:
        return self._append_msg("assistant", "")

    def _update_assistant_msg(self, msg: ChatMessage, text: str) -> None:
        msg.update("🤖 助手：\n" + text)
        log = self.query_one("#chat-log", VerticalScroll)
        log.scroll_end(animate=False)

    def _finish_chat(
        self,
        text: str,
        existing_msg: ChatMessage | None = None,
    ) -> None:
        if existing_msg is None:
            self._append_msg("assistant", text)
        else:
            self._update_assistant_msg(existing_msg, text)
        self._thinking = False
        self._set_status("")

    def clear_chat(self) -> None:
        self._history.clear()
        log = self.query_one("#chat-log", VerticalScroll)
        log.remove_children()
        self._append_system("对话已清空。")

    def notify_index_ready(self) -> None:
        """RAG 索引构建完成后调用。"""
        mode = "AI 对话模式" if self._llm.is_available() else "纯检索模式（未配置 API Key）"
        self._append_system(f"✅ RAG 索引构建完成。当前为 {mode}。")


# ──────────────────────────────────────────────────────────────
# 命令参考面板
# ──────────────────────────────────────────────────────────────

class CommandPane(Widget):
    """命令参考面板：可搜索的脚本列表 + 详情预览。"""

    DEFAULT_CSS = """
    CommandPane {
        layout: vertical;
        height: 1fr;
    }
    #cmd-search-bar {
        height: 3;
        padding: 0 1;
        border-bottom: solid $primary-darken-2;
    }
    #cmd-main {
        layout: horizontal;
        height: 1fr;
    }
    #cmd-list-container {
        width: 40%;
        border-right: solid $primary-darken-2;
        overflow-y: auto;
    }
    #cmd-detail {
        width: 60%;
        overflow-y: auto;
        padding: 1;
    }
    .cmd-item {
        padding: 0 1;
        height: auto;
    }
    .cmd-item-name {
        text-style: bold;
        color: $accent;
    }
    .cmd-item-desc {
        color: $text-muted;
    }
    #cmd-placeholder {
        padding: 2 4;
        color: $text-muted;
    }
    """

    def __init__(self, scripts: list[dict[str, Any]]) -> None:
        super().__init__()
        self._all_scripts = scripts
        self._filtered = list(scripts)
        self._selected: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        yield Input(
            placeholder="🔍 搜索脚本（按名称/路径/命令过滤）…",
            id="cmd-search",
        )
        with Horizontal(id="cmd-main"):
            with VerticalScroll(id="cmd-list-container"):
                yield ListView(id="cmd-list")
            with VerticalScroll(id="cmd-detail"):
                yield Static(
                    "← 点击左侧脚本查看详情",
                    id="cmd-placeholder",
                )

    def on_mount(self) -> None:
        self._render_list()

    def _render_list(self) -> None:
        lv = self.query_one("#cmd-list", ListView)
        lv.clear()
        for script in self._filtered:
            name = script["name"]
            desc = script["description"] or "(无说明)"
            path = script["path"]
            item_content = (
                f"[bold cyan]{name}[/bold cyan]\n"
                f"[dim]{path}[/dim]\n"
                f"[italic]{desc[:60]}{'…' if len(desc) > 60 else ''}[/italic]"
            )
            lv.append(ListItem(Static(item_content), classes="cmd-item"))

    @on(Input.Changed, "#cmd-search")
    def on_search_changed(self, event: Input.Changed) -> None:
        q = event.value.strip().lower()
        if not q:
            self._filtered = list(self._all_scripts)
        else:
            self._filtered = [
                s for s in self._all_scripts
                if q in s["path"].lower()
                or q in s["name"].lower()
                or q in s["description"].lower()
                or any(q in cmd.lower() for cmd in s["key_cmds"])
            ]
        self._render_list()

    @on(ListView.Selected)
    def on_list_selected(self, event: ListView.Selected) -> None:
        idx = self.query_one("#cmd-list", ListView).index
        if idx is None or idx >= len(self._filtered):
            return
        script = self._filtered[idx]
        self._show_detail(script)

    def _show_detail(self, script: dict[str, Any]) -> None:
        detail = self.query_one("#cmd-detail", VerticalScroll)
        detail.remove_children()

        header = Static(
            f"[bold cyan]{script['path']}[/bold cyan]\n"
            f"[italic]{script['description'] or '(无说明)'}[/italic]"
        )
        detail.mount(header)

        if script["key_cmds"]:
            detail.mount(Static("\n[bold yellow]关键命令：[/bold yellow]"))
            cmds_text = "\n".join(f"  $ {cmd}" for cmd in script["key_cmds"])
            detail.mount(Static(f"[green]{cmds_text}[/green]"))

        detail.mount(Static("\n[bold]完整内容：[/bold]"))
        lang = get_file_lang(Path(script["path"]))
        ta = TextArea(
            script["full_text"],
            language=lang if lang != "text" else None,
            read_only=True,
        )
        ta.styles.height = max(len(script["full_text"].splitlines()) + 2, 20)
        detail.mount(ta)


# ──────────────────────────────────────────────────────────────
# 模板填充面板
# ──────────────────────────────────────────────────────────────

class TemplatePane(Widget):
    """模板填充面板：自动检测模板文件，引导填充变量。"""

    DEFAULT_CSS = """
    TemplatePane {
        layout: horizontal;
        height: 1fr;
    }
    #tpl-list-container {
        width: 30%;
        border-right: solid $primary-darken-2;
        overflow-y: auto;
    }
    #tpl-right {
        width: 70%;
        layout: vertical;
        height: 1fr;
    }
    #tpl-form-area {
        height: 40%;
        overflow-y: auto;
        padding: 1;
        border-bottom: solid $primary-darken-2;
    }
    #tpl-preview-area {
        height: 60%;
        overflow-y: auto;
        padding: 1;
    }
    .tpl-var-row {
        layout: horizontal;
        height: 3;
        margin-bottom: 0;
    }
    .tpl-var-label {
        width: 25%;
        padding: 1 1;
        color: $accent;
    }
    .tpl-var-input {
        width: 75%;
    }
    #tpl-buttons {
        height: 3;
        layout: horizontal;
        padding: 0 1;
        border-top: solid $primary-darken-2;
    }
    #tpl-placeholder-msg {
        padding: 2 4;
        color: $text-muted;
    }
    #btn-tpl-copy {
        margin-right: 1;
    }
    """

    def __init__(self, templates: list[dict[str, Any]], repo: Path) -> None:
        super().__init__()
        self._templates = templates
        self._repo = repo
        self._current: dict[str, Any] | None = None
        self._var_inputs: dict[str, Input] = {}

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="tpl-list-container"):
            yield ListView(id="tpl-list")
        with Vertical(id="tpl-right"):
            with VerticalScroll(id="tpl-form-area"):
                yield Static(
                    "← 选择左侧模板文件，然后填写变量",
                    id="tpl-placeholder-msg",
                )
            with VerticalScroll(id="tpl-preview-area"):
                pass
            with Horizontal(id="tpl-buttons"):
                yield Button("📋 复制到剪贴板", id="btn-tpl-copy")
                yield Button("💾 保存为新文件", variant="primary", id="btn-tpl-save")

    def on_mount(self) -> None:
        lv = self.query_one("#tpl-list", ListView)
        for tpl in self._templates:
            label = f"[bold]{tpl['name']}[/bold]\n[dim]{tpl['path']}[/dim]"
            if tpl["placeholders"]:
                n = len(tpl["placeholders"])
                label += f"\n[yellow]{n} 个占位符[/yellow]"
            lv.append(ListItem(Static(label)))

    @on(ListView.Selected)
    def on_list_selected(self, event: ListView.Selected) -> None:
        lv = self.query_one("#tpl-list", ListView)
        idx = lv.index
        if idx is None or idx >= len(self._templates):
            return
        self._load_template(self._templates[idx])

    def _load_template(self, tpl: dict[str, Any]) -> None:
        self._current = tpl
        self._var_inputs = {}

        form_area = self.query_one("#tpl-form-area", VerticalScroll)
        form_area.remove_children()

        if not tpl["placeholders"]:
            form_area.mount(Static(
                f"[green]文件 {tpl['name']} 未检测到占位符。[/green]\n"
                "可直接复制或查看内容。"
            ))
        else:
            form_area.mount(Static(
                f"[bold cyan]{tpl['path']}[/bold cyan]\n"
                f"检测到 {len(tpl['placeholders'])} 个占位符，请逐一填写："
            ))
            for var in tpl["placeholders"]:
                row = Horizontal(classes="tpl-var-row")
                lbl = Label(var, classes="tpl-var-label")
                inp = Input(placeholder=f"填写 {var}", classes="tpl-var-input", id=f"tplvar_{var}")
                self._var_inputs[var] = inp
                form_area.mount(row)
                row.mount(lbl)
                row.mount(inp)

        # 初始预览
        self._refresh_preview()

    @on(Input.Changed)
    def on_any_input_changed(self, event: Input.Changed) -> None:
        if event.input.id and event.input.id.startswith("tplvar_"):
            self._refresh_preview()

    def _get_filled_text(self) -> str:
        if self._current is None:
            return ""
        text = self._current["full_text"]
        for var, inp in self._var_inputs.items():
            val = inp.value or f"{{{var}}}"
            # 替换 Jinja2 {{ var }} 格式
            text = re.sub(
                r"\{\{\s*" + re.escape(var) + r"\s*\}\}",
                val,
                text,
            )
            # 替换 xxx / your_xxx 格式（精确匹配）
            text = re.sub(r"\b" + re.escape(var) + r"\b", val, text)
        return text

    def _refresh_preview(self) -> None:
        preview_area = self.query_one("#tpl-preview-area", VerticalScroll)
        preview_area.remove_children()
        if self._current is None:
            return
        filled = self._get_filled_text()
        preview_area.mount(Static("[bold]预览（已替换变量）：[/bold]"))
        lang = get_file_lang(Path(self._current["path"]))
        ta = TextArea(
            filled,
            language=lang if lang != "text" else None,
            read_only=True,
        )
        ta.styles.height = max(len(filled.splitlines()) + 2, 15)
        preview_area.mount(ta)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-tpl-copy":
            self._copy_to_clipboard()
        elif event.button.id == "btn-tpl-save":
            self._save_to_file()

    def _copy_to_clipboard(self) -> None:
        if self._current is None:
            self.app.notify("请先选择一个模板文件", severity="warning")
            return
        text = self._get_filled_text()
        try:
            # 尝试 xclip / xsel / pbcopy / wl-copy
            for cmd in [
                ["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"],
                ["pbcopy"],
                ["wl-copy"],
            ]:
                try:
                    subprocess.run(cmd, input=text.encode(), check=True, timeout=5)
                    self.app.notify("✅ 已复制到剪贴板")
                    return
                except (FileNotFoundError, subprocess.CalledProcessError):
                    continue
            self.app.notify("未找到剪贴板工具（xclip/xsel/pbcopy/wl-copy）", severity="warning")
        except Exception as e:
            self.app.notify(f"复制失败：{e}", severity="error")

    def _save_to_file(self) -> None:
        if self._current is None:
            self.app.notify("请先选择一个模板文件", severity="warning")
            return
        text = self._get_filled_text()
        orig = Path(self._current["path"])
        # 生成输出文件名：去掉 .example 后缀，或加 .filled
        name = orig.name
        if ".example" in name:
            new_name = name.replace(".example", "")
        elif name.endswith(".j2"):
            new_name = name[:-3]
        else:
            new_name = name + ".filled"
        out_path = self._repo / orig.parent / new_name
        try:
            out_path.write_text(text, encoding="utf-8")
            self.app.notify(f"✅ 已保存到 {out_path.relative_to(self._repo)}")
        except Exception as e:
            self.app.notify(f"保存失败：{e}", severity="error")


# ──────────────────────────────────────────────────────────────
# 主应用
# ──────────────────────────────────────────────────────────────

class MaintainAllApp(App):
    """MaintainAll TUI 主应用。"""

    TITLE = "MaintainAll TUI"
    SUB_TITLE = "配置模板 · 部署脚本 · 运维参考"

    CSS = """
    Screen {
        background: $background;
    }
    TabbedContent {
        height: 1fr;
    }
    TabPane {
        height: 1fr;
        padding: 0;
    }
    #loading-indicator {
        padding: 1 2;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "退出", show=True),
        Binding("f1", "open_settings", "设置", show=True),
        Binding("ctrl+l", "clear_chat", "清空对话", show=True),
        Binding("ctrl+s", "save_template", "保存模板", show=True),
        Binding("ctrl+f", "focus_search", "搜索", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._cfg = load_config()
        self._repo = Path(self._cfg.get("repo_path") or REPO_ROOT)
        self._rag_index = TFIDFIndex()
        self._llm = LLMClient(self._cfg)
        self._scripts: list[dict[str, Any]] = []
        self._templates: list[dict[str, Any]] = []
        self._index_ready = False

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(id="main-tabs"):
            with TabPane("📁 浏览", id="tab-browse"):
                yield BrowsePane(self._repo)
            with TabPane("🤖 AI 对话", id="tab-chat"):
                yield ChatPane(self._rag_index, self._llm, self._cfg)
            with TabPane("⌨  命令参考", id="tab-commands"):
                yield Static("⏳ 扫描脚本中…", id="loading-commands")
            with TabPane("📝 模板填充", id="tab-templates"):
                yield Static("⏳ 扫描模板中…", id="loading-templates")
        yield Footer()

    def on_mount(self) -> None:
        # 后台线程同时构建 RAG 索引 + 扫描脚本 + 扫描模板
        threading.Thread(target=self._background_init, daemon=True).start()

    def _background_init(self) -> None:
        """后台初始化：构建索引、扫描脚本和模板。"""
        chunk_size = self._cfg.get("rag_chunk_size", 100)

        # 并发执行三个任务
        scripts_done = threading.Event()
        templates_done = threading.Event()
        rag_done = threading.Event()

        def do_scripts():
            self._scripts = scan_scripts(self._repo)
            scripts_done.set()

        def do_templates():
            self._templates = scan_templates(self._repo)
            templates_done.set()

        def do_rag():
            self._rag_index.build(self._repo, chunk_size=chunk_size)
            rag_done.set()

        t1 = threading.Thread(target=do_scripts, daemon=True)
        t2 = threading.Thread(target=do_templates, daemon=True)
        t3 = threading.Thread(target=do_rag, daemon=True)
        t1.start(); t2.start(); t3.start()
        t1.join(); t2.join(); t3.join()

        # 回到主线程更新 UI
        self.call_from_thread(self._on_init_done)

    def _on_init_done(self) -> None:
        """所有后台初始化完成后更新 UI。"""
        # 更新命令参考面板
        try:
            placeholder = self.query_one("#loading-commands", Static)
            placeholder.remove()
        except NoMatches:
            pass
        cmd_pane_parent = self.query_one("#tab-commands", TabPane)
        cmd_pane_parent.mount(CommandPane(self._scripts))

        # 更新模板填充面板
        try:
            placeholder = self.query_one("#loading-templates", Static)
            placeholder.remove()
        except NoMatches:
            pass
        tpl_pane_parent = self.query_one("#tab-templates", TabPane)
        tpl_pane_parent.mount(TemplatePane(self._templates, self._repo))

        # 通知对话面板索引就绪
        try:
            chat = self.query_one(ChatPane)
            chat.notify_index_ready()
        except NoMatches:
            pass

        self._index_ready = True
        self.notify(
            f"✅ 初始化完成：{len(self._scripts)} 个脚本，"
            f"{len(self._templates)} 个模板，"
            f"{len(self._rag_index.chunks)} 个 RAG 片段"
        )

    # ── Actions ──────────────────────────────────────────────

    def action_open_settings(self) -> None:
        def on_dismiss(result: dict[str, Any] | None) -> None:
            if result is not None:
                self._cfg = result
                save_config(result)
                # 更新 LLM 客户端配置
                self._llm.cfg = result
                self._llm._client = None
                self.notify("✅ 设置已保存")

        self.push_screen(SettingsScreen(self._cfg), on_dismiss)

    def action_clear_chat(self) -> None:
        try:
            chat = self.query_one(ChatPane)
            chat.clear_chat()
        except NoMatches:
            pass

    def action_save_template(self) -> None:
        try:
            tpl = self.query_one(TemplatePane)
            tpl._save_to_file()
        except NoMatches:
            pass

    def action_focus_search(self) -> None:
        """将焦点移到当前面板的搜索框。"""
        try:
            tabs = self.query_one("#main-tabs", TabbedContent)
            active = tabs.active
            if active == "tab-commands":
                self.query_one("#cmd-search", Input).focus()
            elif active == "tab-chat":
                self.query_one("#chat-input", Input).focus()
        except NoMatches:
            pass


# ──────────────────────────────────────────────────────────────
# 首次运行引导
# ──────────────────────────────────────────────────────────────

def first_run_setup() -> None:
    """首次运行时，交互式引导用户配置 API。"""
    print("=" * 60)
    print("欢迎使用 MaintainAll TUI！")
    print("=" * 60)
    print()
    print("检测到配置文件不存在，请进行初始化配置。")
    print("（所有配置均可跳过，按 Enter 使用默认值）")
    print()

    cfg = dict(DEFAULT_CONFIG)
    cfg["repo_path"] = str(REPO_ROOT)

    print("【AI 对话功能配置】")
    print("如果你有 OpenAI 兼容的 API（如 DeepSeek、Qwen、SiliconFlow 等），")
    print("填入后可启用 AI 智能问答；否则使用纯关键词检索模式。")
    print()

    api_base = input("API Base URL（例如 https://api.deepseek.com/v1，留空跳过）: ").strip()
    if api_base:
        cfg["api_base"] = api_base
        api_key = input("API Key（sk-...）: ").strip()
        cfg["api_key"] = api_key
        model = input("模型名称（默认 deepseek-chat）: ").strip()
        cfg["model"] = model or "deepseek-chat"

    save_config(cfg)
    print()
    print(f"✅ 配置已保存到 {CONFIG_PATH}")
    print("提示：之后可在 TUI 界面中按 F1 修改设置。")
    print()


# ──────────────────────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────────────────────

def main() -> None:
    if not CONFIG_PATH.exists():
        first_run_setup()

    app = MaintainAllApp()
    app.run()


if __name__ == "__main__":
    main()
