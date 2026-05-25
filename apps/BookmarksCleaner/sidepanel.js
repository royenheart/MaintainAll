/**
 * Side panel logic — all 3 panels: Cleaner, Knowledge Base, Settings.
 */
import { renderMarkdown } from './lib/markdown_renderer.js';

// ============ DOM Refs ============
const $ = (id) => document.getElementById(id);
const els = {
  tabs: document.querySelectorAll('.tab'),
  panels: document.querySelectorAll('.panel'),

  // Cleaner
  previewBtn: $('previewBtn'), regexCleanBtn: $('regexCleanBtn'), aiCleanBtn: $('aiCleanBtn'), backupBtn: $('backupBtn'),
  aiStatus: $('aiStatus'),
  progressCard: $('progressCard'), phaseLabel: $('phaseLabel'),
  progressFill: $('progressFill'), progressMessage: $('progressMessage'), cancelProcessingBtn: $('cancelProcessingBtn'), log: $('log'),
  resultsCard: $('resultsCard'),
  statProcessed: $('statProcessed'), statRenamed: $('statRenamed'),
  statEntertainment: $('statEntertainment'), statTutorials: $('statTutorials'),
  changeDetails: $('changeDetails'), changeSummary: $('changeSummary'), changeList: $('changeList'),
  previewCard: $('previewCard'), previewCount: $('previewCount'), previewList: $('previewList'),

  // Knowledge Base
  kbGenerateBtn: $('kbGenerateBtn'), kbRefreshBtn: $('kbRefreshBtn'),
  kbImportBtn: $('kbImportBtn'), kbImportFile: $('kbImportFile'),
  kbExportBtn: $('kbExportBtn'), kbWebdavSyncBtn: $('kbWebdavSyncBtn'),
  kbContent: $('kbContent'), kbInfo: $('kbInfo'),

  // Settings
  apiKey: $('apiKey'), modelSelect: $('modelSelect'), modelCustom: $('modelCustom'),
  deepseekTestBtn: $('deepseekTestBtn'), deepseekResult: $('deepseekResult'),
  excludedFolders: $('excludedFolders'), autoBackup: $('autoBackup'),
  standardizeTitles: $('standardizeTitles'),
  webdavUrl: $('webdavUrl'), webdavUser: $('webdavUser'), webdavPass: $('webdavPass'),
  profileIdDisplay: $('profileIdDisplay'), webdavPathPreview: $('webdavPathPreview'),
  webdavTestBtn: $('webdavTestBtn'), webdavResult: $('webdavResult'),
  saveSettingsBtn: $('saveSettingsBtn'),
  // Rules
  rulesDetails: $('rulesDetails'), rulesEditor: $('rulesEditor'),
  resetRulesBtn: $('resetRulesBtn'), saveRulesBtn: $('saveRulesBtn'),
  // Prompts
  promptDetails: $('promptDetails'), promptList: $('promptList'),
  resetPromptsBtn: $('resetPromptsBtn'), savePromptsBtn: $('savePromptsBtn'),
  // Version
  versionInfo: $('versionInfo'), checkUpdateBtn: $('checkUpdateBtn'), updateResult: $('updateResult'),
};

// ============ Tab Switching ============
els.tabs.forEach(tab => {
  tab.addEventListener('click', () => {
    els.tabs.forEach(t => t.classList.remove('active'));
    els.panels.forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    const panelId = 'panel-' + tab.dataset.panel;
    document.getElementById(panelId)?.classList.add('active');

    if (tab.dataset.panel === 'knowledge') refreshKB();
    if (tab.dataset.panel === 'settings') { loadProfileId(); loadPrompts(); loadRules(); }
  });
});

// ============ Logger ============
function addLog(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `log-entry ${type}`;
  el.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
  els.log.appendChild(el);
  els.log.scrollTop = els.log.scrollHeight;
  return el;
}

const streamLogEntries = new Map();

function appendStreamLog({ streamId, title, delta, type = 'thinking' }) {
  const id = streamId || type;
  let entry = streamLogEntries.get(id);
  if (!entry) {
    const container = document.createElement('div');
    container.className = `log-entry stream ${type}`;

    const header = document.createElement('div');
    header.className = 'stream-title';
    header.textContent = `[${new Date().toLocaleTimeString()}] ${title || 'AI 思考'}`;

    const body = document.createElement('div');
    body.className = 'stream-body';

    container.appendChild(header);
    container.appendChild(body);
    els.log.appendChild(container);
    entry = { container, body };
    streamLogEntries.set(id, entry);
  }

  entry.body.textContent += delta || '';
  entry.body.scrollTop = entry.body.scrollHeight;
  els.log.scrollTop = els.log.scrollHeight;
}

// ============ Model Select ============
const MODEL_PRESETS = ['deepseek-v4-flash', 'deepseek-v4-pro', 'deepseek-chat', 'deepseek-reasoner'];

els.modelSelect.addEventListener('change', () => {
  if (els.modelSelect.value === '__custom__') {
    els.modelCustom.style.display = '';
    els.modelCustom.focus();
  } else {
    els.modelCustom.style.display = 'none';
  }
});

function getModel() {
  if (els.modelSelect.value === '__custom__') {
    return els.modelCustom.value.trim() || 'deepseek-v4-flash';
  }
  return els.modelSelect.value;
}

function setModel(value) {
  if (MODEL_PRESETS.includes(value)) {
    els.modelSelect.value = value;
    els.modelCustom.style.display = 'none';
  } else {
    els.modelSelect.value = '__custom__';
    els.modelCustom.style.display = '';
    els.modelCustom.value = value;
  }
}

// ============ WebDAV Profile ============
async function loadProfileId() {
  chrome.runtime.sendMessage({ type: 'get_profile_id' }, resp => {
    if (chrome.runtime.lastError || !resp?.profileId) {
      els.profileIdDisplay.textContent = '未知';
      els.webdavPathPreview.textContent = '...';
    } else {
      els.profileIdDisplay.textContent = resp.profileId;
      els.webdavPathPreview.textContent = resp.profileId;
    }
  });
}

// ============ Settings ============
async function loadSettings() {
  return new Promise(resolve => {
    chrome.runtime.sendMessage({ type: 'get_settings' }, s => {
      if (chrome.runtime.lastError) { resolve(null); return; }
      els.apiKey.value = s.apiKey || '';
      setModel(s.model || 'deepseek-v4-flash');
      els.excludedFolders.value = (s.excludedFolders || ['娱乐']).join('\n');
      els.autoBackup.checked = s.autoBackup !== false;
      els.standardizeTitles.checked = s.standardizeTitles !== false;
      els.webdavUrl.value = s.webdavUrl || '';
      els.webdavUser.value = s.webdavUser || '';
      els.webdavPass.value = s.webdavPass || '';
      resolve(s);
    });
  });
}

async function getSettingsFromUI() {
  return {
    apiKey: els.apiKey.value.trim(),
    model: getModel(),
    excludedFolders: els.excludedFolders.value
      .split('\n')
      .map(s => s.trim())
      .filter(Boolean),
    autoBackup: els.autoBackup.checked,
    standardizeTitles: els.standardizeTitles.checked,
    dryRun: false,
    webdavUrl: els.webdavUrl.value.trim(),
    webdavUser: els.webdavUser.value.trim(),
    webdavPass: els.webdavPass.value.trim(),
  };
}

async function saveSettings() {
  const settings = await getSettingsFromUI();
  return new Promise(resolve => {
    chrome.runtime.sendMessage({ type: 'save_settings', settings }, resp => {
      if (chrome.runtime.lastError) {
        addLog('保存失败', 'error');
        els.webdavResult.textContent = '✗ 设置保存失败';
        els.webdavResult.className = 'webdav-result fail';
        resolve(false);
        return;
      }
      addLog('✓ 设置已保存', 'success');
      els.webdavResult.textContent = '✓ 设置已保存';
      els.webdavResult.className = 'webdav-result ok';
      resolve(true);
    });
  });
}

// ============ Cleaner ============
let isProcessing = false;
let lastChanges = [];
let lastProgressKey = '';
let lastKBProgressKey = '';
let lastKBRenderAt = 0;

// Persistent listener for progress & changes from background
chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === 'progress_update') handleProgress(msg);
    if (msg.type === 'kb_progress_update') handleKBProgress(msg);
    if (msg.type === 'changes_result') showChangeDiff(msg.changes);
});

function handleProgress(msg) {
  const phaseLabels = {
    collecting: '收集书签',
    backup: '备份',
    classify: '分类',
    ai_analyze: 'AI 标题分析',
    ai_structure: 'AI 结构规划',
    ai_thinking: 'AI 思考',
    structure_apply: '分类整理',
    apply: '应用修改',
    kb_prepare: '知识库准备',
    kb_topic: '知识库章节',
    kb_stream: 'AI 正在生成正文',
    kb_topic_done: '章节完成',
    complete: '完成',
    cancelled: '已取消',
  };
  const total = Number(msg.total || 0);
  const done = Number(msg.done || 0);
  const percent = msg.phase === 'complete' ? 100 : (total > 0 ? Math.max(3, Math.min(99, Math.round((done / total) * 100))) : 3);

  els.progressCard.classList.remove('hidden');
  els.phaseLabel.textContent = phaseLabels[msg.phase] || msg.phase || '';
  els.progressFill.style.width = `${percent}%`;
  els.progressMessage.textContent = msg.message || '';

  if (msg.phase === 'ai_thinking') {
    appendStreamLog({
      streamId: msg.streamId,
      title: msg.title || 'AI 思考',
      delta: msg.delta || msg.message || '',
      type: 'thinking'
    });
    return;
  }

  const key = `${msg.phase}:${msg.message}`;
  if (key !== lastProgressKey && msg.phase !== 'kb_stream') {
    lastProgressKey = key;
    const logType = msg.phase === 'complete' ? 'success' : (msg.phase === 'cancelled' ? 'warning' : 'info');
    addLog(msg.message || '处理中...', logType);
  }

  if (msg.markdown && String(msg.phase || '').startsWith('kb_')) {
    renderKBProgress(msg);
  }

  if (msg.phase === 'complete') {
    isProcessing = false;
    els.regexCleanBtn.disabled = false;
    els.aiCleanBtn.disabled = false;
    els.cancelProcessingBtn.classList.add('hidden');
    els.progressFill.style.width = '100%';
    if (msg.summary) {
      els.resultsCard.classList.remove('hidden');
      els.statProcessed.textContent = msg.summary.processed || 0;
      els.statRenamed.textContent = `${msg.summary.renamed || 0}/${msg.summary.moved || 0}/${msg.summary.deleted || 0}`;
      els.statEntertainment.textContent = msg.summary.entertainment || 0;
      els.statTutorials.textContent = msg.summary.tutorials || 0;
    }
  }

  if (msg.phase === 'cancelled') {
    isProcessing = false;
    els.regexCleanBtn.disabled = false;
    els.aiCleanBtn.disabled = false;
    els.cancelProcessingBtn.classList.add('hidden');
    els.progressMessage.textContent = msg.message || '已取消';
  }
}

function handleKBProgress(msg) {
  const key = `${msg.phase}:${msg.message}`;
  if (key !== lastKBProgressKey && msg.phase !== 'kb_stream') {
    lastKBProgressKey = key;
    addLog(msg.message || '正在生成知识库...', msg.phase === 'kb_complete' ? 'success' : 'info');
  }
  renderKBProgress(msg);
}

function renderKBProgress(msg) {
  const total = Number(msg.total || 0);
  const done = Number(msg.done || 0);
  const percent = msg.phase === 'kb_complete' ? 100 : (total > 0 ? Math.max(5, Math.min(99, Math.round((done / total) * 100))) : 5);
  const now = Date.now();
  const shouldRender = msg.phase !== 'kb_stream' || now - lastKBRenderAt > 250;
  if (!shouldRender) return;
  lastKBRenderAt = now;

  els.kbInfo.textContent = `${msg.message || '正在生成知识库...'} ${total ? `(${done}/${total})` : ''}`;
  const markdown = msg.markdown || '';
  const body = markdown ? renderMarkdown(markdown) : '<div class="kb-empty"><h3>正在准备内容...</h3></div>';
  els.kbContent.innerHTML = `
    <div style="border:1px solid #2a2a4a;border-radius:6px;padding:8px;margin-bottom:10px;background:#17172a;">
      <div style="font-size:11px;color:#aaa;margin-bottom:6px;">${esc(msg.message || '正在生成知识库...')}</div>
      <div class="progress-bar"><div class="progress-fill" style="width:${percent}%"></div></div>
    </div>
    ${body}
  `;
}

function showChangeDiff(changes = []) {
  lastChanges = changes;
  els.changeList.innerHTML = '';
  els.changeSummary.textContent = changes.length ? `查看详细修改（${changes.length} 项）` : '没有标题修改';

  if (!changes.length) {
    els.changeList.innerHTML = '<div class="preview-item">没有检测到需要应用的标题修改</div>';
    return;
  }

  for (const item of changes) {
    const div = document.createElement('div');
    div.className = 'preview-item';
    const typeLabel = {
      rename: '改名',
      move: '移动',
      delete: '删除',
      delete_after_kb: '入库后删除',
      folder_rename: '分类改名',
      folder_merge: '分类合并',
    }[item.type] || '变更';
    div.innerHTML = `<span style="color:#7c83ff;">[${typeLabel}]</span> <span class="old">${esc(item.old)}</span><span class="arrow">→</span><span class="new">${esc(item.new)}</span><div style="color:#666;font-size:9px">${esc(item.folder || '')} ${esc(item.reason || '')}</div>`;
    els.changeList.appendChild(div);
  }
}

async function updateAIStatus() {
  const apiKey = els.apiKey.value.trim();
  if (!apiKey) {
    els.aiStatus.textContent = '⚠ 未配置 API Key，AI 整理不可用';
    els.aiStatus.style.color = '#f87171';
    return false;
  }
  // Quick ping test
  try {
    const result = await new Promise(resolve => {
      chrome.runtime.sendMessage({
        type: 'test_deepseek',
        settings: { apiKey, model: getModel() }
      }, resolve);
    });
    if (result?.ok) {
      els.aiStatus.textContent = '✓ API 已连接 (' + (result.model || '') + ')';
      els.aiStatus.style.color = '#4ade80';
      return true;
    } else {
      els.aiStatus.textContent = '⚠ ' + (result?.error || 'API 连接失败');
      els.aiStatus.style.color = '#f87171';
      return false;
    }
  } catch {
    els.aiStatus.textContent = '⚠ API 连接失败';
    els.aiStatus.style.color = '#f87171';
    return false;
  }
}

async function startCleaning(useAI = false) {
  if (isProcessing) return;
  isProcessing = true;
  els.regexCleanBtn.disabled = true;
  els.aiCleanBtn.disabled = true;
  els.resultsCard.classList.add('hidden');
  els.previewCard.classList.add('hidden');
  els.log.innerHTML = '';
  els.progressCard.classList.remove('hidden');
  els.progressFill.style.width = '0%';
  els.cancelProcessingBtn.classList.remove('hidden');
  streamLogEntries.clear();

  if (useAI) {
    els.phaseLabel.textContent = 'AI 连接检查';
    els.progressMessage.textContent = '正在检查 API 连接...';
    addLog('正在检查 DeepSeek API 连接...', 'info');
  }

  if (useAI && !(await updateAIStatus())) {
    addLog('请先配置 DeepSeek API Key 并通过测试连接', 'error');
    isProcessing = false;
    els.regexCleanBtn.disabled = false;
    els.aiCleanBtn.disabled = false;
    els.cancelProcessingBtn.classList.add('hidden');
    return;
  }
  await saveSettings();

  els.progressCard.classList.remove('hidden');
  els.progressFill.style.width = '0%';
  lastChanges = [];

  addLog(useAI ? '🤖 AI 整理中...' : '🔧 常规整理中...', 'info');

  chrome.runtime.sendMessage({ type: 'start_processing', useAI }, resp => {
    if (chrome.runtime.lastError || !resp?.success) {
      addLog(resp?.cancelled ? 'AI 整理已取消' : '处理失败: ' + (resp?.error || '未知错误'), resp?.cancelled ? 'warning' : 'error');
      isProcessing = false;
      els.regexCleanBtn.disabled = false;
      els.aiCleanBtn.disabled = false;
      els.cancelProcessingBtn.classList.add('hidden');
    }
  });
}

async function cancelProcessing() {
  if (!isProcessing) return;
  els.cancelProcessingBtn.disabled = true;
  els.cancelProcessingBtn.textContent = '取消中...';
  chrome.runtime.sendMessage({ type: 'cancel_processing' }, resp => {
    els.cancelProcessingBtn.disabled = false;
    els.cancelProcessingBtn.textContent = '取消整理';
    if (chrome.runtime.lastError || !resp?.success) {
      addLog('取消请求发送失败', 'error');
      return;
    }
    addLog(resp.cancelled ? '已请求取消，等待当前请求停止...' : '当前没有运行中的整理任务', 'warning');
  });
}

async function showPreview() {
  els.previewList.innerHTML = '';
  els.previewCard.classList.remove('hidden');
  els.previewCount.textContent = '加载中...';
  addLog('🔍 生成预览...', 'info');

  chrome.runtime.sendMessage({ type: 'get_preview' }, resp => {
    if (chrome.runtime.lastError || !resp?.success) { addLog('预览失败', 'error'); return; }
    const { changes, total } = resp;
    els.previewCount.textContent = `${total} 书签，${changes.length} 个标题将修改`;
    if (!changes.length) {
      els.previewList.innerHTML = '<div class="preview-item">✓ 所有标题已简洁，无需修改</div>';
    } else {
      for (const item of changes.slice(0, 100)) {
        const div = document.createElement('div');
        div.className = 'preview-item';
        div.innerHTML = `<span class="old">${esc(item.title)}</span><span class="arrow">→</span><span class="new">${esc(item.newTitle)}</span><div style="color:#666;font-size:9px">${esc(item.reason||'')}</div>`;
        els.previewList.appendChild(div);
      }
      if (changes.length > 100) {
        els.previewList.appendChild(Object.assign(document.createElement('div'), {className:'preview-item',textContent:`... 还有 ${changes.length-100} 项`}));
      }
    }
    addLog(`✓ 预览: ${changes.length} 个标题需修改`, 'success');
  });
}

async function backupOnly() {
  addLog('💾 备份中...', 'info');
  chrome.runtime.sendMessage({ type: 'backup_only' }, resp => {
    if (chrome.runtime.lastError || !resp?.success) { addLog('备份失败', 'error'); return; }
    addLog(`✓ 备份已下载: ${resp.filename}`, 'success');
  });
}

// ============ Knowledge Base ============
async function refreshKB() {
  chrome.runtime.sendMessage({ type: 'get_knowledge_base' }, resp => {
    if (chrome.runtime.lastError || !resp?.success || !resp.data) {
      els.kbContent.innerHTML = `<div class="kb-empty"><h3>📚 知识库为空</h3><p>点击「🤖 生成知识库」创建。</p></div>`;
      els.kbInfo.textContent = '';
      return;
    }
    renderKB(resp.data.markdown, { ...(resp.data.stats || {}), updatedAt: resp.data.updatedAt });
  });
}

function renderKB(markdown, stats) {
  const html = renderMarkdown(markdown);
  els.kbContent.innerHTML = html;
  if (stats) {
    els.kbInfo.textContent = `更新时间: ${new Date(stats.updatedAt || Date.now()).toLocaleString('zh-CN')} | ${stats.total || 0} 篇文章, ${stats.groups || 0} 个主题`;
  }
}

async function importKB() {
  els.kbImportFile.value = '';
  els.kbImportFile.click();
}

async function handleKBImportFile() {
  const file = els.kbImportFile.files?.[0];
  if (!file) return;
  if (!file.name.toLowerCase().endsWith('.md')) {
    addLog('导入失败: 请选择 .md 文件', 'error');
    return;
  }

  try {
    const markdown = await file.text();
    chrome.runtime.sendMessage({ type: 'import_knowledge_base', markdown, filename: file.name }, resp => {
      if (chrome.runtime.lastError || !resp?.success) {
        addLog('导入失败: ' + (resp?.error || '未知错误'), 'error');
        return;
      }
      renderKB(resp.data.markdown, { ...(resp.data.stats || {}), updatedAt: resp.data.updatedAt });
      addLog(`✓ 已导入知识库: ${file.name}`, 'success');
    });
  } catch (err) {
    addLog('导入失败: ' + (err.message || err), 'error');
  }
}

async function generateKB() {
  addLog('🤖 正在生成知识库...', 'info');
  els.kbGenerateBtn.disabled = true;
  els.kbGenerateBtn.textContent = '生成中...';

  // Switch to KB tab to show progress
  els.tabs.forEach(t => t.classList.remove('active'));
  els.panels.forEach(p => p.classList.remove('active'));
  document.querySelector('[data-panel="knowledge"]').classList.add('active');
  document.getElementById('panel-knowledge').classList.add('active');

  els.kbContent.innerHTML = `<div class="kb-empty"><h3>⏳ 正在生成知识库...</h3><p>AI 正在分析书签并提取知识点摘要</p></div>`;

  chrome.runtime.sendMessage({ type: 'generate_knowledge_base' }, resp => {
    els.kbGenerateBtn.disabled = false;
    els.kbGenerateBtn.textContent = '🤖 生成知识库';
    if (chrome.runtime.lastError || !resp?.success) {
      els.kbContent.innerHTML = `<div class="kb-empty"><h3>❌ 生成失败</h3><p>${resp?.error || '未知错误'}</p></div>`;
      addLog('知识库生成失败: ' + (resp?.error || ''), 'error');
      return;
    }
    renderKB(resp.markdown, resp.stats);
    addLog(`✓ 知识库已生成: ${resp.stats.total} 篇文章, ${resp.stats.groups} 个主题`, 'success');
  });
}

async function exportKB() {
  chrome.runtime.sendMessage({ type: 'export_knowledge_base' }, resp => {
    if (chrome.runtime.lastError || !resp?.success) { addLog('导出失败', 'error'); return; }
    addLog(`✓ 已导出: ${resp.filename}`, 'success');
  });
}

async function syncKBToWebdav() {
  els.kbWebdavSyncBtn.disabled = true;
  els.kbWebdavSyncBtn.textContent = '同步中...';

  const doSync = async () => {
    const saved = await saveSettings();
    if (!saved) {
      els.kbWebdavSyncBtn.disabled = false;
      els.kbWebdavSyncBtn.textContent = '☁ 同步到 WebDAV';
      return;
    }
    addLog('☁ 正在同步知识库...', 'info');
    els.kbInfo.textContent = '正在同步到 WebDAV...';
    chrome.runtime.sendMessage({ type: 'sync_knowledge_base' }, async resp => {
      if (chrome.runtime.lastError || !resp) {
        els.kbWebdavSyncBtn.disabled = false;
        els.kbWebdavSyncBtn.textContent = '☁ 同步到 WebDAV';
        els.kbInfo.textContent = 'WebDAV 同步失败: 请求超时';
        addLog('WebDAV 同步失败: 请求超时', 'error');
        return;
      }

      // Need permission — user gesture available here
      if (resp.needPermission && resp.origin) {
        const s = await chrome.runtime.sendMessage({ type: 'get_settings' }).catch(() => ({}));
        const granted = await requestWebdavPermission(resp.origin, s.webdavUrl || '');
        if (granted) {
          doSync(); // Retry
        } else {
          els.kbWebdavSyncBtn.disabled = false;
          els.kbWebdavSyncBtn.textContent = '☁ 同步到 WebDAV';
        }
        return;
      }

      els.kbWebdavSyncBtn.disabled = false;
      els.kbWebdavSyncBtn.textContent = '☁ 同步到 WebDAV';
      if (resp.success) {
        const act = { pulled: '已拉取远程知识库', pushed: '已推送本地知识库', merged: '已合并', unchanged: '无变化' };
        const actionText = act[resp.action] || '已同步';
        let msg = `✓ ${actionText}`;
        if (resp.addedFromRemote > 0) msg += `（新增 ${resp.addedFromRemote} 个远程章节）`;
        msg += ` (${resp.remotePath || ''})`;
        els.kbInfo.textContent = msg;
        addLog(msg, 'success');
        refreshKB();
      } else {
        els.kbInfo.textContent = 'WebDAV 同步失败: ' + (resp.error || '');
        addLog('WebDAV 同步失败: ' + (resp.error || ''), 'error');
      }
    });
  };
  doSync();
}

// ============ WebDAV Permission Helper ============
async function requestWebdavPermission(origin, url) {
  // Called from user gesture context — can show Chrome permission dialog
  const granted = await chrome.permissions.request({ origins: [origin] });
  if (!granted) {
    addLog('⛔ 未授权访问 ' + url, 'warning');
    return false;
  }
  addLog('✓ 已授权访问 ' + url, 'success');
  return true;
}

// ============ WebDAV Test ============
async function testWebdav() {
  els.webdavTestBtn.disabled = true;
  els.webdavTestBtn.textContent = '测试中...';
  els.webdavResult.textContent = '';
  els.webdavResult.className = 'webdav-result';

  const doTest = () => {
    chrome.runtime.sendMessage({
      type: 'test_webdav',
      settings: {
        webdavUrl: els.webdavUrl.value.trim(),
        webdavUser: els.webdavUser.value.trim(),
        webdavPass: els.webdavPass.value.trim(),
      }
    }, async resp => {
      if (chrome.runtime.lastError || !resp) {
        els.webdavTestBtn.disabled = false;
        els.webdavTestBtn.textContent = '🔍 测试连接';
        els.webdavResult.textContent = '✗ 请求失败';
        els.webdavResult.className = 'webdav-result fail';
        return;
      }

      // Need permission — user gesture available here
      if (resp.needPermission && resp.origin) {
        const granted = await requestWebdavPermission(resp.origin, els.webdavUrl.value.trim());
        if (granted) {
          doTest(); // Retry with permission granted
        } else {
          els.webdavTestBtn.disabled = false;
          els.webdavTestBtn.textContent = '🔍 测试连接';
          els.webdavResult.textContent = '✗ 未授权';
          els.webdavResult.className = 'webdav-result fail';
        }
        return;
      }

      els.webdavTestBtn.disabled = false;
      els.webdavTestBtn.textContent = '🔍 测试连接';
      if (resp.ok) {
        els.webdavResult.textContent = '✓ 连接成功';
        els.webdavResult.className = 'webdav-result ok';
      } else {
        els.webdavResult.textContent = '✗ ' + (resp.error || '连接失败');
        els.webdavResult.className = 'webdav-result fail';
      }
    });
  };
  doTest();
}

// ============ DeepSeek Test ============
async function testDeepseek() {
  els.deepseekTestBtn.disabled = true;
  els.deepseekTestBtn.textContent = '测试中...';
  els.deepseekResult.textContent = '';
  els.deepseekResult.className = 'webdav-result';
  chrome.runtime.sendMessage({
    type: 'test_deepseek',
    settings: {
      apiKey: els.apiKey.value.trim(),
      model: getModel(),
    }
  }, resp => {
    els.deepseekTestBtn.disabled = false;
    els.deepseekTestBtn.textContent = '🔍 测试连接';
    if (resp?.ok) {
      els.deepseekResult.textContent = '✓ 连接成功 (' + (resp.model || '') + ')';
      els.deepseekResult.className = 'webdav-result ok';
    } else {
      els.deepseekResult.textContent = '✗ ' + (resp?.error || '连接失败');
      els.deepseekResult.className = 'webdav-result fail';
    }
  });
}

// ============ Rules ============
async function loadRules() {
  chrome.runtime.sendMessage({ type: 'get_rules' }, resp => {
    if (chrome.runtime.lastError || !resp) return;
    els.rulesEditor.value = resp.rules.join('\n');
  });
}

async function saveRules() {
  const rules = els.rulesEditor.value.split('\n').map(s => s.trim()).filter(Boolean);
  chrome.runtime.sendMessage({ type: 'save_rules', rules }, resp => {
    if (resp?.success) addLog('✓ 规则已保存', 'success');
    else addLog('规则保存失败', 'error');
  });
}

async function resetRules() {
  chrome.runtime.sendMessage({ type: 'reset_rules' }, resp => {
    if (resp?.success) {
      els.rulesEditor.value = resp.rules.join('\n');
      addLog('✓ 已恢复默认规则', 'success');
    }
  });
}

// ============ Prompts ============
async function loadPrompts() {
  chrome.runtime.sendMessage({ type: 'get_prompts' }, resp => {
    if (chrome.runtime.lastError || !resp?.prompts) return;
    renderPromptEditor(resp.prompts);
  });
}

function renderPromptEditor(prompts) {
  const labels = {
    titleCleaner: '标题清理 System',
    titleCleanerUser: '标题清理 User（{items}替换为书签列表）',
    classify: '书签分类 System',
    classifyUser: '书签分类 User（{items}替换为书签列表）',
    structureOrganizer: '结构整理 System',
    structureOrganizerUser: '结构整理 User（{folders}和{items}替换）',
    topicSummary: '知识摘要 System',
    topicSummaryUser: '知识摘要 User（{topic}和{items}替换）',
  };
  let html = '';
  for (const [key, label] of Object.entries(labels)) {
    html += `<div style="margin-bottom:8px;"><label style="display:block;font-size:10px;color:#888;margin-bottom:2px;">${label}</label>`;
    html += `<textarea data-prompt="${key}" rows="4" style="width:100%;padding:5px;border:1px solid #2a2a4a;border-radius:4px;background:#1a1a2e;color:#e0e0e0;font-size:11px;resize:vertical;">${esc(prompts[key] || '')}</textarea></div>`;
  }
  els.promptList.innerHTML = html;
}

async function savePrompts() {
  const prompts = {};
  els.promptList.querySelectorAll('textarea').forEach(ta => {
    prompts[ta.dataset.prompt] = ta.value.trim();
  });
  chrome.runtime.sendMessage({ type: 'save_prompts', prompts }, resp => {
    if (resp?.success) addLog('✓ 提示词已保存', 'success');
    else addLog('提示词保存失败', 'error');
  });
}

async function resetPrompts() {
  chrome.runtime.sendMessage({ type: 'save_prompts', prompts: {} }, resp => {
    if (resp?.success) {
      loadPrompts();
      addLog('✓ 已恢复默认提示词', 'success');
    }
  });
}

// ============ Helpers ============
function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

// ============ Version / Update ============
async function showVersion() {
  chrome.runtime.sendMessage({ type: 'get_version' }, resp => {
    if (chrome.runtime.lastError) return;
    els.versionInfo.textContent = `v${resp.version}`;
  });
}

async function checkForUpdate() {
  els.updateResult.textContent = '⏳';
  els.updateResult.className = '';
  chrome.runtime.sendMessage({ type: 'check_update' }, resp => {
    if (chrome.runtime.lastError) return;
    if (resp.updateAvailable) {
      els.updateResult.innerHTML = `<span style="color:#fbbf24;">v${resp.latest} 可用</span>`;
    } else {
      els.updateResult.textContent = '✓ 已是最新';
      els.updateResult.style.color = '#4ade80';
    }
  });
}

// ============ Event Bindings ============
els.regexCleanBtn.addEventListener('click', () => startCleaning(false));
els.aiCleanBtn.addEventListener('click', () => startCleaning(true));
els.cancelProcessingBtn.addEventListener('click', cancelProcessing);
els.previewBtn.addEventListener('click', showPreview);
els.backupBtn.addEventListener('click', backupOnly);
els.saveSettingsBtn.addEventListener('click', saveSettings);
els.kbGenerateBtn.addEventListener('click', generateKB);
els.kbRefreshBtn.addEventListener('click', refreshKB);
els.kbImportBtn.addEventListener('click', importKB);
els.kbImportFile.addEventListener('change', handleKBImportFile);
els.kbExportBtn.addEventListener('click', exportKB);
els.kbWebdavSyncBtn.addEventListener('click', syncKBToWebdav);
els.webdavTestBtn.addEventListener('click', testWebdav);
els.deepseekTestBtn.addEventListener('click', testDeepseek);
els.checkUpdateBtn.addEventListener('click', checkForUpdate);
els.savePromptsBtn.addEventListener('click', savePrompts);
els.resetPromptsBtn.addEventListener('click', resetPrompts);
els.saveRulesBtn.addEventListener('click', saveRules);
els.resetRulesBtn.addEventListener('click', resetRules);

// ============ Init ============
(async () => {
  await loadSettings();
  showVersion();
  loadProfileId();
  updateAIStatus();
  addLog('✅ 插件已就绪', 'info');
})();
