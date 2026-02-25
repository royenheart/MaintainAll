# MaintainAll TUI — 方案文档

## 目标

在仓库顶层提供一个单文件 Python TUI（`maintain.py`），以类似 AI Agent 的方式帮助用户：

- 快速浏览仓库中的配置模板/部署脚本
- 通过自然语言问答获取部署/命令/配置参考
- 交互式填充配置模板中的占位符变量
- 搜索并参考仓库中的关键命令片段

---

## 技术选型

| 项目 | 选择 | 理由 |
|---|---|---|
| TUI 框架 | **Textual** | 现代、支持鼠标、布局丰富，社区活跃 |
| LLM 客户端 | **openai** SDK（可选依赖） | 兼容 OpenAI 接口的国内 API（DeepSeek、Qwen、SiliconFlow 等）均可直接对接 |
| RAG 检索 | **纯 Python TF-IDF**（不引入 sklearn） | 仓库内容以配置文件和 shell 脚本为主，关键词匹配已足够，零额外依赖 |

### 最小依赖

```
textual>=0.47    # TUI 框架（必需）
openai>=1.0     # LLM 调用（可选，不配置时自动降级为纯检索模式）
```

---

## 整体布局

```
┌──────────────────────────────────────────────────────────────┐
│  MaintainAll  [浏览] [对话] [命令参考] [模板填充]   ⚙ 设置  │
├─────────────────────┬────────────────────────────────────────┤
│                     │                                        │
│  📁 仓库导航树      │   内容 / 对话区                        │
│  ├ apps/            │                                        │
│  ├ deploy/          │   （根据 Tab 切换展示内容）             │
│  ├ maintaince/      │                                        │
│  ├ scripts/         │                                        │
│  ├ stow-configs/    │                                        │
│  └ templates/       │                                        │
│                     │                                        │
├─────────────────────┴────────────────────────────────────────┤
│  状态栏 / 快捷键提示                                         │
└──────────────────────────────────────────────────────────────┘
```

左侧为始终可见的仓库文件导航树（`Tree` 组件），右侧根据顶部 Tab 切换不同功能面板。

---

## 四大功能模块

### 1. 浏览（Browse）

- 左侧 `Tree` 组件展示仓库完整目录结构，支持展开/折叠
- 点击文件后，右侧内容区显示带语法高亮的文件内容（Textual 内置 `SyntaxHighlighter`）
- 支持格式：`.md`、`.sh`、`.py`、`.yml`、`.yaml`、`.toml`、`.conf`、`.j2`、`.service` 等

### 2. AI 对话（Chat）

**RAG 流程（含 API 配置时）**：

1. 启动时后台扫描仓库所有文本文件，构建纯 Python TF-IDF 索引
2. 用户提问时，计算问题与各文件片段的余弦相似度，检索 Top-K 相关片段
3. 将检索到的上下文 + 用户问题拼装为 `system prompt` 发送给 LLM
4. 支持流式输出（`stream=True`），逐字显示回复

**降级模式（无 API 配置时）**：

- 根据 TF-IDF 检索展示最相关的文件列表，引导用户手动查看

**对话特性**：

- 保持多轮对话历史
- 支持清空对话
- 可在对话中直接引用仓库文件路径

### 3. 命令参考（Commands）

- 扫描仓库所有 shell/Python 脚本
- 提取每个脚本的：
  - 名称 + 所在路径
  - 头部注释（用途说明）
  - 关键命令行（`docker`、`ansible`、`systemctl`、`kubectl`、`ansible-playbook` 等）
- 展示为可实时搜索/过滤的列表
- 点击条目展开完整脚本内容 + 高亮关键命令

### 4. 模板填充（Templates）

**自动检测可填充模板**，识别以下特征：

- 文件名含 `.example`（如 `jupyterhub_config.example.py`）
- Jinja2 占位符 `{{ variable }}` / `{% for ... %}`（`.j2` 文件）
- 明显的占位符：`xxx`、`your_xxx`、`<placeholder>`、`CHANGE_ME`

**填充流程**：

1. 自动解析占位符，生成对应的输入表单
2. 用户逐一填写变量值
3. 实时预览替换后的内容
4. 可一键复制到剪贴板或保存为新文件

---

## 配置文件

路径：`~/.maintainall.json`

首次运行时会交互式引导生成，内容示例：

```json
{
  "api_base": "https://api.deepseek.com/v1",
  "api_key": "sk-...",
  "model": "deepseek-chat",
  "repo_path": "/path/to/MaintainAll",
  "rag_top_k": 5,
  "rag_chunk_size": 500
}
```

| 字段 | 说明 | 是否必需 |
|---|---|---|
| `api_base` | LLM API 基础 URL（兼容 OpenAI 接口） | 否（不填则降级） |
| `api_key` | API 密钥 | 否（不填则降级） |
| `model` | 模型名称 | 否（默认 `gpt-4o-mini`） |
| `repo_path` | 仓库根目录绝对路径 | 否（默认为脚本所在目录） |
| `rag_top_k` | RAG 检索返回的最大片段数 | 否（默认 5） |
| `rag_chunk_size` | 文件分块大小（行数） | 否（默认 100） |

---

## 文件结构

```
MaintainAll/
├── maintain.py      # 单一入口，所有逻辑集中于此
├── AGENTS.md        # 本文档
└── ...              # 现有仓库内容
```

---

## 快速开始

```bash
# 安装依赖
pip install textual
pip install openai   # 可选，需要 AI 对话功能时安装

# 运行
python maintain.py
```

首次运行会提示配置 API（可跳过），之后直接进入 TUI 界面。

---

## 键盘快捷键

| 快捷键 | 功能 |
|---|---|
| `Tab` / `Shift+Tab` | 切换功能面板 |
| `Ctrl+Q` | 退出程序 |
| `Ctrl+F` | 在当前面板中搜索/过滤 |
| `Ctrl+L` | 清空对话记录 |
| `Ctrl+S` | 保存模板填充结果 |
| `F1` | 打开设置面板 |
| `Escape` | 关闭弹窗/返回上级 |
