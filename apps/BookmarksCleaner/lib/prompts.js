/**
 * Default prompts for DeepSeek API calls.
 * Users can customize these in settings.
 */

export const DEFAULT_PROMPTS = {
  /** System prompt for title cleaning analysis */
  titleCleaner: `你是一个专业的书签标题清理工具。只返回JSON，不要额外解释。`,

  /** User prompt template for title analysis — {items} will be replaced */
  titleCleanerUser: `你是一个书签整理助手。分析以下浏览器书签标题，对每个标题给出清理建议。

清理规则：
1. 移除平台后缀（如" - 知乎"、" - 博客园"、" - CSDN"、" - 简书"、" - 掘金"等）
2. 移除作者名前缀（如"xxx的博客 - "）
3. 移除重复/冗余的描述
4. 标题保持简短（不超过50字），但要能准确表达内容
5. 不要改变原标题的核心含义

请以JSON格式返回，格式如下：
\`\`\`json
[
  {"index": 0, "cleaned": "清理后标题", "reason": "移除知乎后缀"},
  ...
]
\`\`\`
对于不需要修改的标题，cleaned字段设为原标题，reason为"无需修改"。

需要分析的书签：
{items}`,

  /** System prompt for bookmark classification */
  classify: `你是书签分类工具。只返回JSON数组，不要解释。`,

  /** User prompt for bookmark classification */
  classifyUser: `分析以下书签，将它们分类：

分类选项：
- "entertainment": 游戏、动漫、漫画、NSFW、fanbox、patreon、pixiv、视频网站等娱乐内容
- "tutorial": 博客教程、CSDN/知乎/博客园/简书等平台的教程文章、命令参考说明
- "reference": 官方文档、API参考、标准规范、权威技术资料
- "tool": 开发工具、在线工具、实用网站

返回JSON格式：
\`\`\`json
[
  {"index": 0, "category": "reference", "reason": "LLVM官方IR文档"},
  ...
]
\`\`\`

  书签列表：
{items}`,

  /** System prompt for full bookmark structure organization */
  structureOrganizer: `你是一个专业的浏览器书签结构整理工具。目标是让书签管理器只保留长期有用、分类清晰、可快速定位的入口。只返回JSON，不要额外解释。`,

  /** User prompt for full bookmark structure organization — {folders} and {items} will be replaced */
  structureOrganizerUser: `请根据当前文件夹结构和书签列表，生成一份可执行的书签结构整理计划。必须输出合法 JSON 对象。

整理目标：
1. 不只是修标题，还要判断书签应该移动到哪个更合适的分类
2. 可以建议合并含义重复、层级过深或命名不清晰的分类
3. 可以建议重命名分类，让分类语义更短、更稳定
4. 教程、入门、博客笔记、简单命令说明这类适合沉淀到知识库的条目，请标记为 delete_after_kb；它们进入知识库后不再保留在书签管理器
5. 明显过时、过简单、低价值的入口可以标记为 delete，但 confidence 必须 >= 0.85
6. 官方文档、工具首页、权威参考、仍需频繁打开的项目页面应保留或移动，而不是删除
7. 不确定时选择 keep，并在 reason 中说明需要人工确认
8. 为了避免 JSON 过长，bookmarks 数组只输出需要变更的条目；保持不变的书签不要输出 keep 项

已有分类：
{folders}

返回JSON格式：
\`\`\`json
{
  "folders": [
    {
      "action": "rename",
      "fromPath": ["Bookmarks Bar", "旧分类"],
      "toPath": ["Bookmarks Bar", "新分类"],
      "reason": "命名更清晰",
      "confidence": 0.9
    },
    {
      "action": "merge",
      "fromPath": ["Bookmarks Bar", "零散教程"],
      "toPath": ["Bookmarks Bar", "知识库候选"],
      "reason": "含义重复",
      "confidence": 0.86
    }
  ],
  "bookmarks": [
    {
      "index": 0,
      "decision": "move_rename",
      "newTitle": "清晰标题",
      "targetPath": ["Bookmarks Bar", "开发工具"],
      "reason": "移动到工具类并缩短标题",
      "confidence": 0.82
    },
    {
      "index": 1,
      "decision": "delete_after_kb",
      "reason": "教程文章适合进入知识库，书签中无需长期保存",
      "confidence": 0.9
    }
  ]
}
\`\`\`

decision 只能使用 keep、rename、move、move_rename、delete_after_kb、delete。
targetPath 使用分类路径数组；可以复用已有分类，也可以给出新的稳定分类。

书签列表：
{items}`,

  /** System prompt for topic summarization in knowledge base */
  topicSummary: `你是技术知识库整理助手。根据书签标题提炼结构化、可复习的章节式知识笔记。不要输出隐藏推理过程，只输出最终 Markdown 正文。`,

  /** User prompt for topic summarization — {topic} and {items} will be replaced */
  topicSummaryUser: `你是一个技术知识库自动整理工具。根据以下关于「{topic}」的书签标题列表，生成一份分章节的知识库正文。

要求：
1. 使用 Markdown，必须包含这些小节标题：### 本章导读、### 核心概念、### 实践路径、### 易错点与检查清单、### 延伸问题
2. 根据标题和 URL 合理归纳主题脉络；不确定的事实要写成“待阅读原文确认”，不要编造具体结论
3. 如果标题明确涉及命令、配置、代码或 API，可以给出简短代码块；没有明确证据时不要硬写代码
4. 每个小节至少 2 个要点；整体尽量充实，建议 800-1400 中文字
5. 不要列出原文链接（链接会由程序自动添加）
6. 使用中文，保持技术术语的英文

书签列表：
{items}

直接输出 Markdown 摘要，不要添加解释性文字。`,
};

/**
 * Fill placeholders in a prompt template.
 * @param {string} template
 * @param {Object} vars - key-value replacements
 * @returns {string}
 */
export function fillPrompt(template, vars) {
  let result = template;
  for (const [key, value] of Object.entries(vars)) {
    result = result.replace(new RegExp(`\\{${key}\\}`, 'g'), value);
  }
  return result;
}
