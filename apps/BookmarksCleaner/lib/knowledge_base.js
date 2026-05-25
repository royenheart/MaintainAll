/**
 * Knowledge Base engine.
 * Generates markdown summaries from tutorial bookmarks,
 * stores in chrome.storage.local, supports export.
 */

const KB_STORAGE_KEY = 'knowledge_base';

/**
 * Generate a knowledge base from classified bookmarks.
 * Groups tutorial bookmarks by folder topic, optionally uses AI for summaries.
 * @param {Array<{title:string, url:string, path:string[], isTutorial:boolean}>} bookmarks
 * @param {Object} options - { useAI, deepseekClient, onProgress }
 * @returns {Promise<{markdown: string, stats: Object}>}
 */
export async function generateKnowledgeBase(bookmarks, options = {}) {
  const tutorialBookmarks = bookmarks.filter(b => b.isTutorial);
  if (tutorialBookmarks.length === 0) {
    return { markdown: '', stats: { total: 0, groups: 0, aiSummaries: 0 } };
  }

  const reportProgress = typeof options.onProgress === 'function' ? options.onProgress : () => {};

  // Group by top-level folder
  const groups = {};
  for (const bm of tutorialBookmarks) {
    const topic = bm.path[0] || '未分类';
    if (!groups[topic]) groups[topic] = [];
    groups[topic].push(bm);
  }
  const sortedGroups = Object.entries(groups).sort(([a], [b]) => a.localeCompare(b, 'zh-CN'));

  const lines = [];
  lines.push('# 技术知识库');
  lines.push('');
  lines.push('> 从浏览器书签中的教程文章自动提取。由 Bookmarks Cleaner 插件生成。');
  lines.push('> 生成时间: ' + new Date().toLocaleString('zh-CN'));
  lines.push('');
  lines.push('## 目录');
  lines.push('');
  for (const [topic, items] of sortedGroups) {
    lines.push(`- ${topic}（${items.length} 篇）`);
  }
  lines.push('');

  let aiCount = 0;
  reportProgress({
    phase: 'kb_prepare',
    message: `已识别 ${tutorialBookmarks.length} 篇教程，分为 ${sortedGroups.length} 个章节`,
    done: 0,
    total: sortedGroups.length,
    markdown: lines.join('\n')
  });

  for (let groupIndex = 0; groupIndex < sortedGroups.length; groupIndex++) {
    const [topic, items] = sortedGroups[groupIndex];
    lines.push(`## ${topic}`);
    lines.push('');
    lines.push(`本章收录 ${items.length} 篇相关书签，主要来自 ${summarizeSources(items)}。`);
    lines.push('');

    reportProgress({
      phase: 'kb_topic',
      message: `正在生成章节: ${topic} (${groupIndex + 1}/${sortedGroups.length})`,
      topic,
      done: groupIndex,
      total: sortedGroups.length,
      markdown: lines.join('\n')
    });

    if (options.useAI && options.deepseekClient) {
      // Use AI to summarize this group
      try {
        let summary = '';
        if (typeof options.deepseekClient.generateTopicSummaryStream === 'function') {
          summary = await options.deepseekClient.generateTopicSummaryStream(topic, items, (delta) => {
            summary += delta;
            reportProgress({
              phase: 'kb_stream',
              message: `AI 正在写入「${topic}」正文...`,
              topic,
              delta,
              done: groupIndex,
              total: sortedGroups.length,
              markdown: [...lines, summary].join('\n')
            });
          }, (message) => {
            reportProgress({
              phase: 'kb_stream',
              message,
              topic,
              done: groupIndex,
              total: sortedGroups.length,
              markdown: [...lines, summary].join('\n')
            });
          }, { signal: options.signal });
        } else {
          summary = await options.deepseekClient.generateTopicSummary(topic, items, { signal: options.signal });
        }

        if (summary.trim()) {
          lines.push(summary.trim());
        } else {
          appendChapterFallback(lines, topic, items);
        }
        lines.push('');
        aiCount++;
      } catch (err) {
        const msg = String(err).substring(0, 150);
        console.error(`AI summary failed for ${topic}:`, msg);
        appendChapterFallback(lines, topic, items);
      }
    } else {
      appendChapterFallback(lines, topic, items);
    }

    // Add reference links
    lines.push('### 参考链接');
    lines.push('');
    for (const item of items) {
      lines.push(`- [${item.title}](${item.url})`);
    }
    lines.push('');

    reportProgress({
      phase: 'kb_topic_done',
      message: `章节完成: ${topic}`,
      topic,
      done: groupIndex + 1,
      total: sortedGroups.length,
      markdown: lines.join('\n')
    });
  }

  const markdown = lines.join('\n');
  const stats = {
    total: tutorialBookmarks.length,
    groups: Object.keys(groups).length,
    aiSummaries: aiCount
  };

  return { markdown, stats };
}

function appendChapterFallback(lines, topic, items) {
  const keywords = collectKeywords(topic, items);
  lines.push('### 本章导读');
  lines.push('');
  lines.push(`- 这一章围绕「${topic}」整理，覆盖 ${items.length} 篇教程或经验文章。`);
  lines.push(`- 适合先按标题建立索引，再打开原文补齐细节；关键词包括：${keywords.join('、') || topic}。`);
  lines.push('');

  lines.push('### 核心概念');
  lines.push('');
  for (const item of items.slice(0, 8)) {
    lines.push(`- **${item.title}**：从标题看，适合作为「${topic}」下的一个知识点入口；具体结论待阅读原文确认。`);
  }
  if (items.length > 8) lines.push(`- 另有 ${items.length - 8} 篇相关材料可作为补充阅读。`);
  lines.push('');

  lines.push('### 实践路径');
  lines.push('');
  lines.push('- 先阅读入门、安装、配置类条目，建立环境和基本术语。');
  lines.push('- 再阅读问题排查、性能优化、源码分析或案例类条目，把知识点落到实际任务中。');
  lines.push('- 对命令、配置项和 API 名称建立单独笔记，后续可从参考链接回溯原文。');
  lines.push('');

  lines.push('### 易错点与检查清单');
  lines.push('');
  lines.push('- 标题相近的文章可能覆盖不同版本、平台或上下文，使用前需要确认原文发布日期和适用范围。');
  lines.push('- 涉及命令和配置的内容不要直接复制执行，先核对路径、权限、版本号和环境变量。');
  lines.push('- 如果文章来自博客平台，优先把结论与官方文档或源码行为交叉验证。');
  lines.push('');

  lines.push('### 延伸问题');
  lines.push('');
  lines.push(`- 「${topic}」中哪些条目适合沉淀为命令速查或配置模板？`);
  lines.push('- 哪些文章解决的是同一个问题，是否可以合并成一条更稳定的操作流程？');
  lines.push('- 哪些链接需要补充官方文档、版本说明或更权威的参考来源？');
  lines.push('');
}

function appendSimpleList(lines, topic, items) {
  if (items.length <= 2) {
    for (const item of items) {
      lines.push(`### ${item.title}`);
      lines.push('');
      lines.push(`来源: ${item.url}`);
      lines.push('');
    }
  } else {
    lines.push(`本组包含 ${items.length} 篇文章：`);
    lines.push('');
    for (const item of items) {
      lines.push(`- ${item.title}`);
    }
    lines.push('');
  }
}

function summarizeSources(items) {
  const domains = [...new Set(items.map(item => {
    try {
      return new URL(item.url).hostname.replace(/^www\./, '');
    } catch {
      return '未知来源';
    }
  }))].slice(0, 5);
  return domains.join('、') || '多个来源';
}

function collectKeywords(topic, items) {
  const stopWords = new Set(['the', 'and', 'with', 'from', 'http', 'https', 'www', 'com', 'cn', 'html']);
  const text = [topic, ...items.map(i => i.title)].join(' ');
  const tokens = text.match(/[A-Za-z][A-Za-z0-9_+.-]{1,}|[\u4e00-\u9fa5]{2,}/g) || [];
  const counts = new Map();
  for (const token of tokens) {
    const key = token.trim();
    if (!key || stopWords.has(key.toLowerCase())) continue;
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'zh-CN'))
    .slice(0, 8)
    .map(([key]) => key);
}

/**
 * Save knowledge base to chrome.storage.local.
 */
export async function saveKnowledgeBase(markdown, stats = {}) {
  const normalizedStats = normalizeKnowledgeBaseStats(markdown, stats);
  const entry = {
    markdown,
    stats: normalizedStats,
    updatedAt: new Date().toISOString(),
    version: 2
  };
  await chrome.storage.local.set({ [KB_STORAGE_KEY]: entry });
  return entry;
}

/**
 * Load knowledge base from chrome.storage.local.
 */
export async function loadKnowledgeBase() {
  const data = await chrome.storage.local.get(KB_STORAGE_KEY);
  const entry = data[KB_STORAGE_KEY] || null;
  if (!entry) return null;
  return {
    ...entry,
    stats: normalizeKnowledgeBaseStats(entry.markdown || '', entry.stats || {})
  };
}

/**
 * Export knowledge base as a downloadable .md file.
 */
export async function exportKnowledgeBase(markdown) {
  const encoded = btoa(unescape(encodeURIComponent(markdown)));
  const url = `data:text/markdown;base64,${encoded}`;

  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').substring(0, 19);
  const filename = `knowledge_base_${timestamp}.md`;

  await chrome.downloads.download({
    url,
    filename,
    saveAs: false
  });

  return filename;
}

/**
 * Parse markdown into sections keyed by ## heading.
 * @param {string} markdown
 * @returns {Map<string, string>} headingText -> section body
 */
export function parseSections(markdown) {
  const sections = new Map();
  if (!markdown) return sections;

  const lines = markdown.split('\n');
  let currentHeading = '';
  let currentBody = [];

  for (const line of lines) {
    if (line.startsWith('## ')) {
      if (currentHeading) {
        sections.set(currentHeading, currentBody.join('\n').trim());
      }
      currentHeading = line.substring(3).trim();
      currentBody = [line];
    } else {
      currentBody.push(line);
    }
  }
  if (currentHeading) {
    sections.set(currentHeading, currentBody.join('\n').trim());
  }

  return sections;
}

export function normalizeKnowledgeBaseStats(markdown, stats = {}) {
  const sections = parseSections(markdown);
  const groups = [...sections.keys()].filter(heading => heading !== '目录').length;
  const linkCount = countReferenceLinks(markdown);
  return {
    ...stats,
    total: Number(stats.total) > 0 ? Number(stats.total) : linkCount,
    groups: Number(stats.groups) > 0 ? Number(stats.groups) : groups,
    updatedAt: stats.updatedAt
  };
}

/**
 * Merge local and remote knowledge bases by ## sections.
 * Strategy: local wins on conflicts; new remote sections are appended.
 * @param {string} localMd - local KB markdown
 * @param {string} remoteMd - remote KB markdown
 * @returns {{merged: string, stats: {localSections: number, remoteSections: number, addedFromRemote: number}}}
 */
export function mergeKnowledgeBases(localMd, remoteMd) {
  if (!localMd) return { merged: remoteMd, stats: { ...normalizeKnowledgeBaseStats(remoteMd), localSections: 0, remoteSections: parseSections(remoteMd).size, addedFromRemote: 0 } };
  if (!remoteMd) return { merged: localMd, stats: { ...normalizeKnowledgeBaseStats(localMd), localSections: parseSections(localMd).size, remoteSections: 0, addedFromRemote: 0 } };

  const localSections = parseSections(localMd);
  const remoteSections = parseSections(remoteMd);

  let addedFromRemote = 0;
  const mergedLines = [];

  // Start with preamble (everything before first ##)
  const localPreamble = getPreamble(localMd);
  if (localPreamble) mergedLines.push(localPreamble, '');

  // Add local sections first
  for (const [heading, body] of localSections) {
    mergedLines.push(body, '');
  }

  // Add remote sections not in local
  for (const [heading, body] of remoteSections) {
    if (!localSections.has(heading)) {
      mergedLines.push(body, '');
      addedFromRemote++;
    }
  }

  const merged = mergedLines.join('\n').trim();
  const stats = {
    ...normalizeKnowledgeBaseStats(merged),
    localSections: localSections.size,
    remoteSections: remoteSections.size,
    addedFromRemote
  };

  return { merged, stats };
}

function getPreamble(md) {
  const lines = [];
  for (const line of md.split('\n')) {
    if (line.startsWith('## ')) break;
    lines.push(line);
  }
  const result = lines.join('\n').trim();
  return result || null;
}

function countReferenceLinks(markdown) {
  if (!markdown) return 0;
  const referenceBlocks = markdown.match(/### 参考链接[\s\S]*?(?=\n## |\n### (?!参考链接)|$)/g) || [];
  const text = referenceBlocks.length ? referenceBlocks.join('\n') : markdown;
  const links = text.match(/^\s*[-*]\s+\[[^\]]+\]\([^)]+\)/gm) || [];
  return links.length;
}
