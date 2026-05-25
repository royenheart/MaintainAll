import { describe, test, expect } from '@jest/globals';

let sanitizeStructurePlan, applyStructurePlanToResults, buildStructureDiff, normalizeBookmarkPath;

beforeAll(async () => {
  const mod = await import('../../lib/bookmark_organizer.js');
  ({ sanitizeStructurePlan, applyStructurePlanToResults, buildStructureDiff, normalizeBookmarkPath } = mod);
});

describe('bookmark organizer helpers', () => {
  test('normalizes paths and removes empty root titles', () => {
    expect(normalizeBookmarkPath(['', 'Bookmarks Bar', ' Dev ', ''])).toEqual(['Bookmarks Bar', 'Dev']);
  });

  test('sanitizes bookmark and folder structure plan', () => {
    const bookmarks = [
      { title: 'Docker 入门教程', isTutorial: true },
      { title: 'LLVM 官方文档', isTutorial: false },
    ];
    const plan = sanitizeStructurePlan({
      folders: [
        { action: 'merge', fromPath: 'Bookmarks Bar/教程', toPath: ['Bookmarks Bar', '知识库候选'], reason: '重复', confidence: 0.9 },
      ],
      bookmarks: [
        { index: 0, decision: 'delete_after_kb', reason: '教程入库', confidence: 0.9 },
        { index: 1, decision: 'delete_after_kb', reason: '非教程不能入库删除', confidence: 0.9 },
        { index: 1, decision: 'move', targetPath: 'Bookmarks Bar/官方文档', reason: '长期参考', confidence: 0.7 },
      ],
    }, bookmarks);

    expect(plan.folders).toHaveLength(1);
    expect(plan.folders[0].toPath).toEqual(['Bookmarks Bar', '知识库候选']);
    expect(plan.bookmarks).toHaveLength(2);
    expect(plan.bookmarks[0].decision).toBe('delete_after_kb');
    expect(plan.bookmarks[1].decision).toBe('move');
  });

  test('rejects low-confidence direct delete suggestions', () => {
    const plan = sanitizeStructurePlan({
      bookmarks: [
        { index: 0, decision: 'delete', reason: '可能低价值', confidence: 0.5 },
      ],
    }, [{ title: 'old', isTutorial: false }]);

    expect(plan.bookmarks).toHaveLength(0);
  });

  test('applies plan to results and builds structural diff', () => {
    const results = [
      { title: 'Docker 入门教程', path: ['Bookmarks Bar', '教程'], isTutorial: true, action: 'keep' },
      { title: 'LLVM 文档', path: ['Bookmarks Bar', 'LLVM'], isTutorial: false, action: 'keep' },
    ];
    const plan = sanitizeStructurePlan({
      bookmarks: [
        { index: 0, decision: 'delete_after_kb', reason: '已入库', confidence: 0.9 },
        { index: 1, decision: 'move_rename', newTitle: 'LLVM Language Reference', targetPath: ['Bookmarks Bar', '官方文档'], reason: '归入官方文档', confidence: 0.88 },
      ],
    }, results);

    applyStructurePlanToResults(results, plan);
    const diff = buildStructureDiff(results, [], true);

    expect(results[1].newTitle).toBe('LLVM Language Reference');
    expect(results[1].targetPath).toEqual(['Bookmarks Bar', '官方文档']);
    expect(diff.map(item => item.type)).toEqual(['delete_after_kb', 'rename', 'move']);
  });
});
