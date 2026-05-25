const $ = (id) => document.getElementById(id);
const els = {
  apiKey: $('apiKey'), modelSelect: $('modelSelect'), modelCustom: $('modelCustom'),
  deepseekTestBtn: $('deepseekTestBtn'), deepseekResult: $('deepseekResult'),
  excludedFolders: $('excludedFolders'), autoBackup: $('autoBackup'), standardizeTitles: $('standardizeTitles'),
  webdavUrl: $('webdavUrl'), webdavUser: $('webdavUser'), webdavPass: $('webdavPass'),
  saveBtn: $('saveBtn'), toast: $('toast'),
  versionInfo: $('versionInfo'), checkUpdateBtn: $('checkUpdateBtn'), updateResult: $('updateResult'),
};

let toastTimer;
function showToast(msg, isErr = false) {
  const t = els.toast;
  t.textContent = msg; t.className = 'toast show' + (isErr ? ' error' : '');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('show'), 2000);
}

const MODEL_PRESETS = ['deepseek-v4-flash', 'deepseek-v4-pro', 'deepseek-chat', 'deepseek-reasoner'];

els.modelSelect.addEventListener('change', () => {
  els.modelCustom.style.display = els.modelSelect.value === '__custom__' ? '' : 'none';
  if (els.modelSelect.value === '__custom__') els.modelCustom.focus();
});

function getModel() {
  return els.modelSelect.value === '__custom__'
    ? (els.modelCustom.value.trim() || 'deepseek-v4-flash')
    : els.modelSelect.value;
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

async function load() {
  chrome.runtime.sendMessage({ type: 'get_settings' }, s => {
    if (chrome.runtime.lastError) return;
    els.apiKey.value = s.apiKey || '';
    setModel(s.model || 'deepseek-v4-flash');
    els.excludedFolders.value = (s.excludedFolders || ['娱乐']).join('\n');
    els.autoBackup.checked = s.autoBackup !== false;
    els.standardizeTitles.checked = s.standardizeTitles !== false;
    els.webdavUrl.value = s.webdavUrl || '';
    els.webdavUser.value = s.webdavUser || '';
    els.webdavPass.value = s.webdavPass || '';
  });
}

async function save() {
  chrome.runtime.sendMessage({
    type: 'save_settings',
    settings: {
      apiKey: els.apiKey.value.trim(),
      model: getModel(),
      excludedFolders: els.excludedFolders.value.split('\n').map(s => s.trim()).filter(Boolean),
      autoBackup: els.autoBackup.checked,
      standardizeTitles: els.standardizeTitles.checked,
      dryRun: false,
      webdavUrl: els.webdavUrl.value.trim(),
      webdavUser: els.webdavUser.value.trim(),
      webdavPass: els.webdavPass.value.trim(),
    }
  }, resp => {
    if (chrome.runtime.lastError) { showToast('保存失败', true); return; }
    showToast('✓ 设置已保存');
  });
}

async function testDeepseek() {
  els.deepseekTestBtn.disabled = true;
  els.deepseekTestBtn.textContent = '测试中...';
  els.deepseekResult.textContent = '';
  els.deepseekResult.className = 'test-result';
  chrome.runtime.sendMessage({
    type: 'test_deepseek',
    settings: { apiKey: els.apiKey.value.trim(), model: getModel() }
  }, resp => {
    els.deepseekTestBtn.disabled = false;
    els.deepseekTestBtn.textContent = '🔍 测试连接';
    if (resp?.ok) {
      els.deepseekResult.textContent = '✓ 连接成功 (' + (resp.model || '') + ')';
      els.deepseekResult.className = 'test-result ok';
    } else {
      els.deepseekResult.textContent = '✗ ' + (resp?.error || '连接失败');
      els.deepseekResult.className = 'test-result fail';
    }
  });
}

async function showVersion() {
  chrome.runtime.sendMessage({ type: 'get_version' }, resp => {
    if (chrome.runtime.lastError) return;
    els.versionInfo.textContent = `v${resp.version}`;
  });
}

async function checkForUpdate() {
  els.updateResult.textContent = '⏳';
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

els.saveBtn.addEventListener('click', save);
els.deepseekTestBtn.addEventListener('click', testDeepseek);
els.checkUpdateBtn.addEventListener('click', checkForUpdate);
load();
showVersion();
