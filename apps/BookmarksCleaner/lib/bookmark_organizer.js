/**
 * Helpers for AI-assisted bookmark structure organization.
 * The AI produces suggestions; these helpers normalize and validate them before
 * background.js applies any Chrome bookmarks mutations.
 */

export const BOOKMARK_DECISIONS = new Set([
  'keep',
  'rename',
  'move',
  'move_rename',
  'delete_after_kb',
  'delete',
]);

export const FOLDER_ACTIONS = new Set(['rename', 'merge']);

export function normalizeBookmarkPath(path) {
  if (!Array.isArray(path)) return [];
  return path
    .map(part => String(part || '').trim())
    .filter(Boolean);
}

export function parsePath(value) {
  if (Array.isArray(value)) return normalizeBookmarkPath(value);
  if (typeof value !== 'string') return [];
  return normalizeBookmarkPath(value.split(/\s*(?:>|\/|\\)\s*/));
}

export function formatBookmarksForStructurePrompt(bookmarks) {
  return bookmarks.map((bookmark, index) => {
    const path = normalizeBookmarkPath(bookmark.path).join(' > ') || '未分类';
    const tags = [
      bookmark.isTutorial ? 'tutorial' : '',
      bookmark.isEntertainment ? 'entertainment' : '',
    ].filter(Boolean).join(', ') || 'normal';
    return `[${index}] 标题: "${bookmark.newTitle || bookmark.title}"
    原标题: "${bookmark.title}"
    URL: ${bookmark.url}
    当前分类: ${path}
    标记: ${tags}`;
  }).join('\n\n');
}

export function formatFoldersForStructurePrompt(foldersOrBookmarks) {
  const folderSet = new Set();
  for (const item of foldersOrBookmarks) {
    const path = normalizeBookmarkPath(item.path);
    for (let i = 1; i <= path.length; i++) {
      folderSet.add(path.slice(0, i).join(' > '));
    }
  }
  return [...folderSet].filter(Boolean).sort((a, b) => a.localeCompare(b, 'zh-CN')).join('\n');
}

export function sanitizeStructurePlan(rawPlan, bookmarks) {
  const plan = rawPlan && typeof rawPlan === 'object' ? rawPlan : {};
  const bookmarkActions = Array.isArray(plan.bookmarks) ? plan.bookmarks : [];
  const folderActions = Array.isArray(plan.folders) ? plan.folders : [];
  const cleaned = { bookmarks: [], folders: [] };
  const seen = new Set();

  for (const action of bookmarkActions) {
    if (!action || typeof action !== 'object') continue;
    const index = Number(action.index);
    if (!Number.isInteger(index) || index < 0 || index >= bookmarks.length || seen.has(index)) continue;

    const decision = BOOKMARK_DECISIONS.has(action.decision) ? action.decision : 'keep';
    const targetPath = parsePath(action.targetPath);
    const newTitle = typeof action.newTitle === 'string' ? action.newTitle.trim() : '';
    const confidence = clampConfidence(action.confidence);
    const bookmark = bookmarks[index];
    const isTutorial = Boolean(bookmark.isTutorial);

    if (decision === 'delete_after_kb' && !isTutorial) continue;
    if (decision === 'delete' && confidence < 0.85) continue;
    if ((decision === 'move' || decision === 'move_rename') && targetPath.length === 0) continue;
    if ((decision === 'rename' || decision === 'move_rename') && !newTitle) continue;

    cleaned.bookmarks.push({
      index,
      decision,
      newTitle,
      targetPath,
      reason: String(action.reason || '').trim(),
      confidence,
    });
    seen.add(index);
  }

  for (const action of folderActions) {
    if (!action || typeof action !== 'object') continue;
    const type = FOLDER_ACTIONS.has(action.action) ? action.action : '';
    if (!type) continue;

    const fromPath = parsePath(action.fromPath);
    let toPath = parsePath(action.toPath);
    if (fromPath.length === 0 || toPath.length === 0) continue;
    if (type === 'rename') {
      toPath = [...fromPath.slice(0, -1), toPath[toPath.length - 1]];
    }
    if (fromPath.join('\n') === toPath.join('\n')) continue;

    cleaned.folders.push({
      action: type,
      fromPath,
      toPath,
      reason: String(action.reason || '').trim(),
      confidence: clampConfidence(action.confidence),
    });
  }

  return cleaned;
}

export function applyStructurePlanToResults(results, plan) {
  for (const action of plan.bookmarks || []) {
    const item = results[action.index];
    if (!item) continue;
    item.structureAction = action.decision;
    item.structureReason = action.reason;
    item.structureConfidence = action.confidence;

    if (action.newTitle && action.newTitle !== item.title) {
      item.newTitle = action.newTitle;
      item.action = item.action === 'keep' ? 'rename' : item.action;
      item.changeReason = action.reason ? `AI结构整理: ${action.reason}` : 'AI结构整理';
    }
    if (action.targetPath.length > 0) {
      item.targetPath = action.targetPath;
    }
  }
}

export function buildStructureDiff(results, folderPlan = [], kbSaved = false) {
  const changes = [];
  for (const folder of folderPlan) {
    changes.push({
      type: folder.action === 'merge' ? 'folder_merge' : 'folder_rename',
      old: folder.fromPath.join(' > '),
      new: folder.toPath.join(' > '),
      reason: folder.reason,
    });
  }

  for (const item of results) {
    const oldPath = normalizeBookmarkPath(item.path).join(' > ');
    const newPath = normalizeBookmarkPath(item.targetPath).join(' > ');
    const willDelete = item.structureAction === 'delete' || (kbSaved && item.structureAction === 'delete_after_kb');
    if (willDelete) {
      changes.push({
        type: item.structureAction,
        old: item.title,
        new: item.structureAction === 'delete_after_kb' ? '已写入知识库，删除书签' : '删除书签',
        folder: oldPath,
        reason: item.structureReason || item.changeReason,
      });
      continue;
    }
    if (item.newTitle && item.newTitle !== item.title) {
      changes.push({ type: 'rename', old: item.title, new: item.newTitle, folder: oldPath, reason: item.changeReason });
    }
    if (newPath && newPath !== oldPath) {
      changes.push({ type: 'move', old: item.title, new: newPath, folder: oldPath, reason: item.structureReason });
    }
  }
  return changes;
}

function clampConfidence(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0.7;
  return Math.max(0, Math.min(1, n));
}
