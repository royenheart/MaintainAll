/**
 * Unit tests for title_cleaner.js
 * Tests all regex patterns for platform suffix removal and title standardization.
 */
import { describe, test, expect, beforeEach } from '@jest/globals';
import '../__mocks__/chrome.js';

// We need to import the module. Since it's an ES module with exports,
// we dynamically import it
let standardizeTitle, isEntertainment, isTutorial;

beforeAll(async () => {
  const mod = await import('../../lib/title_cleaner.js');
  ({ standardizeTitle, isEntertainment, isTutorial } = mod);
});

describe('standardizeTitle', () => {
  test('removes " - 知乎" suffix', () => {
    const r = standardizeTitle('LLVM链接器 - 知乎');
    expect(r.cleaned).toBe('LLVM链接器');
    expect(r.changed).toBe(true);
  });

  test('removes " - 博客园" suffix', () => {
    const r = standardizeTitle('Linux内核编译 - 博客园');
    expect(r.cleaned).toBe('Linux内核编译');
    expect(r.changed).toBe(true);
  });

  test('removes " - CSDN" suffix', () => {
    const r = standardizeTitle('GDB调试命令 - CSDN');
    expect(r.cleaned).toBe('GDB调试命令');
    expect(r.changed).toBe(true);
  });

  test('removes " - CSDN博客" suffix', () => {
    const r = standardizeTitle('Java GC - CSDN博客');
    expect(r.cleaned).toBe('Java GC');
    expect(r.changed).toBe(true);
  });

  test('removes " - 简书" suffix', () => {
    const r = standardizeTitle('JVM内存模型 - 简书');
    expect(r.cleaned).toBe('JVM内存模型');
    expect(r.changed).toBe(true);
  });

  test('removes " - 掘金" suffix', () => {
    const r = standardizeTitle('Rust异步编程 - 掘金');
    expect(r.cleaned).toBe('Rust异步编程');
    expect(r.changed).toBe(true);
  });

  test('removes " - 51CTO.COM" suffix', () => {
    const r = standardizeTitle('详解三大编译器 - 51CTO.COM');
    expect(r.cleaned).toBe('详解三大编译器');
    expect(r.changed).toBe(true);
  });

  test('removes " - 思否" suffix', () => {
    const r = standardizeTitle('Webpack配置 - 思否');
    expect(r.cleaned).toBe('Webpack配置');
    expect(r.changed).toBe(true);
  });

  test('removes " - SegmentFault 思否" suffix', () => {
    const r = standardizeTitle('React Hooks - SegmentFault 思否');
    expect(r.cleaned).toBe('React Hooks');
    expect(r.changed).toBe(true);
  });

  test('removes腾讯云 suffix variations', () => {
    const r1 = standardizeTitle('Docker入门 - 腾讯云开发者社区-腾讯云');
    expect(r1.cleaned).toBe('Docker入门');

    const r2 = standardizeTitle('K8s部署 - 云+社区-腾讯云');
    expect(r2.cleaned).toBe('K8s部署');
  });

  test('removes " - Stack Overflow" suffix', () => {
    const r = standardizeTitle('Clang optimization levels - Stack Overflow');
    expect(r.cleaned).toBe('Clang optimization levels');
    expect(r.changed).toBe(true);
  });

  test('removes " - GitHub" suffix', () => {
    const r = standardizeTitle('Awesome List - GitHub');
    expect(r.cleaned).toBe('Awesome List');
    expect(r.changed).toBe(true);
  });

  test('removes " - DEV Community" suffix', () => {
    const r = standardizeTitle('Server-Sent Events in Rust - DEV Community');
    expect(r.cleaned).toBe('Server-Sent Events in Rust');
    expect(r.changed).toBe(true);
  });

  test('removes " - Wiki" suffix', () => {
    const r = standardizeTitle('Process migration - Wiki');
    expect(r.cleaned).toBe('Process migration');
    expect(r.changed).toBe(true);
  });

  test('removes " - wikipedia" suffix', () => {
    const r = standardizeTitle('CPU Cache - wikipedia');
    expect(r.cleaned).toBe('CPU Cache');
    expect(r.changed).toBe(true);
  });

  test('removes " - Reddit" suffix', () => {
    const r = standardizeTitle('FPGA Tips - Reddit');
    expect(r.cleaned).toBe('FPGA Tips');
    expect(r.changed).toBe(true);
  });

  test('removes "| Java 全栈知识体系" suffix', () => {
    const r = standardizeTitle('JVM 内存结构 | Java 全栈知识体系');
    expect(r.cleaned).toBe('JVM 内存结构');
    expect(r.changed).toBe(true);
  });

  test('removes "| Java程序员进阶之路" suffix', () => {
    const r = standardizeTitle('JVM诊断工具 | Java程序员进阶之路');
    expect(r.cleaned).toBe('JVM诊断工具');
    expect(r.changed).toBe(true);
  });

  test('removes "xx的博客 - " prefix', () => {
    const r = standardizeTitle('小明的博客 - 深入理解JVM');
    expect(r.cleaned).toBe('深入理解JVM');
    expect(r.changed).toBe(true);
  });

  test('removes " - AuthorName - 博客园" cascade', () => {
    const r = standardizeTitle('操作系统原理 - 王陸 - 博客园');
    expect(r.cleaned).toBe('操作系统原理 - 王陸');
    expect(r.changed).toBe(true);
  });

  test('keeps clean titles unchanged', () => {
    const r = standardizeTitle('LLVM IR 文档');
    expect(r.cleaned).toBe('LLVM IR 文档');
    expect(r.changed).toBe(false);
  });

  test('keeps short titles unchanged', () => {
    const r = standardizeTitle('GitHub');
    expect(r.cleaned).toBe('GitHub');
    expect(r.changed).toBe(false);
  });

  test('truncates very long titles', () => {
    const long = 'A very long title that goes on and on about something very specific that needs to be shortened down to a reasonable length for display in the bookmarks bar of the browser window';
    const r = standardizeTitle(long);
    expect(r.cleaned.length).toBeLessThanOrEqual(80);
    expect(r.changed).toBe(true);
  });

  test('removes URL anchor fragments', () => {
    const r = standardizeTitle('Java GC #:~:text=some%20long%20fragment');
    expect(r.cleaned).toBe('Java GC');
  });

  test('removes trailing em-dash with long suffix', () => {
    const r = standardizeTitle('Clang Compiler — Clang 16.0.0git documentation with many details');
    expect(r.cleaned).toBe('Clang Compiler');
    expect(r.changed).toBe(true);
  });

  test('handles empty title', () => {
    const r = standardizeTitle('');
    expect(r.cleaned).toBe('');
    expect(r.changed).toBe(false);
  });

  test('handles null/undefined', () => {
    const r1 = standardizeTitle(null);
    expect(r1.cleaned).toBe(null);
    expect(r1.changed).toBe(false);

    const r2 = standardizeTitle(undefined);
    expect(r2.cleaned).toBe(undefined);
    expect(r2.changed).toBe(false);
  });
});

describe('isTutorial', () => {
  test('detects cnblogs articles as tutorial', () => {
    expect(isTutorial('any title', 'https://www.cnblogs.com/user/p/12345.html')).toBe(true);
  });

  test('detects zhihu articles as tutorial', () => {
    expect(isTutorial('any', 'https://zhuanlan.zhihu.com/p/12345')).toBe(true);
  });

  test('detects csdn articles as tutorial', () => {
    expect(isTutorial('any', 'https://blog.csdn.net/user/article/details/12345')).toBe(true);
  });

  test('detects jianshu articles as tutorial', () => {
    expect(isTutorial('any', 'https://www.jianshu.com/p/12345')).toBe(true);
  });

  test('detects segmentfault as tutorial', () => {
    expect(isTutorial('any', 'https://segmentfault.com/a/12345')).toBe(true);
  });

  test('detects juejin as tutorial', () => {
    expect(isTutorial('any', 'https://juejin.cn/post/12345')).toBe(true);
  });

  test('detects cloud.tencent.com/developer as tutorial', () => {
    expect(isTutorial('any', 'https://cloud.tencent.com/developer/article/12345')).toBe(true);
  });

  test('detects 51cto article as tutorial', () => {
    expect(isTutorial('any', 'https://www.51cto.com/article/12345')).toBe(true);
  });

  test('detects title with "教程" as tutorial', () => {
    expect(isTutorial('Python 教程', 'https://example.com')).toBe(true);
  });

  test('detects title with "入门" as tutorial', () => {
    expect(isTutorial('Rust 入门指南', 'https://example.com')).toBe(true);
  });

  test('detects title with "详解" as tutorial', () => {
    expect(isTutorial('JVM 详解', 'https://example.com')).toBe(true);
  });

  test('does not flag official docs as tutorial', () => {
    expect(isTutorial('LLVM LangRef', 'https://llvm.org/docs/LangRef.html')).toBe(false);
  });

  test('does not flag GitHub repos as tutorial', () => {
    expect(isTutorial('mpi4py', 'https://github.com/mpi4py/mpi4py')).toBe(false);
  });
});

describe('isEntertainment', () => {
  test('detects pixiv as entertainment', () => {
    expect(isEntertainment('fanart', 'https://www.pixiv.net/artworks/12345')).toBe(true);
  });

  test('detects fanbox as entertainment', () => {
    expect(isEntertainment('any', 'https://www.fanbox.cc/creator')).toBe(true);
  });

  test('detects patreon as entertainment', () => {
    expect(isEntertainment('any', 'https://www.patreon.com/creator')).toBe(true);
  });

  test('detects nhentai as entertainment', () => {
    expect(isEntertainment('any', 'https://nhentai.net/g/12345')).toBe(true);
  });

  test('detects bilibili video as entertainment', () => {
    expect(isEntertainment('any', 'https://www.bilibili.com/video/BV12345')).toBe(true);
  });

  test('detects minecraft related links as entertainment', () => {
    expect(isEntertainment('any', 'https://www.mcbbs.net/thread-12345')).toBe(true);
    expect(isEntertainment('any', 'https://www.curseforge.com/minecraft')).toBe(true);
  });

  test('respects excluded folders', () => {
    // excludedFolders check the folder PATH, not the URL
    expect(isEntertainment('any title', 'https://example.com', ['娱乐', '游戏'])).toBe(true);
    expect(isEntertainment('any title', 'https://example.com', ['工作'], ['娱乐'])).toBe(false);
    expect(isEntertainment('any title', 'https://example.com', ['娱乐'], ['娱乐'])).toBe(true);
  });

  test('does not flag tech sites as entertainment', () => {
    expect(isEntertainment('any', 'https://github.com/user/repo')).toBe(false);
    expect(isEntertainment('any', 'https://docs.python.org/3/')).toBe(false);
    expect(isEntertainment('any', 'https://stackoverflow.com/questions/123')).toBe(false);
  });
});
