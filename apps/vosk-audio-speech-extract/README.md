# vosk-audio-speech-extract

交互式音视频字幕提取工具，基于 **Textual TUI**，支持三种 ASR 后端和三种字幕后处理模式。

---

## 功能概览

### 识别后端

| 后端 | 依赖 | 特点 |
|---|---|---|
| **Vosk（本地）** | `vosk` | 轻量，离线，Kaldi 模型 |
| **Whisper（本地）** | `openai-whisper` | 精度高，支持 tiny / base / small / medium / large |
| **豆包 ASR（云端）** | `boto3`, `requests` | 高精度中文，支持方言、标点、说话人分离 |

缺少某项依赖时，对应选项在界面中自动禁用。

### 字幕后处理

| 模式 | 输出 | 说明 |
|---|---|---|
| 带时间轴字幕（SRT） | `.srt` | 标准 SRT 格式，纯本地生成 |
| 合并段落（纯文本） | `.txt` | 按停顿间隔合并短句，不修改词汇 |
| 整理口述稿（LLM） | `.txt` | 调用 LLM 润色，需配置 API Key |

---

## 安装

需要 Python 3.10+ 和系统已安装 [ffmpeg](https://ffmpeg.org/download.html)。

```bash
# 推荐使用 venv 或者 conda 环境
pip install .
# 可以使用 uv 替代 pip
uv sync
```

---

## 快速开始

```bash
python speech_extractor.py
```

首次使用请先切换到**设置**标签页，填写所需的凭证和路径，按 `Ctrl+S` 保存。

---

## 界面说明

```
┌─ Speech Extractor ────────────────────────────────────────────┐
│  Header（标题 + 时钟）                                        │
├──────────[识别] [设置]────────────────────────────────────────┤
│  ┌─ 输入文件 ─────────────────────────────────────────────┐   │
│  │  [路径输入框 ................................]  [浏览]  │   │
│  └────────────────────────────────────────────────────────┘   │
│  ┌─ 识别引擎 ───────────┐  ┌─ 后处理模式 ──────────────────┐  │
│  │  ○ Vosk（本地）      │  │  ● 带时间轴字幕（SRT）        │  │
│  │  ● Whisper（本地）   │  │  ○ 合并段落（纯文本）         │  │
│  │  ○ 豆包 ASR（云端）  │  │  ○ 整理口述稿（需 LLM）       │  │
│  └─────────────────────┘  └──────────────────────────────┘   │
│  ┌─ 引擎选项 ─────────────────────────────────────────────┐   │
│  │  模型大小: [small ▼]    语言: [zh — 中文 ▼]            │   │
│  └────────────────────────────────────────────────────────┘   │
│  输出文件: [speeches/filename_srt.srt .................]      │
│                                         [开始识别]  [取消]    │
│  ████████████░░░░░░░░  60%  正在转写（Whisper）...            │
│  ┌─ 输出预览 ─────────────────────────── [复制]  [保存] ──┐   │
│  │  （识别结果实时显示）                                   │   │
│  └────────────────────────────────────────────────────────┘   │
├───────────────────────────────────────────────────────────────┤
│  Footer（快捷键提示）                                         │
└───────────────────────────────────────────────────────────────┘
```

### 设置标签页分组

- **Vosk 设置**：本地模型路径
- **豆包 ASR 设置**：App ID、Access Token
- **Cloudflare R2 设置**：Account ID、Access Key ID、Secret Access Key、Bucket 名称
- **LLM 设置**：类型（豆包 / OpenAI 兼容）、API Key、Base URL、Model ID

---

## 键盘快捷键

| 快捷键 | 功能 |
|---|---|
| `F1` | 切换到识别标签页 |
| `F2` | 切换到设置标签页 |
| `Ctrl+S` | 保存设置 |
| `Ctrl+C` | 中止当前识别 |
| `Ctrl+Q` | 退出程序 |

---

## 配置说明

### 非敏感配置

存储在 `~/.vosk_speech/config.json`，首次运行自动创建：

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

### 密钥

使用系统密钥环（Windows Credential Manager / macOS Keychain / Linux Secret Service）存储，不落盘，不进版本管理。通过设置标签页填写后自动保存。

| 键名 | 说明 |
|---|---|
| `doubao_asr_app_id` | 豆包 ASR App ID |
| `doubao_asr_access_token` | 豆包 ASR Access Token |
| `r2_access_key_id` | Cloudflare R2 Access Key ID |
| `r2_secret_access_key` | Cloudflare R2 Secret Access Key |
| `doubao_llm_api_key` | 豆包 LLM API Key |
| `openai_api_key` | OpenAI 兼容 API Key |

---

## 豆包 ASR 使用说明

豆包 ASR 需要公网可访问的音频 URL，本地文件会经以下流程处理后提交：

```
本地文件
  → ffmpeg 转 WAV（如需）
  → 上传到 Cloudflare R2
  → 生成预签名 URL（有效期 3600s）
  → 提交豆包 ASR 任务
  → 轮询识别结果（每 2s）
  → 解析 utterances
  → 删除 R2 临时文件
```

需要在设置中填写：
1. 豆包 ASR 的 App ID 和 Access Token（[豆包控制台](https://console.volcengine.com/speech/app)）
2. Cloudflare R2 的 Account ID、Access Key ID、Secret Access Key 和 Bucket 名称

---

## Vosk 模型下载

从 [https://alphacephei.com/vosk/models](https://alphacephei.com/vosk/models) 下载模型，解压后放入 `models/` 目录，在设置中填写路径。

推荐中文模型：

| 模型 | 大小 | 说明 |
|---|---|---|
| `vosk-model-small-cn-0.22` | 42 MB | 轻量，速度快 |
| `vosk-model-cn-0.22` | 1.3 GB | 精度更高 |

---

## 文件结构

```
vosk-audio-speech-extract/
├── speech_extractor.py  # 单文件主程序（Textual TUI）
├── pyproject.toml       # 项目元数据与依赖
└──  README.md
```

## TODO

- [ ] 提供模型、对象存储配置的教程网站
- [ ] 使用 RAG / LLM 构造术语表