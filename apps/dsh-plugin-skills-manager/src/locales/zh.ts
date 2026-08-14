import type { SkillManagerKey } from './keys.ts'

/** Simplified-Chinese dictionary for the skills-manager namespace. */
export const zh: Record<SkillManagerKey, string> = {
  'nav.workspace-entry': '技能管理',
  'nav.session-tab': '技能',
  'nav.new-session': '技能管理',
  'nav.settings-section': '技能',

  'page.title': '技能管理',
  'page.description': '开启或禁用技能。作用域覆盖关系：会话 > 工作区 > 全局。支持 Shift 连续多选、Ctrl 独立多选后批量启用/禁用。',
  'page.global-title': '全局技能设置',
  'page.workspace-title': '工作区技能设置',
  'page.session-title': '会话技能设置',

  'scope.global': '全局',
  'scope.workspace': '工作区',
  'scope.session': '会话',
  'scope.inherit': '继承',

  'action.enable': '启用',
  'action.disable': '禁用',
  'action.enable-selected': '启用所选 ({count})',
  'action.disable-selected': '禁用所选 ({count})',
  'action.enable-all': '全部启用',
  'action.disable-all': '全部禁用',
  'action.reset': '重置',
  'action.save': '保存',
  'action.cancel': '取消',
  'action.close': '关闭',
  'action.clear-selection': '清除选择',
  'action.add-skill': '添加技能',
  'action.clear-search': '清除搜索',

  'status.enabled': '已启用',
  'status.disabled': '已禁用',
  'status.enabled-inherited': '已启用（继承）',
  'status.disabled-inherited': '已禁用（继承）',
  'status.no-skills': '未发现技能',
  'status.loading': '加载中…',

  'search.placeholder': '搜索技能…',

  'source.project-dsh': '项目 .dsh',
  'source.project-agents': '.agents',
  'source.user-dsh': '用户 .dsh',
  'source.user-agents': '用户 .agents',

  'hint.inherited-from': '继承自{scope}',
  'hint.overrides': '覆盖{scope}设置',
  'hint.default-enabled': '默认启用',
}
