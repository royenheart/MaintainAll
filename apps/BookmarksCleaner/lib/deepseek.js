/**
 * DeepSeek API client for Chrome extension.
 * Supports both streaming and non-streaming chat completions.
 */
import { fillPrompt } from './prompts.js';
import { formatBookmarksForStructurePrompt, formatFoldersForStructurePrompt, sanitizeStructurePlan } from './bookmark_organizer.js';

const DEEPSEEK_API_BASE = 'https://api.deepseek.com/v1';

export class DeepSeekClient {
  constructor(apiKey, model = 'deepseek-v4-flash', prompts = null) {
    this.apiKey = apiKey;
    this.model = model;
    this.prompts = prompts || {};
  }

  p(type, fallback) {
    return this.prompts[type] || fallback;
  }

  /**
   * Non-streaming chat completion.
   */
  async chat(messages, opts = {}) {
    const { temperature = 0.3, max_tokens = 2048, response_format = null, thinking = false, reasoning_effort = 'high', signal = null } = opts;
    console.log('[DeepSeek] chat: model=', this.model, 'tokens=', max_tokens, 'msgs=', messages.length);
    const body = {
      model: this.model,
      messages,
      max_tokens,
      stream: false
    };
    if (!thinking) body.temperature = temperature;
    if (response_format) body.response_format = response_format;
    if (thinking) {
      body.reasoning_effort = reasoning_effort;
      body.thinking = { type: 'enabled' };
    }

    const response = await fetch(`${DEEPSEEK_API_BASE}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.apiKey}`
      },
      body: JSON.stringify(body),
      signal
    });

    if (!response.ok) {
      const errBody = await response.text();
      console.error('[DeepSeek] HTTP', response.status, errBody.substring(0, 200));
      throw new Error(`DeepSeek API error ${response.status}: ${errBody.substring(0, 200)}`);
    }

    const data = await response.json();
    console.log('[DeepSeek] response received, tokens:', data.usage?.total_tokens || '?');
    return data;
  }

  /**
   * Streaming chat completion with real-time chunk callback.
   * @param {Array} messages
   * @param {Object} opts - { temperature, max_tokens }
   * @param {Function} onChunk - called with each text delta
   * @param {Function} onThinking - called with reasoning_content chunks (DeepSeek R1)
   * @returns {Promise<string>} full accumulated response
   */
  async chatStream(messages, opts = {}, onChunk, onThinking) {
    const { temperature = 0.3, max_tokens = 4096, response_format = null, thinking = false, reasoning_effort = 'high', signal = null } = opts;
    console.log('[DeepSeek] chatStream: model=', this.model, 'tokens=', max_tokens);
    const body = {
      model: this.model,
      messages,
      max_tokens,
      stream: true,
      stream_options: { include_usage: true }
    };
    if (!thinking) body.temperature = temperature;
    if (response_format) body.response_format = response_format;
    if (thinking) {
      body.reasoning_effort = reasoning_effort;
      body.thinking = { type: 'enabled' };
    }

    const response = await fetch(`${DEEPSEEK_API_BASE}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.apiKey}`
      },
      body: JSON.stringify(body),
      signal
    });

    if (!response.ok) {
      const errBody = await response.text();
      console.error('[DeepSeek] stream HTTP', response.status, errBody.substring(0, 200));
      throw new Error(`DeepSeek API error ${response.status}: ${errBody.substring(0, 200)}`);
    }

    console.log('[DeepSeek] stream started, reading chunks...');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let fullContent = '';
    let fullThinking = '';
    let buffer = '';
    let chunkCount = 0;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith('data:')) continue;
        const data = trimmed.slice(5).trim();
        if (data === '[DONE]') continue;

        try {
          const json = JSON.parse(data);
          const choice = json.choices?.[0];
          if (!choice) continue;

          const delta = choice.delta || {};
          if (delta.reasoning_content) {
            fullThinking += delta.reasoning_content;
            if (onThinking) onThinking(delta.reasoning_content);
          }
          if (delta.content) {
            fullContent += delta.content;
            chunkCount++;
            if (onChunk) onChunk(delta.content);
          }
        } catch {
          // ignore parse errors on malformed chunks
        }
      }
    }

    console.log(`[DeepSeek] stream done: ${chunkCount} chunks, ${fullContent.length} chars`);
    return fullContent;
  }

  /**
   * Analyze bookmark titles and suggest cleaned versions.
   */
  async analyzeTitles(bookmarks, opts = {}) {
    const items = bookmarks.map((b, i) =>
      `[${i}] 标题: "${b.title}"\n    URL: ${b.url}\n    文件夹: ${b.folder}`
    ).join('\n\n');

    const prompt = this.p('titleCleanerUser', '分析书签标题...{items}').replace('{items}', items);

    console.log('[DeepSeek] analyzeTitles: analyzing', bookmarks.length, 'bookmarks');
    const response = await this.chat([
      { role: 'system', content: this.p('titleCleaner', '你是书签标题清理工具，只返回JSON。') },
      { role: 'user', content: prompt }
    ], { temperature: 0.1, max_tokens: 4096, signal: opts.signal });

    const content = response.choices[0].message.content;
    const jsonMatch = content.match(/```(?:json)?\s*([\s\S]*?)\s*```/) || [null, content];
    try {
      return JSON.parse(jsonMatch[1].trim());
    } catch (e) {
      console.error('[DeepSeek] analyzeTitles: JSON parse failed, content:', content.substring(0, 300));
      return [];
    }
  }

  /**
   * Classify bookmarks into categories.
   */
  async classifyBookmarks(bookmarks, opts = {}) {
    const items = bookmarks.map((b, i) =>
      `[${i}] "${b.title}"\n    URL: ${b.url}\n    文件夹: ${b.folder}`
    ).join('\n\n');

    const prompt = this.p('classifyUser', '分类书签...{items}').replace('{items}', items);

    console.log('[DeepSeek] classifyBookmarks: classifying', bookmarks.length, 'bookmarks');
    const response = await this.chat([
      { role: 'system', content: this.p('classify', '你是书签分类工具，只返回JSON。') },
      { role: 'user', content: prompt }
    ], { temperature: 0.1, max_tokens: 4096, signal: opts.signal });

    const content = response.choices[0].message.content;
    const jsonMatch = content.match(/```(?:json)?\s*([\s\S]*?)\s*```/) || [null, content];
    try {
      return JSON.parse(jsonMatch[1].trim());
    } catch (e) {
      console.error('[DeepSeek] classifyBookmarks: JSON parse failed, content:', content.substring(0, 300));
      return [];
    }
  }

  /**
   * Analyze the whole bookmark structure and return a validated organization plan.
   */
  async analyzeBookmarkStructure(bookmarks, folders = [], opts = {}) {
    const items = formatBookmarksForStructurePrompt(bookmarks);
    const folderList = formatFoldersForStructurePrompt(folders.length ? folders : bookmarks) || '无';
    const prompt = this.p('structureOrganizerUser', '整理书签结构...{folders}...{items}')
      .replace('{folders}', folderList)
      .replace('{items}', items);

    console.log('[DeepSeek] analyzeBookmarkStructure: analyzing', bookmarks.length, 'bookmarks');
    const useThinking = this.model === 'deepseek-v4-pro' || this.model === 'deepseek-reasoner';
    const content = await this.chatStream([
      { role: 'system', content: this.p('structureOrganizer', '你是书签结构整理工具，只返回JSON。') },
      { role: 'user', content: prompt }
    ], {
      max_tokens: 8192,
      response_format: { type: 'json_object' },
      thinking: useThinking,
      reasoning_effort: 'high',
      signal: opts.signal
    }, opts.onContent, opts.onThinking);

    try {
      return sanitizeStructurePlan(parseJsonObject(content), bookmarks);
    } catch (e) {
      console.error('[DeepSeek] analyzeBookmarkStructure: JSON parse failed, content:', content.substring(0, 300));
      return { bookmarks: [], folders: [] };
    }
  }

  /**
   * Generate a topic-level summary for a group of tutorial bookmarks.
   */
  async generateTopicSummary(topic, bookmarks, opts = {}) {
    const items = formatTopicBookmarks(bookmarks);

    const prompt = this.p('topicSummaryUser', '为{topic}生成摘要...')
      .replace('{topic}', topic).replace('{items}', items);

    console.log('[DeepSeek] generateTopicSummary:', topic, '(', bookmarks.length, 'items)');
    const response = await this.chat([
      { role: 'system', content: this.p('topicSummary', '你是技术知识库整理助手。') },
      { role: 'user', content: prompt }
    ], { temperature: 0.3, max_tokens: 2048, signal: opts.signal });

    return response.choices[0].message.content;
  }

  /**
   * Generate a topic-level summary with streaming content callbacks.
   */
  async generateTopicSummaryStream(topic, bookmarks, onChunk, onStatus, opts = {}) {
    const items = formatTopicBookmarks(bookmarks);
    const prompt = this.p('topicSummaryUser', '为{topic}生成摘要...')
      .replace('{topic}', topic).replace('{items}', items);

    console.log('[DeepSeek] generateTopicSummaryStream:', topic, '(', bookmarks.length, 'items)');
    let statusSent = false;
    return this.chatStream([
      { role: 'system', content: this.p('topicSummary', '你是技术知识库整理助手。') },
      { role: 'user', content: prompt }
    ], { temperature: 0.35, max_tokens: 4096, signal: opts.signal }, onChunk, () => {
      if (!statusSent && onStatus) {
        statusSent = true;
        onStatus('AI 正在规划章节结构...');
      }
    });
  }
}

function formatTopicBookmarks(bookmarks) {
  return bookmarks.map((b, i) => {
    const folder = Array.isArray(b.path) && b.path.length ? `\n    文件夹: ${b.path.join(' > ')}` : '';
    return `[${i + 1}] "${b.title}"\n    来源: ${b.url}${folder}`;
  }).join('\n\n');
}

function parseJsonObject(content) {
  const text = String(content || '').trim();
  if (!text) throw new Error('empty JSON content');
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
  const raw = (fenced ? fenced[1] : text).trim();
  try {
    return JSON.parse(raw);
  } catch {
    const start = raw.indexOf('{');
    const end = raw.lastIndexOf('}');
    if (start >= 0 && end > start) return JSON.parse(raw.slice(start, end + 1));
    throw new Error('No JSON object found');
  }
}
