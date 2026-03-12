# vosk-audio-speech-extract — 方案文档

## 目标

将原始的 `vosk_reg.py` 改写为一个基于 **Textual TUI** 的交互式音视频字幕提取工具，支持多种 ASR 后端和字幕后处理模式。

---

## 文件结构

```
vosk-audio-speech-extract/
├── vosk_reg.py          # 单文件主程序（Textual TUI）
├── pyproject.toml       # 依赖与项目元数据
├── AGENTS.md            # 本文档
├── docs/                # API 接入文档 + Demo
│   ├── 豆包大模型录音识别 API 接入文档.md
│   ├── 豆包语言大模型 API 接入文档.md
│   └── auc_python/
│       ├── readme.md
│       └── auc_websocket_demo.py
├── models/              # Vosk 模型目录（gitignored）
├── audios/              # 输入音视频（gitignored）
└── speeches/            # 输出字幕文件（gitignored）
```

---

## 依赖管理（pyproject.toml）

```toml
[project]
name = "vosk-audio-speech-extract"
version = "0.2.0"
requires-python = ">=3.10"
dependencies = [
    "textual>=0.47",
    "ffmpeg-python",
    "keyring",
]

[project.optional-dependencies]
vosk    = ["vosk"]
whisper = ["openai-whisper"]
doubao  = ["boto3", "requests"]   # R2 上传 + ASR HTTP API
llm     = ["openai>=1.0"]
all     = ["vosk", "openai-whisper", "boto3", "requests", "openai>=1.0"]
```

安装示例：

```bash
# 全部
pip install -e ".[all]"

# 按需
pip install -e ".[whisper,llm]"
```

---

## 功能模块

### 1. 识别后端（三种，缺依赖自动禁用对应选项）

| 后端 | 依赖 | 说明 |
|---|---|---|
| **Vosk（本地）** | `vosk` | 原有实现，使用本地 Kaldi 模型 |
| **Whisper（本地）** | `openai-whisper` | OpenAI Whisper，支持 tiny/base/small/medium/large |
| **豆包 ASR（云端）** | `boto3`, `requests` | 提交+轮询模式，本地文件先上传 Cloudflare R2 |

#### 豆包 ASR 本地文件处理流程

```
本地文件
  → ffmpeg 转 WAV（如需）
  → 上传到 Cloudflare R2（boto3 S3 兼容 API）
  → 生成预签名 URL（有效期 3600s）
  → 提交豆包 ASR 任务（POST submit URL）
  → 轮询结果（每 2s，检查 X-Api-Status-Code）
  → 解析 utterances（start_time/end_time 毫秒转秒）
  → 删除 R2 临时文件（finally 保证执行）
```

豆包 ASR API 端点：
- 提交：`https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit`
- 查询：`https://openspeech.bytedance.com/api/v3/auc/bigmodel/query`

### 2. 字幕后处理（三种模式）

| 模式 | 实现方式 | 输出 |
|---|---|---|
| **带时间轴字幕** | 纯本地，标准 SRT 格式 | `.srt` |
| **合并长段落** | 纯本地规则（按停顿间隔分段） | `.txt` |
| **整理口述稿** | 调用 LLM（需配置） | `.txt` |

**合并段落算法**：遍历 Segment 列表，相邻停顿 ≤ gap_threshold（默认 2.0 秒）则拼接，超过则换行分段。中文无空格，英文加空格。不修改任何词汇。

**口述稿 LLM prompt**：
- system：`你是一个专业的文字整理助手。`
- user：`以下是从音视频中提取的原始转写文字。请整理成一篇逻辑通顺的口述稿：保留核心内容，修正明显语病和口语化重复，不要添加原文没有的信息。\n原文：\n{raw_text}`

### 3. 密钥存储

使用 `keyring` 库，服务名称 `vosk-speech-extractor`，自动使用系统密钥环（Windows Credential Manager / macOS Keychain / Linux Secret Service）。

| 键名 | 说明 |
|---|---|
| `doubao_asr_app_id` | 豆包 ASR App ID |
| `doubao_asr_access_token` | 豆包 ASR Access Token |
| `r2_access_key_id` | Cloudflare R2 Access Key ID |
| `r2_secret_access_key` | Cloudflare R2 Secret Access Key |
| `doubao_llm_api_key` | 豆包 LLM API Key |
| `openai_api_key` | OpenAI 兼容 API Key |

非敏感配置存储在 `~/.vosk_speech/config.json`：

```json
{
  "default_engine": "whisper",
  "whisper_model_size": "small",
  "whisper_language": "zh",
  "vosk_model_path": "models/vosk-model-small-cn-0.22",
  "r2_account_id": "",
  "r2_bucket": "",
  "llm_type": "doubao",
  "llm_base_url": "https://ark.cn-beijing.volces.com/api/v3",
  "llm_model": "doubao-seed-1-6-flash-250615",
  "output_dir": "speeches",
  "paragraph_gap": 2.0
}
```

---

## TUI 界面布局

```
┌─ Speech Extractor ────────────────────────────────────────────┐
│  Header（标题 + 时间）                                        │
├──────────[识别] [设置]────────────────────────────────────────│
│                                                               │
│  识别 Tab:                                                    │
│  ┌─ 输入文件 ─────────────────────────────────────────────┐  │
│  │  [路径输入框 ...........................]  [浏览]       │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌─ 识别引擎 ──────────┐  ┌─ 后处理模式 ─────────────────┐  │
│  │  ○ Vosk（本地）     │  │  ● 带时间轴字幕（SRT）       │  │
│  │  ● Whisper（本地）  │  │  ○ 合并段落（纯文本）        │  │
│  │  ○ 豆包 ASR（云端） │  │  ○ 整理口述稿（需 LLM）      │  │
│  └────────────────────┘  └──────────────────────────────┘  │
│  ┌─ 引擎选项（动态） ─────────────────────────────────────┐  │
│  │  模型大小: [small ▼]    语言: [zh ▼]                  │  │
│  └───────────────────────────────────────────────────────┘  │
│  输出文件: [speeches/xxx.srt ..........]                     │
│                                          [开始识别] [取消]   │
│  进度: ████████░░ 60%  正在转写...                           │
│  ┌─ 输出预览 ──────────────────────────── [复制] [保存] ──┐  │
│  │  [TextArea - 只读]                                     │  │
│  └───────────────────────────────────────────────────────┘  │
├───────────────────────────────────────────────────────────────│
│  Footer（快捷键提示）                                        │
└───────────────────────────────────────────────────────────────┘
```

设置 Tab 分组：
- **Vosk 设置**：模型路径
- **豆包 ASR 设置**：App ID、Access Token
- **Cloudflare R2 设置**：Account ID、Access Key ID、Secret Access Key、Bucket 名称
- **LLM 设置**：LLM 类型（豆包/OpenAI 兼容）、API Key、Base URL、Model ID
- 按钮：[保存设置]、[测试 ASR 连接]

---

## 键盘快捷键

| 快捷键 | 功能 |
|---|---|
| `Ctrl+Q` | 退出程序 |
| `Ctrl+S` | 保存设置 |
| `F1` | 切换到识别 Tab |
| `F2` | 切换到设置 Tab |
| `Ctrl+C` | 中止识别 |

---

## 技术选型

| 项目 | 选择 | 理由 |
|---|---|---|
| TUI 框架 | **Textual** | 现代、支持鼠标、布局丰富 |
| 本地 ASR | **Vosk** + **openai-whisper** | 互补：Vosk 轻量，Whisper 精度高 |
| 云端 ASR | **豆包大模型录音识别** | 高精度中文，支持方言、标点、说话人分离 |
| 对象存储中转 | **Cloudflare R2**（boto3 S3 兼容） | 免费额度大，用完即删，预签名 URL 安全 |
| LLM 后处理 | **openai SDK**（兼容豆包 LLM + OpenAI） | 统一接口 |
| 密钥存储 | **keyring** | 使用系统级密钥环，不落盘 |
| 项目管理 | **pyproject.toml** + hatchling | 标准 PEP 517/621 |

---

## vosk_reg.py 内部结构（单文件）

```
Section 1: 导入与可用性检测
Section 2: 配置与密钥管理（CONFIG_DIR, load/save_config, get/set_secret）
Section 3: 数据结构（Segment dataclass）+ 音频工具（convert_to_wav, detect_format）
Section 4: 识别后端（VoskBackend, WhisperBackend, DoubaoASRBackend）
Section 5: 字幕后处理（SubtitleProcessor: to_srt, merge_paragraphs, polish_script）
Section 6: Textual TUI（FileBrowserModal, SettingsTab, RecognizeTab, SpeechExtractorApp）
```

---

## 快速开始

```bash
# 安装全部依赖
pip install -e ".[all]"

# 运行
python vosk_reg.py
# 或（安装后）
speech-extract
```

首次运行在设置 Tab 中配置所需凭证，按 Ctrl+S 保存后即可使用。
