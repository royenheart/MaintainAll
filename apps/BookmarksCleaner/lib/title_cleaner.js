/**
 * Client-side title standardization engine.
 * Fast regex-based cleaning without API calls.
 */

/** Default suffix patterns — one regex per line. Users can customize in settings. */
export const DEFAULT_TITLE_RULES = [
  // Chinese platform suffixes
  '\\s*-\\s*知[乎呼]$',
  '\\s*-\\s*博客园$',
  '\\s*-\\s*简书$',
  '\\s*-\\s*CSDN(博客)?$',
  '\\s*-\\s*(SegmentFault\\s*)?思否$',
  '\\s*-\\s*腾讯云(开发者社区)?[-\\s]*腾讯云$',
  '\\s*-\\s*云\\+\\s*社区[-\\s]*腾讯云.*$',
  '\\s*-\\s*51CTO\\.COM$',
  '\\s*-\\s*掘金$',
  '\\s*\\|\\s*Java\\s*全栈知识体系$',
  '\\s*\\|\\s*Java程序员进阶之路$',
  '\\s*-\\s*Java程序员进阶之路$',
  // English platform suffixes (case-insensitive via 'i' flag in regex creation)
  '\\s*-\\s*Stack\\s*Overflow$',
  '\\s*-\\s*GitHub(\\s*Marketplace)?$',
  '\\s*-\\s*DEV\\s*Community$',
  '\\s*-\\s*Google\\s*网上论坛$',
  '\\s*-\\s*[Ww]iki(pedia)?$',
  '\\s*-\\s*Bili[bbi]li$',
  '\\s*-\\s*Reddit$',
  '\\s*-\\s*NGA(玩家社区)?$',
  '\\s*-\\s*Pixiv$',
  '\\s*-\\s*Fanbox$',
  '\\s*-\\s*Patreon$',
  '\\s*-\\s*百度百科$',
  '\\s*-\\s*百度贴吧$',
  '\\s*-\\s*华为云$',
  '\\s*-\\s*开发者社区$',
  // Em-dash long suffix
  '\\s*—\\s*[^—]{25,}$',
];

/** Built rules from patterns array. */
function buildRules(patterns) {
  return patterns.map(r => new RegExp(r, ''));
}

export { buildRules };

/**
 * Standardize a bookmark title by removing common platform/author noise.
 * @param {string} title - Original bookmark title
 * @param {string[]} customPatterns - Optional custom regex patterns
 * @returns {{cleaned: string, changed: boolean, reason: string}}
 */
export function standardizeTitle(title, customPatterns = null) {
  if (!title) return { cleaned: title, changed: false, reason: '' };
  let t = title.trim();

  // Pre-process: remove URL anchors and fragment selectors
  t = t.replace(/#:~:text=.*$/, '');
  t = t.replace(/\s*#[^#]*_label\d+/g, '');

  // Remove "xxx的博客 - " prefix
  t = t.replace(/^[\w\u4e00-\u9fff]{2,4}的博客\s*[—\-]\s*/, '');

  // Apply custom/default patterns
  const patterns = customPatterns || DEFAULT_TITLE_RULES;
  let reason = '';

  for (const pattern of patterns) {
    const regex = new RegExp(pattern, 'i');
    if (regex.test(t)) {
      t = t.replace(regex, '');
      reason = reason ? `${reason}; ${pattern.substring(0, 20)}` : pattern.substring(0, 20);
    }
  }

  // Clean up
  t = t.trim();
  t = t.replace(/^[—\-]\s*/, '');
  t = t.replace(/\s*[—\-]\s*$/, '');
  t = t.replace(/\s+/g, ' ');

  // Cap length at 80
  if (t.length > 80) {
    const separators = [' — ', ' - ', ', ', '，', '。', ' (', '（'];
    for (const sep of separators) {
      const idx = t.lastIndexOf(sep);
      if (idx > 25 && idx < 75) { t = t.substring(0, idx).trim(); break; }
    }
    if (t.length > 80) t = t.substring(0, 77) + '...';
  }

  const changed = t !== title.trim();
  return { cleaned: t || title, changed, reason: changed ? reason : '' };
}

/**
 * Check if a bookmark is entertainment (client-side heuristic).
 * @param {string} title
 * @param {string} url
 * @param {string[]} folderPath
 * @param {string[]} excludedFolders - user-configured folders to skip
 * @returns {boolean}
 */
export function isEntertainment(title, url, folderPath = [], excludedFolders = ['娱乐']) {
  const fullPath = folderPath.join('/').toLowerCase();
  const u = url.toLowerCase();

  // Check excluded folders first
  for (const folder of excludedFolders) {
    if (fullPath.includes(folder.toLowerCase())) return true;
  }

  const keywords = [
    'nhentai', 'iwara', 'hentai', 'rule34', 'smutba', 'hanime', 'ohentai',
    'fanbox', 'patreon', 'kemono', 'pixiv',
    'minecraft', 'mcbbs', 'mcmod', 'curseforge', 'modrinth',
    'ff14', 'ffxiv',
    'bangumi', 'mikanani',
    'bilibili.com/video', 'bilibili.com/bangumi',
    'dlsite', 'galgame', 'ko-fi',
    'gamemale', 'loverslab',
    'acg.la', 'avacg', 'wnacg',
  ];

  for (const kw of keywords) {
    if (u.includes(kw)) return true;
  }

  return false;
}

/**
 * Check if a bookmark is a tutorial/article (likely summarizable).
 */
export function isTutorial(title, url) {
  const tutorialDomains = [
    'blog.csdn.net', 'zhuanlan.zhihu.com', 'cnblogs.com',
    'jianshu.com', 'segmentfault.com', 'juejin.cn',
    'cloud.tencent.com/developer', '51cto.com/article',
    'yiibai.com', 'runoob.com', 'dev.to',
  ];

  for (const d of tutorialDomains) {
    if (url.includes(d)) return true;
  }

  const tutorialKeywords = ['教程', '入门', '详解', '介绍', '如何使用', '笔记', '第.*课'];
  const t = title.toLowerCase();
  for (const kw of tutorialKeywords) {
    if (new RegExp(kw).test(t)) return true;
  }

  return false;
}
