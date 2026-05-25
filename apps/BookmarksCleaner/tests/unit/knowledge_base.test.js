import { describe, test, expect, beforeEach } from '@jest/globals';
import '../__mocks__/chrome.js';
import { resetChromeStorage } from '../__mocks__/chrome.js';

let generateKnowledgeBase, saveKnowledgeBase, loadKnowledgeBase, normalizeKnowledgeBaseStats;

beforeAll(async () => {
  const mod = await import('../../lib/knowledge_base.js');
  ({ generateKnowledgeBase, saveKnowledgeBase, loadKnowledgeBase, normalizeKnowledgeBaseStats } = mod);
});

beforeEach(() => {
  resetChromeStorage();
});

describe('generateKnowledgeBase', () => {
  test('generates markdown from tutorial bookmarks', async () => {
    const bookmarks = [
      { id: '1', title: 'LLVM入门教程', url: 'https://zhuanlan.zhihu.com/p/1', path: ['编译技术'], isTutorial: true },
      { id: '2', title: 'Clang优化选项', url: 'https://www.cnblogs.com/p/2', path: ['编译技术'], isTutorial: true },
      { id: '3', title: 'GCC编译选项', url: 'https://cloud.tencent.com/developer/article/3', path: ['编译技术'], isTutorial: true },
      { id: '4', title: 'Rust入门', url: 'https://blog.csdn.net/p/4', path: ['Rust'], isTutorial: true },
      { id: '5', title: 'Serde文档', url: 'https://serde.rs', path: ['Rust'], isTutorial: false }, // not tutorial
    ];

    const { markdown, stats } = await generateKnowledgeBase(bookmarks);
    expect(markdown).toContain('# 技术知识库');
    expect(markdown).toContain('## 编译技术');
    expect(markdown).toContain('## Rust');
    expect(markdown).toContain('### 本章导读');
    expect(markdown).toContain('### 核心概念');
    expect(markdown).toContain('### 实践路径');
    expect(markdown).toContain('[LLVM入门教程](https://zhuanlan.zhihu.com/p/1)');
    expect(stats.total).toBe(4); // 4 tutorial bookmarks
    expect(stats.groups).toBe(2); // 2 groups: 编译技术, Rust
  });

  test('returns empty for no tutorial bookmarks', async () => {
    const bookmarks = [
      { id: '1', title: 'Docs', url: 'https://docs.rs', path: ['Rust'], isTutorial: false },
    ];
    const { markdown, stats } = await generateKnowledgeBase(bookmarks);
    expect(markdown).toBe('');
    expect(stats.total).toBe(0);
  });

  test('groups by top-level folder', async () => {
    const bookmarks = [
      { id: '1', title: 'a', url: 'https://1.com', path: ['OS'], isTutorial: true },
      { id: '2', title: 'b', url: 'https://2.com', path: ['OS', '子文件夹'], isTutorial: true },
      { id: '3', title: 'c', url: 'https://3.com', path: ['HPC'], isTutorial: true },
    ];
    const { stats } = await generateKnowledgeBase(bookmarks);
    expect(stats.groups).toBe(2); // OS and HPC
  });

  test('emits streaming progress while AI writes chapter content', async () => {
    const bookmarks = [
      { id: '1', title: 'Docker Compose 教程', url: 'https://example.com/1', path: ['DevOps'], isTutorial: true },
      { id: '2', title: 'Kubernetes 入门', url: 'https://example.com/2', path: ['DevOps'], isTutorial: true },
    ];
    const events = [];
    const deepseekClient = {
      async generateTopicSummaryStream(topic, items, onChunk) {
        onChunk('### 本章导读\n\n- DevOps 入门路线。\n');
        onChunk('\n### 核心概念\n\n- 容器编排与服务配置。\n');
        return '### 本章导读\n\n- DevOps 入门路线。\n\n### 核心概念\n\n- 容器编排与服务配置。';
      },
    };

    const { markdown, stats } = await generateKnowledgeBase(bookmarks, {
      useAI: true,
      deepseekClient,
      onProgress: event => events.push(event),
    });

    expect(stats.aiSummaries).toBe(1);
    expect(markdown).toContain('### 本章导读');
    expect(markdown).toContain('### 核心概念');
    expect(events.some(e => e.phase === 'kb_stream' && e.markdown.includes('DevOps 入门路线'))).toBe(true);
    expect(events.some(e => e.phase === 'kb_topic_done')).toBe(true);
  });
});

describe('saveKnowledgeBase / loadKnowledgeBase', () => {
  test('saves and loads markdown', async () => {
    const md = '# Test\nSome content';
    await saveKnowledgeBase(md, { total: 5, groups: 2 });
    const data = await loadKnowledgeBase();
    expect(data.markdown).toBe(md);
    expect(data.stats.total).toBe(5);
    expect(data.stats.groups).toBe(2);
    expect(data.updatedAt).toBeDefined();
    expect(data.version).toBe(2);
  });

  test('backfills stats from imported markdown', async () => {
    const md = `# 技术知识库

## Rust

### 参考链接

- [Rust Book](https://doc.rust-lang.org/book/)
- [Cargo](https://doc.rust-lang.org/cargo/)

## Python

### 参考链接

- [Python Docs](https://docs.python.org/)`;
    await saveKnowledgeBase(md, {});
    const data = await loadKnowledgeBase();
    expect(data.stats.total).toBe(3);
    expect(data.stats.groups).toBe(2);
  });

  test('normalizes zero stats without losing nonzero values', () => {
    const stats = normalizeKnowledgeBaseStats('## Topic\n- [A](https://a.test)', { total: 7, groups: 1 });
    expect(stats.total).toBe(7);
    expect(stats.groups).toBe(1);
  });

  test('load returns null when empty', async () => {
    const data = await loadKnowledgeBase();
    expect(data).toBeNull();
  });
});
