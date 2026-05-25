# Bookmarks Cleaner — Chrome 书签整理插件

AI 驱动的浏览器书签清理工具。标准化标题、生成知识库、备份同步。

## 功能

- **标题标准化**：自动移除 `- 知乎`、`- 博客园`、`- CSDN` 等平台后缀
- **智能分类**：识别娱乐/游戏内容（默认不动）、标记教程文章
- **知识库生成**：从教程书签中提取知识点，AI 生成结构化摘要，渲染为 Markdown 在侧边栏浏览，支持导出 `.md` 到本地
- **WebDAV 同步**：知识库可同步到 WebDAV 服务器（如 NextCloud、ownCloud、群晖）
- **AI 辅助**：可选接入 DeepSeek API，智能分析标题和生成知识摘要
- **自动备份**：修改前自动导出书签 HTML 到本地下载
- **排除文件夹**：可配置特定文件夹完全跳过
- **预览模式**：先预览标题修改，确认后再执行

## 安装

1. 打开 Chrome，进入 `chrome://extensions/`
2. 开启右上角「开发者模式」
3. 点击「加载已解压的扩展程序」
4. 选择 `apps/BookmarksCleaner` 目录
5. 点击工具栏扩展图标打开侧边栏

## 使用

### 侧边栏三面板

| 面板 | 功能 |
|------|------|
| 📑 书签整理 | 预览修改、开始清理、仅备份 |
| 📚 知识库 | 生成知识库、浏览 Markdown 渲染内容、导出 .md、同步到 WebDAV |
| ⚙ 设置 | API Key、排除文件夹、WebDAV 配置、开关控制 |

### 基础使用（不需要 API Key）

1. 点 **👁 预览** 查看标题变化
2. 点 **💾 仅备份** 导出书签
3. 点 **🚀 开始整理** 执行标题标准化

### AI 增强使用

1. 在设置面板填入 DeepSeek API Key
2. 开启「AI 分析」开关
3. 保存设置
4. 点 **🚀 开始整理**：标题标准化 + 知识库自动生成
5. 切换到 **📚 知识库** 面板查看 AI 生成的摘要
6. 点 **📥 导出 .md** 下载到本地

### WebDAV 同步

1. 在设置面板填写 WebDAV 服务器 URL、用户名、密码
2. 点 **🔍 测试连接** 验证配置
3. 在知识库面板点 **☁ 同步到 WebDAV** 上传

## 设置说明

| 设置项 | 说明 | 默认值 |
|--------|------|--------|
| API Key | DeepSeek API 密钥 | 空 |
| 模型 | 模型名称 | `deepseek-v4-flash` |
| 排除文件夹 | 不处理的文件夹 | `娱乐` |
| AI 分析 | 调用 AI 分析标题 | 关闭 |
| 自动备份 | 修改前自动下载备份 | 开启 |
| 标准化标题 | 清理标题后缀 | 开启 |
| WebDAV URL | 服务器地址 | 空 |
| WebDAV 用户名 | 用户名 | 空 |
| WebDAV 密码 | 密码 | 空 |

## 标题标准化规则

移除：`- 知乎`、`- 博客园`、`- CSDN`、`- 简书`、`- 掘金`、`- 51CTO`、`- Stack Overflow`、`- GitHub`、`- DEV Community`、过长版本后缀、博客作者前缀等。

## 知识库生成流程

1. 扫描所有书签，识别教程类文章（cnblogs/CSDN/Zhihu/Jianshu 等平台）
2. 按顶级文件夹分组
3. 调用 DeepSeek API 对每组生成知识点摘要（核心方法、命令、概念）
4. 存储为 Markdown，可在侧边栏渲染浏览
5. 支持导出 `.md` 到本地，或同步到 WebDAV

## 文件结构

```
BookmarksCleaner/
├── manifest.json          # MV3 配置
├── background.js           # Service Worker
├── sidepanel.html          # 侧边栏（三面板）
├── sidepanel.js            # 侧边栏逻辑
├── settings.html           # 独立设置页
├── settings.js             # 设置逻辑
├── lib/
│   ├── deepseek.js         # DeepSeek API 客户端
│   ├── title_cleaner.js    # 标题标准化引擎
│   ├── knowledge_base.js   # 知识库生成/存储/导出
│   ├── webdav.js           # WebDAV 客户端 (PUT/GET/PROPFIND)
│   └── markdown_renderer.js # Markdown → HTML 渲染
└── icons/
    └── icon128.png
```

## 技术

- Manifest V3
- ES Modules in Service Worker
- Chrome Side Panel API
- DeepSeek API（可选）
- WebDAV 协议（PROPFIND/PUT/GET/DELETE）
- `optional_host_permissions` — 用户首次连接 WebDAV 时由 Chrome 弹出原生对话框逐站点授权
- chrome.storage.local 存储密码/API Key，chrome.storage.sync 存储偏好设置
