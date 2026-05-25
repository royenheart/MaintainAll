/**
 * Background service worker for Bookmarks Cleaner.
 * Handles bookmarks API, backup, KB generation, WebDAV sync, and coordinates processing.
 */

import { standardizeTitle, isEntertainment, isTutorial, DEFAULT_TITLE_RULES } from './lib/title_cleaner.js';
import { DeepSeekClient } from './lib/deepseek.js';
import { DEFAULT_PROMPTS } from './lib/prompts.js';
import { generateKnowledgeBase, saveKnowledgeBase, loadKnowledgeBase, exportKnowledgeBase, mergeKnowledgeBases, normalizeKnowledgeBaseStats } from './lib/knowledge_base.js';
import { WebDAVClient } from './lib/webdav.js';
import { applyStructurePlanToResults, buildStructureDiff, normalizeBookmarkPath, sanitizeStructurePlan } from './lib/bookmark_organizer.js';

// ============ Settings ============
// Sensitive fields stored in chrome.storage.local (never synced to Google).
// Non-sensitive fields in chrome.storage.sync for cross-device preferences.

const DEFAULT_SETTINGS = {
  // Non-sensitive (sync)
  model: 'deepseek-v4-flash',
  excludedFolders: ['娱乐'],
  useAI: false,
  autoBackup: true,
  standardizeTitles: true,
  dryRun: false,
  webdavUrl: '',
  // Sensitive (local)
  apiKey: '',
  webdavUser: '',
  webdavPass: '',
};

const SENSITIVE_KEYS = ['apiKey', 'webdavUser', 'webdavPass'];
const NON_SENSITIVE_DEFAULTS = Object.fromEntries(
  Object.entries(DEFAULT_SETTINGS).filter(([key]) => !SENSITIVE_KEYS.includes(key))
);
const SENSITIVE_DEFAULTS = Object.fromEntries(
  Object.entries(DEFAULT_SETTINGS).filter(([key]) => SENSITIVE_KEYS.includes(key))
);

async function getSettings() {
  const [syncData, localData] = await Promise.all([
    chrome.storage.sync.get(NON_SENSITIVE_DEFAULTS),
    chrome.storage.local.get(SENSITIVE_DEFAULTS),
  ]);
  return { ...DEFAULT_SETTINGS, ...syncData, ...localData };
}

/**
 * Auto-detect a stable profile identifier for WebDAV path separation.
 * - Google-signed-in accounts → "google_<account-hash>"
 * - Guest / temp profiles → "temp_<profile-hash>"
 * Cached in chrome.storage.local after first detection.
 */
async function getProfileId() {
  console.log('[ProfileId] getProfileId() called');
  const { profileId } = await chrome.storage.local.get('profileId');
  console.log('[ProfileId] cached value:', profileId || '(empty)');

  if (profileId && profileId.startsWith('google_')) {
    console.log('[ProfileId] returning cached google_ id');
    return profileId;
  }

  let id;
  try {
    if (chrome.identity && chrome.identity.getProfileUserInfo) {
      const info = await chrome.identity.getProfileUserInfo();
      console.log('[ProfileId] getProfileUserInfo returned:', JSON.stringify(info));
      if (info && info.id && info.id !== '') {
        id = 'google_' + simpleHash(info.id).substring(0, 8);
        console.log('[ProfileId] google account detected, id=', id);
      } else {
        console.log('[ProfileId] empty id/email — check manifest has identity.email permission');
      }
    }
  } catch (e) {
    console.log('[ProfileId] getProfileUserInfo threw:', e.message || e);
  }

  if (!id) {
    id = 'profile_' + simpleHash(chrome.runtime.id).substring(0, 8);
    console.log('[ProfileId] fallback:', id);
  }

  if (id !== profileId) {
    await chrome.storage.local.set({ profileId: id });
    console.log('[ProfileId] saved:', id);
  }
  return id;
}

/** Simple FNV-1a style hash returning hex string. */
function simpleHash(str) {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(16);
}

async function saveSettings(settings) {
  const syncPart = {};
  const localPart = {};
  for (const [k, v] of Object.entries(settings)) {
    if (SENSITIVE_KEYS.includes(k)) {
      localPart[k] = v;
    } else {
      syncPart[k] = v;
    }
  }
  await Promise.all([
    chrome.storage.sync.set(syncPart),
    chrome.storage.local.set(localPart),
  ]);
}

/** Load prompts from storage, falling back to defaults. */
async function getPrompts() {
  const { prompts } = await chrome.storage.local.get('prompts');
  return { ...DEFAULT_PROMPTS, ...(prompts || {}) };
}

/** Load custom title rules, falling back to defaults. */
async function getRules() {
  const { customRules } = await chrome.storage.local.get('customRules');
  return customRules && customRules.length ? customRules : DEFAULT_TITLE_RULES;
}

// ============ WebDAV Permission Helper ============

/**
 * Ensure the extension has host permission for a user's WebDAV server.
 * Prompts the user via Chrome's native permission dialog on first access.
 * @param {string} webdavUrl
 * @returns {Promise<{granted: boolean, error?: string}>}
 */
async function ensureWebdavPermission(webdavUrl) {
  let origin;
  try {
    const u = new URL(webdavUrl);
    origin = `${u.protocol}//${u.host}/*`;
  } catch {
    return { granted: false, error: '无效的 URL 格式', origin: null };
  }
  const already = await chrome.permissions.contains({ origins: [origin] });
  if (already) return { granted: true, origin };
  // Side panel handles the actual request() call (needs user gesture)
  return { granted: false, needRequest: true, origin };
}

// ============ Backup ============
async function backupBookmarks() {
  const tree = await chrome.bookmarks.getTree();
  const html = treeToHTML(tree);
  // Service worker: Blob/URL.createObjectURL not available, use data URL
  const encoded = btoa(unescape(encodeURIComponent(html)));
  const url = `data:text/html;base64,${encoded}`;
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').substring(0, 19);
  const filename = `bookmarks_backup_${timestamp}.html`;
  await chrome.downloads.download({ url, filename, saveAs: false });
  return filename;
}

function treeToHTML(nodes, indent = 0) {
  let html = `<!DOCTYPE NETSCAPE-Bookmark-file-1>\n<!-- Backup by Bookmarks Cleaner -->\n<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">\n<TITLE>Bookmarks Backup</TITLE>\n<H1>Bookmarks</H1>\n<DL><p>\n`;
  for (const node of nodes) html += nodeToHTML(node, 1);
  html += '</DL><p>\n';
  return html;
}

function nodeToHTML(node, depth) {
  const pad = '    '.repeat(depth);
  if (node.url) return `${pad}<DT><A HREF="${esc(node.url)}" ADD_DATE="${Math.floor(Date.now()/1000)}">${esc(node.title)}</A>\n`;
  if (node.children) {
    let h = `${pad}<DT><H3>${esc(node.title)}</H3>\n${pad}<DL><p>\n`;
    for (const c of node.children) h += nodeToHTML(c, depth + 1);
    h += `${pad}</DL><p>\n`;
    return h;
  }
  return '';
}

function esc(s) { return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

// ============ Processing Cancellation ============
let activeProcessingJob = null;

function createProcessingJob() {
  return { cancelled: false, controller: new AbortController() };
}

function cancelProcessingJob() {
  if (!activeProcessingJob) return false;
  activeProcessingJob.cancelled = true;
  activeProcessingJob.controller.abort();
  return true;
}

function assertNotCancelled(job) {
  if (job?.cancelled || job?.controller?.signal?.aborted) {
    const err = new Error('用户已取消 AI 整理');
    err.name = 'AbortError';
    throw err;
  }
}

// ============ Collect Bookmarks ============
async function collectBookmarkTree() {
  const tree = await chrome.bookmarks.getTree();
  const bookmarks = [];
  const folders = [];

  function walk(nodes, path = []) {
    for (const node of nodes) {
      const p = [...path, node.title];
      if (node.url) {
        bookmarks.push({ id: node.id, title: node.title, url: node.url, path: p.slice(0, -1), parentId: node.parentId });
      } else {
        folders.push({ id: node.id, title: node.title, path: p, parentId: node.parentId, children: node.children || [] });
      }
      if (node.children) walk(node.children, p);
    }
  }

  walk(tree);
  return { bookmarks, folders };
}

async function collectBookmarks() {
  const { bookmarks } = await collectBookmarkTree();
  return bookmarks;
}

function folderKey(path) {
  return normalizeBookmarkPath(path).join('\u001f');
}

function buildFolderIndex(folders) {
  const map = new Map();
  const topLevel = new Set();
  for (const folder of folders) {
    const path = normalizeBookmarkPath(folder.path);
    if (!path.length) continue;
    map.set(folderKey(path), { ...folder, path });
    if (path.length === 1) topLevel.add(path[0]);
  }
  return { map, topLevel };
}

async function ensureFolderPath(targetPath, sourcePath, folderState) {
  let path = normalizeBookmarkPath(targetPath);
  if (!path.length) return null;

  const sourceRoot = normalizeBookmarkPath(sourcePath)[0];
  if (sourceRoot && !folderState.topLevel.has(path[0])) {
    path = [sourceRoot, ...path];
  }

  let parent = null;
  for (let i = 1; i <= path.length; i++) {
    const currentPath = path.slice(0, i);
    const key = folderKey(currentPath);
    let folder = folderState.map.get(key);
    if (!folder) {
      if (!parent) return null;
      folder = await chrome.bookmarks.create({ parentId: parent.id, title: currentPath[currentPath.length - 1] });
      folder.path = currentPath;
      folderState.map.set(key, folder);
    }
    parent = folder;
  }
  return parent;
}

async function applyFolderPlan(folderPlan, folderState, results, onProgress, job = null) {
  const counts = { renamedFolders: 0, mergedFolders: 0 };
  for (let i = 0; i < folderPlan.length; i++) {
    assertNotCancelled(job);
    const action = folderPlan[i];
    onProgress({ phase: 'structure_apply', message: `整理分类... ${i + 1}/${folderPlan.length}`, done: i, total: folderPlan.length });
    const source = folderState.map.get(folderKey(action.fromPath));
    if (!source) continue;

    if (action.action === 'rename') {
      const newTitle = action.toPath[action.toPath.length - 1];
      if (newTitle && newTitle !== source.title) {
        await chrome.bookmarks.update(source.id, { title: newTitle });
        folderState.map.delete(folderKey(action.fromPath));
        const renamed = { ...source, title: newTitle, path: action.toPath };
        folderState.map.set(folderKey(action.toPath), renamed);
        counts.renamedFolders++;
      }
      continue;
    }

    if (action.action === 'merge') {
      const target = await ensureFolderPath(action.toPath, action.fromPath, folderState);
      if (!target || target.id === source.id) continue;
      const sourceKey = folderKey(action.fromPath);
      const descendants = results.filter(item => {
        const key = folderKey(item.path);
        return key === sourceKey || key.startsWith(`${sourceKey}\u001f`);
      });
      for (const item of descendants) {
        await chrome.bookmarks.move(item.id, { parentId: target.id });
        item.parentId = target.id;
        item.path = action.toPath;
      }
      if (chrome.bookmarks.removeTree) {
        await chrome.bookmarks.removeTree(source.id).catch(() => {});
      }
      counts.mergedFolders++;
    }
  }
  return counts;
}

async function applyBookmarkChanges(results, folderPlan, options) {
  const { kbSaved, folderState, onProgress, dryRun, job = null } = options;
  const changes = results.filter(item => {
    const titleChanged = item.newTitle && item.newTitle !== item.title;
    const targetChanged = item.targetPath && folderKey(item.targetPath) !== folderKey(item.path);
    const willDelete = item.structureAction === 'delete' || (kbSaved && item.structureAction === 'delete_after_kb');
    return titleChanged || targetChanged || willDelete;
  });

  const counts = { renamed: 0, moved: 0, deleted: 0, removedKnowledge: 0 };
  if (dryRun || changes.length === 0) return counts;

  for (let i = 0; i < changes.length; i++) {
    assertNotCancelled(job);
    const item = changes[i];
    onProgress({ phase: 'apply', message: `应用结构整理... ${i + 1}/${changes.length}`, done: i, total: changes.length });
    const willDelete = item.structureAction === 'delete' || (kbSaved && item.structureAction === 'delete_after_kb');

    if (willDelete) {
      await chrome.bookmarks.remove(item.id);
      counts.deleted++;
      if (item.structureAction === 'delete_after_kb') counts.removedKnowledge++;
      continue;
    }

    if (item.newTitle && item.newTitle !== item.title) {
      await chrome.bookmarks.update(item.id, { title: item.newTitle });
      counts.renamed++;
    }

    if (item.targetPath && folderKey(item.targetPath) !== folderKey(item.path)) {
      const targetFolder = await ensureFolderPath(item.targetPath, item.path, folderState);
      if (targetFolder && targetFolder.id !== item.parentId) {
        await chrome.bookmarks.move(item.id, { parentId: targetFolder.id });
        counts.moved++;
      }
    }
  }

  return counts;
}

// ============ Processing Pipeline ============
async function processBookmarks(onProgress, useAIOverride = null, job = null) {
  console.log('[Process] Starting processBookmarks, useAI=', useAIOverride);
  assertNotCancelled(job);
  const settings = await getSettings();
  if (useAIOverride !== null) settings.useAI = useAIOverride;
  console.log('[Process] useAI:', settings.useAI, 'apiKey:', settings.apiKey ? 'present (length=' + settings.apiKey.length + ')' : 'missing');
  const titleRules = await getRules();
  console.log('[Process] titleRules loaded:', titleRules.length, 'first rule:', titleRules[0]?.substring(0, 40) || '(empty)');

  onProgress({ phase: 'collecting', message: '正在收集书签...', done: 0, total: 0 });
  console.log('[Process] collecting bookmarks...');
  const { bookmarks: allBookmarks, folders: allFolders } = await collectBookmarkTree();
  assertNotCancelled(job);
  const folderState = buildFolderIndex(allFolders);
  const total = allBookmarks.length;
  console.log('[Process] total bookmarks:', total);

  if (settings.autoBackup) {
    onProgress({ phase: 'backup', message: '正在备份书签...', done: 0, total });
    console.log('[Process] backing up...');
    const bf = await backupBookmarks();
    assertNotCancelled(job);
    console.log('[Process] backup done:', bf);
    onProgress({ phase: 'backup', message: `备份完成: ${bf}`, done: 0, total });
  }

  onProgress({ phase: 'classify', message: '正在分类和标准化标题...', done: 0, total });

  const excluded = (settings.excludedFolders || ['娱乐']).map(f => f.toLowerCase());
  const toProcess = allBookmarks.filter(bm => {
    const fp = bm.path.join('/').toLowerCase();
    return !excluded.some(f => fp.includes(f));
  });
  console.log('[Process] excluded:', total - toProcess.length, 'toProcess:', toProcess.length);

  let done = 0;
  const results = [];

  for (const bm of toProcess) {
    assertNotCancelled(job);
    done++;
    const ent = isEntertainment(bm.title, bm.url, bm.path, excluded);
    const tut = isTutorial(bm.title, bm.url);
    let action = 'keep', newTitle = bm.title, reason = '';

    if (settings.standardizeTitles) {
      const r = standardizeTitle(bm.title, titleRules);
      if (r.changed) { newTitle = r.cleaned; reason = r.reason; action = 'rename'; }
    }

    results.push({ ...bm, isEntertainment: ent, isTutorial: tut, action, newTitle, changeReason: reason });

    if (done % 100 === 0 || done === toProcess.length) {
      onProgress({ phase: 'classify', message: `分类中... ${done}/${toProcess.length}`, done, total: toProcess.length });
    }
  }

  const renameCount = results.filter(r => r.action === 'rename').length;
  console.log('[Process] regex rename candidates:', renameCount);
  let structurePlan = { bookmarks: [], folders: [] };

  // AI structure analysis: title cleanup, bookmark moves, folder merge/rename, low-value cleanup.
  if (settings.useAI && settings.apiKey) {
    console.log('[Process] starting AI analysis phase');
    // Re-read settings for latest model
    const latestSettings = await getSettings();
    const prompts = await getPrompts();
    const ai = new DeepSeekClient(latestSettings.apiKey, latestSettings.model, prompts);
    onProgress({ phase: 'ai_structure', message: 'AI 正在分析书签结构...', done: 0, total: results.length });
    const STRUCTURE_BATCH = 30;
    for (let i = 0; i < results.length; i += STRUCTURE_BATCH) {
      assertNotCancelled(job);
      const chunk = results.slice(i, i + STRUCTURE_BATCH);
      const batchNo = Math.floor(i / STRUCTURE_BATCH) + 1;
      const batchTotal = Math.ceil(results.length / STRUCTURE_BATCH);
      onProgress({ phase: 'ai_structure', message: `AI 正在规划第 ${batchNo}/${batchTotal} 批书签结构...`, done: i, total: results.length });
      try {
        const thinkingStreamId = `structure-thinking-${batchNo}`;
        let thinkingPending = '';
        let lastThinkingFlushAt = 0;
        const flushThinking = () => {
          if (!thinkingPending) return;
          const delta = thinkingPending;
          thinkingPending = '';
          lastThinkingFlushAt = Date.now();
          onProgress({
            phase: 'ai_thinking',
            streamId: thinkingStreamId,
            title: `AI 思考 - 第 ${batchNo}/${batchTotal} 批`,
            message: `AI 正在思考第 ${batchNo}/${batchTotal} 批书签结构...`,
            delta,
            done: i,
            total: results.length
          });
        };
        let lastContentAt = 0;
        const batchPlan = sanitizeStructurePlan(await ai.analyzeBookmarkStructure(chunk, allFolders, {
          signal: job?.controller?.signal,
          onThinking: (delta) => {
            thinkingPending += String(delta || '');
            const now = Date.now();
            if (now - lastThinkingFlushAt >= 300 || thinkingPending.length >= 180) flushThinking();
          },
          onContent: () => {
            const now = Date.now();
            if (now - lastContentAt < 500) return;
            lastContentAt = now;
            onProgress({
              phase: 'ai_structure',
              message: `AI 正在输出第 ${batchNo}/${batchTotal} 批 JSON 计划...`,
              done: i,
              total: results.length
            });
          }
        }), chunk);
        flushThinking();
        for (const action of batchPlan.bookmarks) {
          structurePlan.bookmarks.push({ ...action, index: i + action.index });
        }
        structurePlan.folders.push(...batchPlan.folders);
      } catch (e) {
        if (e?.name === 'AbortError') throw e;
        console.error('[Process] AI structure batch failed:', String(e).substring(0, 200));
      }
      onProgress({ phase: 'ai_structure', message: `AI 结构规划... ${Math.min(i + STRUCTURE_BATCH, results.length)}/${results.length}`, done: Math.min(i + STRUCTURE_BATCH, results.length), total: results.length });
    }
    applyStructurePlanToResults(results, structurePlan);

    // Keep existing title-refinement pass for regex-detected noisy titles.
    const renameTargets = results.filter(r => r.action === 'rename');
    console.log('[Process] AI rename targets:', renameTargets.length);

    if (renameTargets.length > 0) {
      onProgress({ phase: 'ai_analyze', message: 'AI 分析标题中...', done: 0, total: renameTargets.length });
      const BATCH = 20;
      for (let i = 0; i < renameTargets.length; i += BATCH) {
        assertNotCancelled(job);
        const batch = renameTargets.slice(i, i + BATCH).map(b => ({ title: b.title, url: b.url, folder: b.path.join(' > ') }));
        const batchNo = Math.floor(i / BATCH) + 1;
        const batchTotal = Math.ceil(renameTargets.length / BATCH);
        console.log(`[Process] AI batch ${batchNo}/${batchTotal}`);
        onProgress({
          phase: 'ai_analyze',
          message: `AI 正在分析第 ${batchNo}/${batchTotal} 批标题...`,
          done: i,
          total: renameTargets.length
        });
        try {
          const suggestions = await ai.analyzeTitles(batch, { signal: job?.controller?.signal });
          console.log('[Process] batch got', suggestions?.length || 0, 'suggestions');
          for (const s of suggestions || []) {
            const idx = i + s.index;
            if (idx < renameTargets.length && s && s.cleaned !== s.original) {
              renameTargets[idx].newTitle = s.cleaned;
              renameTargets[idx].changeReason = `AI: ${s.reason || '优化'}`;
            }
          }
        } catch (e) {
          if (e?.name === 'AbortError') throw e;
          console.error('[Process] AI batch failed:', String(e).substring(0, 200));
        }
        const progress = Math.min(i + BATCH, renameTargets.length);
        onProgress({ phase: 'ai_analyze', message: `AI 分析... ${progress}/${renameTargets.length}`, done: progress, total: renameTargets.length });
      }
    }
  } else {
    console.log('[Process] skipping AI: useAI=', settings.useAI, 'apiKey=', !!settings.apiKey);
  }

  // Generate KB from tutorials (if AI enabled)
  let kbSaved = false;
  if (settings.useAI && settings.apiKey) {
    const tutorials = results.filter(r => r.isTutorial);
    console.log('[Process] KB generation: tutorials found:', tutorials.length);
    if (tutorials.length > 0) {
      assertNotCancelled(job);
      onProgress({ phase: 'kb', message: '正在生成知识库...', done: 0, total: tutorials.length });
      try {
        // Re-read settings for model (may have been updated by side panel)
        const latestSettings = await getSettings();
        const prompts = await getPrompts();
        const ai = new DeepSeekClient(latestSettings.apiKey, latestSettings.model, prompts);
        const { markdown, stats } = await generateKnowledgeBase(tutorials, {
          useAI: true,
          deepseekClient: ai,
          signal: job?.controller?.signal,
          onProgress: (update) => onProgress({
            phase: update.phase || 'kb',
            message: update.message || '正在生成知识库...',
            done: update.done || 0,
            total: update.total || tutorials.length,
            topic: update.topic,
            markdown: update.markdown
          })
        });
        if (markdown) {
          await saveKnowledgeBase(markdown, stats);
          kbSaved = true;
          for (const item of tutorials) {
            item.structureAction = 'delete_after_kb';
            item.structureReason = item.structureReason || '已整理进知识库，书签管理器中不再长期保留';
          }
          console.log('[Process] KB saved:', stats.total, 'articles,', stats.groups, 'groups');
        }
      } catch (e) {
        if (e?.name === 'AbortError') throw e;
        console.error('[Process] KB generation failed:', String(e).substring(0, 200));
      }
    }
  }

  assertNotCancelled(job);
  onProgress({ phase: 'apply', message: '开始统一应用最终整理计划...', done: 0, total: 1 });
  const folderCounts = settings.useAI && settings.apiKey
    ? await applyFolderPlan(structurePlan.folders, folderState, results, onProgress, job)
    : { renamedFolders: 0, mergedFolders: 0 };
  assertNotCancelled(job);
  const bookmarkCounts = await applyBookmarkChanges(results, structurePlan.folders, {
    kbSaved,
    folderState,
    onProgress,
    dryRun: settings.dryRun,
    job
  });
  const diff = buildStructureDiff(results, structurePlan.folders, kbSaved).slice(0, 250);
  chrome.runtime.sendMessage({ type: 'changes_result', changes: diff }).catch(() => {});

  const summary = {
    total, processed: toProcess.length, skipped: total - toProcess.length,
    renamed: bookmarkCounts.renamed,
    moved: bookmarkCounts.moved,
    deleted: bookmarkCounts.deleted,
    removedKnowledge: bookmarkCounts.removedKnowledge,
    renamedFolders: folderCounts.renamedFolders,
    mergedFolders: folderCounts.mergedFolders,
    entertainment: results.filter(r => r.isEntertainment).length,
    tutorials: results.filter(r => r.isTutorial).length,
    dryRun: settings.dryRun,
    kbSaved
  };

  console.log('[Process] complete. summary:', JSON.stringify(summary));
  onProgress({ phase: 'complete', message: '处理完成', done: total, total, summary });
  return { results, summary };
}

// ============ Update Check ============

const UPDATE_CHECK_URL = 'https://raw.githubusercontent.com/royenheart/MaintainAll/main/apps/BookmarksCleaner/VERSION';
const UPDATE_CHECK_INTERVAL_MINUTES = 1440; // 24 hours

async function getInstalledVersion() {
  const { version } = chrome.runtime.getManifest();
  return version;
}

async function checkForUpdates() {
  try {
    const installed = await getInstalledVersion();
    const response = await fetch(UPDATE_CHECK_URL, { cache: 'no-cache' });
    if (!response.ok) return { installed, latest: null, updateAvailable: false };

    const latest = (await response.text()).trim();
    const updateAvailable = compareVersions(latest, installed) > 0;
    return { installed, latest, updateAvailable };
  } catch {
    return { installed: await getInstalledVersion(), latest: null, updateAvailable: false };
  }
}

function compareVersions(a, b) {
  const pa = a.split('.').map(Number);
  const pb = b.split('.').map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    if ((pa[i] || 0) > (pb[i] || 0)) return 1;
    if ((pa[i] || 0) < (pb[i] || 0)) return -1;
  }
  return 0;
}

async function periodicUpdateCheck() {
  const result = await checkForUpdates();
  if (result.updateAvailable) {
    chrome.notifications.create('update-available', {
      type: 'basic',
      iconUrl: 'icons/icon128.png',
      title: 'Bookmarks Cleaner 有新版本',
      message: `v${result.latest} 可用（当前 v${result.installed}）。请下载最新版。`,
      buttons: [{ title: '查看发布页' }],
      requireInteraction: true,
    });
  }
}

chrome.alarms.create('update-check', { periodInMinutes: UPDATE_CHECK_INTERVAL_MINUTES });
chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === 'update-check') periodicUpdateCheck();
});

chrome.notifications.onButtonClicked.addListener(notificationId => {
  if (notificationId === 'update-available') {
    chrome.tabs.create({ url: 'https://github.com/royenheart/MaintainAll/releases' });
  }
});

setTimeout(periodicUpdateCheck, 30000);

// ============ Message Handlers ============
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // --- start_processing ---
  if (message.type === 'start_processing') {
    if (activeProcessingJob) return sendResponse({ success: false, error: '已有整理任务正在运行' });
    const useAIOverride = message.useAI !== undefined ? message.useAI : null;
    activeProcessingJob = createProcessingJob();
    const cb = (update) => chrome.runtime.sendMessage({ type: 'progress_update', ...update }).catch(() => {});
    processBookmarks(cb, useAIOverride, activeProcessingJob)
      .then(r => sendResponse({ success: true, ...r.summary }))
      .catch(e => {
        if (e?.name === 'AbortError') {
          cb({ phase: 'cancelled', message: 'AI 整理已取消，未应用最终修改', done: 0, total: 0 });
          sendResponse({ success: false, cancelled: true, error: 'AI 整理已取消' });
        } else {
          sendResponse({ success: false, error: e.message });
        }
      })
      .finally(() => { activeProcessingJob = null; });
    return true;
  }

  // --- cancel_processing ---
  if (message.type === 'cancel_processing') {
    const cancelled = cancelProcessingJob();
    sendResponse({ success: true, cancelled });
    return true;
  }

  // --- backup_only ---
  if (message.type === 'backup_only') {
    backupBookmarks().then(f => sendResponse({ success: true, filename: f })).catch(e => sendResponse({ success: false, error: e.message }));
    return true;
  }

  // --- check_update ---
  if (message.type === 'check_update') {
    checkForUpdates().then(result => sendResponse({ success: true, ...result }));
    return true;
  }

  // --- get_version ---
  if (message.type === 'get_version') {
    getInstalledVersion().then(v => sendResponse({ version: v }));
    return true;
  }

  // --- get_profile_id ---
  if (message.type === 'get_profile_id') {
    getProfileId().then(profileId => sendResponse({ profileId }))
      .catch(() => sendResponse({ profileId: 'profile_unknown' }));
    return true;
  }

  // --- get_prompts ---
  if (message.type === 'get_prompts') {
    getPrompts().then(prompts => sendResponse({ prompts }));
    return true;
  }

  // --- save_prompts ---
  if (message.type === 'save_prompts') {
    chrome.storage.local.set({ prompts: message.prompts }, () => sendResponse({ success: true }));
    return true;
  }

  // --- get_rules ---
  if (message.type === 'get_rules') {
    getRules().then(rules => sendResponse({ rules }));
    return true;
  }

  // --- save_rules ---
  if (message.type === 'save_rules') {
    chrome.storage.local.set({ customRules: message.rules }, () => sendResponse({ success: true }));
    return true;
  }

  // --- reset_rules ---
  if (message.type === 'reset_rules') {
    chrome.storage.local.remove('customRules', () => sendResponse({ success: true, rules: DEFAULT_TITLE_RULES }));
    return true;
  }

  // --- get_preview ---
  if (message.type === 'get_preview') {
    collectBookmarks().then(async all => {
      const rules = await getRules();
      const changes = all.filter(bm => standardizeTitle(bm.title, rules).changed).map(bm => {
        const { cleaned, reason } = standardizeTitle(bm.title, rules);
        return { ...bm, newTitle: cleaned, reason };
      });
      sendResponse({ success: true, changes, total: all.length });
    }).catch(e => sendResponse({ success: false, error: e.message }));
    return true;
  }

  // --- get_settings ---
  if (message.type === 'get_settings') {
    getSettings().then(s => sendResponse(s));
    return true;
  }

  // --- save_settings ---
  if (message.type === 'save_settings') {
    saveSettings(message.settings).then(() => sendResponse({ success: true }));
    return true;
  }

  // --- get_knowledge_base ---
  if (message.type === 'get_knowledge_base') {
    loadKnowledgeBase().then(data => sendResponse({ success: true, data })).catch(e => sendResponse({ success: false, error: e.message }));
    return true;
  }

  // --- import_knowledge_base ---
  if (message.type === 'import_knowledge_base') {
    (async () => {
      const markdown = String(message.markdown || '').trim();
      if (!markdown) return sendResponse({ success: false, error: '导入内容为空' });
      const stats = normalizeKnowledgeBaseStats(markdown, { source: 'imported' });
      const entry = await saveKnowledgeBase(markdown, stats);
      sendResponse({ success: true, data: entry, stats: entry.stats });
    })().catch(e => sendResponse({ success: false, error: e.message }));
    return true;
  }

  // --- generate_knowledge_base ---
  if (message.type === 'generate_knowledge_base') {
    (async () => {
      const emit = (update) => chrome.runtime.sendMessage({ type: 'kb_progress_update', ...update }).catch(() => {});
      const settings = await getSettings();
      if (!settings.apiKey) return sendResponse({ success: false, error: '请先在设置中配置 DeepSeek API Key' });

      emit({ phase: 'kb_collect', message: '正在收集书签...', done: 0, total: 0 });
      const all = await collectBookmarks();
      const tutorials = all.filter(bm => isTutorial(bm.title, bm.url));
      if (tutorials.length === 0) return sendResponse({ success: false, error: '没有检测到教程类书签' });
      emit({ phase: 'kb_filter', message: `检测到 ${tutorials.length} 篇教程类书签`, done: 0, total: tutorials.length });

      const prompts = await getPrompts();
      const ai = new DeepSeekClient(settings.apiKey, settings.model, prompts);
      const { markdown, stats } = await generateKnowledgeBase(tutorials, {
        useAI: true,
        deepseekClient: ai,
        onProgress: emit
      });
      await saveKnowledgeBase(markdown, stats);
      emit({
        phase: 'kb_complete',
        message: `知识库生成完成: ${stats.total} 篇文章, ${stats.groups} 个章节`,
        done: stats.groups,
        total: stats.groups,
        markdown
      });
      sendResponse({ success: true, markdown, stats: { ...stats, updatedAt: new Date().toISOString() } });
    })().catch(e => sendResponse({ success: false, error: e.message }));
    return true;
  }

  // --- export_knowledge_base ---
  if (message.type === 'export_knowledge_base') {
    loadKnowledgeBase().then(data => {
      if (!data || !data.markdown) return sendResponse({ success: false, error: '知识库为空' });
      return exportKnowledgeBase(data.markdown).then(f => sendResponse({ success: true, filename: f }));
    }).catch(e => sendResponse({ success: false, error: e.message }));
    return true;
  }

  // --- sync_knowledge_base ---
  if (message.type === 'sync_knowledge_base') {
    (async () => {
      const s = await getSettings();
      if (!s.webdavUrl || !s.webdavUser) return sendResponse({ success: false, error: '请先配置 WebDAV 服务器' });
      if (s.webdavUrl.startsWith('http://')) return sendResponse({ success: false, error: '请使用 HTTPS URL，HTTP 会导致凭证明文传输' });

      const perm = await ensureWebdavPermission(s.webdavUrl);
      if (!perm.granted) return sendResponse({ success: false, needPermission: true, origin: perm.origin, error: perm.error || '需要授权访问该服务器' });

      // Determine remote path
      let profile;
      try { profile = await getProfileId(); } catch { profile = 'profile_unknown'; }
      const remotePath = `BookmarksCleaner/knowledge_base_${profile}.md`;

      const client = new WebDAVClient(s.webdavUrl, s.webdavUser, s.webdavPass);

      // Step 1: Pull remote KB
      const remoteMd = await client.get(remotePath);
      const localData = await loadKnowledgeBase();
      const localMd = localData?.markdown || '';

      let finalMd, mergeStats;

      if (!remoteMd && !localMd) {
        return sendResponse({ success: false, error: '本地和远程均为空，请先生成知识库' });
      }

      if (remoteMd && !localMd) {
        // Remote only: pull down
        finalMd = remoteMd;
        mergeStats = { action: 'pulled', remoteSections: 0, localSections: 0 };
      } else if (!remoteMd && localMd) {
        // Local only: push up
        finalMd = localMd;
        mergeStats = { action: 'pushed', remoteSections: 0, localSections: 0 };
      } else {
        // Both exist: merge
        const { merged, stats } = mergeKnowledgeBases(localMd, remoteMd);
        finalMd = merged;
        mergeStats = { action: stats.addedFromRemote > 0 ? 'merged' : 'unchanged', ...stats };
      }

      // Step 2: Save locally
      await saveKnowledgeBase(finalMd, mergeStats);

      // Step 3: Push merged version to remote
      const dirOk = await client.ensureDirectory('BookmarksCleaner');
      if (!dirOk) return sendResponse({ success: false, error: '创建远程目录 BookmarksCleaner 失败，请检查 WebDAV 权限' });
      const ok = await client.put(remotePath, finalMd);
      if (!ok) return sendResponse({ success: false, error: '上传失败，请检查 WebDAV 配置' });

      sendResponse({
        success: true,
        remotePath,
        action: mergeStats.action,
        addedFromRemote: mergeStats.addedFromRemote || 0,
      });
    })().catch(e => sendResponse({ success: false, error: e.message }));
    return true;
  }

  // --- test_webdav ---
  if (message.type === 'test_webdav') {
    (async () => {
      const { webdavUrl, webdavUser, webdavPass } = message.settings || {};
      if (!webdavUrl) return sendResponse({ ok: false, error: 'WebDAV URL 为空' });
      if (webdavUrl.startsWith('http://')) return sendResponse({ ok: false, error: '请使用 HTTPS URL，HTTP 会导致凭证明文传输' });

      const perm = await ensureWebdavPermission(webdavUrl);
      if (!perm.granted) return sendResponse({ ok: false, needPermission: true, origin: perm.origin, error: perm.error || '需要授权访问该服务器' });

      const client = new WebDAVClient(webdavUrl, webdavUser, webdavPass);
      const result = await client.testConnection();
      sendResponse(result);
    })().catch(e => sendResponse({ ok: false, error: e.message }));
    return true;
  }

  // --- test_deepseek ---
  if (message.type === 'test_deepseek') {
    (async () => {
      const { apiKey, model } = message.settings || {};
      if (!apiKey) return sendResponse({ ok: false, error: 'API Key 为空' });
      const client = new DeepSeekClient(apiKey, model || 'deepseek-v4-flash', await getPrompts());
      try {
        const resp = await client.chat([
          { role: 'user', content: 'hi' }
        ], { max_tokens: 10 });
        const reply = resp?.choices?.[0]?.message?.content || '';
        sendResponse({ ok: true, model: model || 'deepseek-v4-flash', reply: reply.substring(0, 50) });
      } catch (e) {
        sendResponse({ ok: false, error: e.message });
      }
    })().catch(e => sendResponse({ ok: false, error: e.message }));
    return true;
  }
});

chrome.action.onClicked.addListener((tab) => {
  chrome.sidePanel.open({ windowId: tab.windowId });
});

console.log('Bookmarks Cleaner service worker started');
