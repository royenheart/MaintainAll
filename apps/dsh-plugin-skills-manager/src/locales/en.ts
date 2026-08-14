import type { SkillManagerKey } from './keys.ts'

/** English dictionary for the skills-manager namespace. */
export const en: Record<SkillManagerKey, string> = {
  'nav.workspace-entry': 'Manage skills',
  'nav.session-tab': 'Skills',
  'nav.settings-section': 'Skills',

  'page.title': 'Skill Management',
  'page.description': 'Enable or disable skills. Scope precedence: session > workspace > global. Shift-select a range or Ctrl-select individual skills to batch enable/disable.',
  'page.global-title': 'Global Skill Settings',
  'page.workspace-title': 'Workspace Skill Settings',
  'page.session-title': 'Session Skill Settings',

  'scope.global': 'Global',
  'scope.workspace': 'Workspace',
  'scope.session': 'Session',
  'scope.inherit': 'Inherit',

  'action.enable': 'Enable',
  'action.disable': 'Disable',
  'action.enable-selected': 'Enable ({count})',
  'action.disable-selected': 'Disable ({count})',
  'action.enable-all': 'Enable all',
  'action.disable-all': 'Disable all',
  'action.reset': 'Reset',
  'action.save': 'Save',
  'action.cancel': 'Cancel',
  'action.close': 'Close',
  'action.clear-selection': 'Clear selection',
  'action.add-skill': 'Add skill',

  'status.enabled': 'Enabled',
  'status.disabled': 'Disabled',
  'status.enabled-inherited': 'Enabled (inherited)',
  'status.disabled-inherited': 'Disabled (inherited)',
  'status.no-skills': 'No skills found',
  'status.loading': 'Loading…',

  'search.placeholder': 'Search skills…',

  'source.project-dsh': 'Project .dsh',
  'source.project-agents': '.agents',
  'source.user-dsh': 'User .dsh',
  'source.user-agents': 'User .agents',

  'hint.inherited-from': 'Inherited from {scope}',
  'hint.overrides': 'Overrides {scope}',
  'hint.default-enabled': 'Enabled by default',
}
