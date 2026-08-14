/**
 * The skills-manager locale namespace key list. This is the single source of
 * truth for bilingual completeness: `zh.ts` and `en.ts` are typed against it,
 * and the unit tests assert both dictionaries cover exactly these keys with
 * matching `{placeholder}` sets.
 */

export const SKILL_MANAGER_KEYS = [
  // navigation / labels
  'nav.workspace-entry',
  'nav.session-tab',
  'nav.settings-section',

  // page copy
  'page.title',
  'page.description',
  'page.global-title',
  'page.workspace-title',
  'page.session-title',

  // scopes
  'scope.global',
  'scope.workspace',
  'scope.session',
  'scope.inherit',

  // actions
  'action.enable',
  'action.disable',
  'action.enable-selected',
  'action.disable-selected',
  'action.enable-all',
  'action.disable-all',
  'action.reset',
  'action.save',
  'action.cancel',
  'action.close',
  'action.clear-selection',
  'action.add-skill',

  // status
  'status.enabled',
  'status.disabled',
  'status.enabled-inherited',
  'status.disabled-inherited',
  'status.no-skills',
  'status.loading',

  // search
  'search.placeholder',

  // sources
  'source.project-dsh',
  'source.project-agents',
  'source.user-dsh',
  'source.user-agents',

  // hints (templated)
  'hint.inherited-from',
  'hint.overrides',
  'hint.default-enabled',
] as const

export type SkillManagerKey = (typeof SKILL_MANAGER_KEYS)[number]

/** Flat locale dictionary shape (key -> template string with {name} placeholders). */
export type LocaleDict = Record<string, string>

/** The two shipped locales, mirroring `@deepseek-ai/dsh-client-locale`'s `LocaleId`. */
export type LocaleId = 'zh' | 'en'
