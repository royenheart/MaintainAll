/**
 * Client (browser) half of the skills-manager plugin.
 *
 * Data flow (no custom RPC — reuses existing wire surfaces):
 *   - OVERRIDES: `ctx.settingsScope.bind({ namespace: 'skills-manager' })`, the
 *     same settings transport every preference row uses;
 *   - SKILL LIST: `ctx.connection.api.skills.list({ sessionId })`, the same
 *     read-only catalog the `/`-trigger skill picker uses.
 *
 * Skill discovery is session-addressed (the RPC resolves the session's
 * workspace cwd server-side). The GLOBAL settings page therefore follows the
 * current session (read from `ctx.sessions.list.current`) so it can list the
 * skills available right now, while the SESSION tab uses its own session id.
 *
 * Surfaces:
 *   - `settings.section` page for GLOBAL skill settings;
 *   - `conversation.view` tab ("技能") beside the trajectory tab for
 *     EXISTING sessions;
 *   - `sidebar.workspaces.entry` per-workspace row (declared by the workspace
 *     browser when present — see registerWorkspaceEntry).
 */

import * as React from 'react'
import type { Context } from '@deepseek-ai/cordis'
// The `Context.locale` / `Context.slots` / `Context.settingsScope` /
// `Context.sessions` client-side augmentations live in each package's
// `./client` types subpath (not the root).
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-runtime/client'
import type {} from '@deepseek-ai/dsh-client-ui-settings/client'
import type {} from '@deepseek-ai/dsh-client-ui-slots'

import { dictionaries, NAMESPACE } from './locales/index.ts'
import type { SkillManagerKey } from './locales/keys.ts'
import { normalizeSection, overrideFieldFor, setOverrideInSection, setOverridesInSection, SETTINGS_NAMESPACE, toStoreData, type SkillsManagerSection } from './core/settings-schema.ts'
import { resolveSkillState, type ScopeKind } from './core/scope.ts'
import { isGlobalSource, isManagedSource } from './core/skill-filter.ts'

// Merge the skills-manager namespace into the locale key map so
// `ctx.locale.register('skills-manager', ...)` type-checks.
declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    'skills-manager': SkillManagerKey
  }
}

type Translate = (key: string, params?: Record<string, string>) => string

/** The settings-scope face this client consumes. */
interface BoundScope {
  getSnapshot(): { status: string; value?: SkillsManagerSection }
  subscribe(listener: () => void): () => void
  set(field: string, value: unknown): Promise<void>
  unset(field: string): Promise<void>
}

/** The skills RPC face this client consumes. */
interface SkillsApiFace {
  list(
    request: { sessionId?: string; cwd?: string },
    signal?: AbortSignal,
  ): Promise<{ result: { ok: boolean; value?: { skills: readonly SkillEntry[] }; error?: { message?: string } } }>
}

interface SkillEntry {
  readonly name: string
  readonly description: string
  readonly whenToUse?: string
  readonly modelInvocable: boolean
  readonly source: string
}

/** The sessions-service face we read the current session from (global discovery). */
interface SessionsFace {
  list: {
    getSnapshot(): { current?: string }
    subscribe(fn: () => void): () => void
  }
}

// 声明插件注入的服务 (Cordis guard: 直接访问 ctx.<name> 必须先声明 inject)。
export const inject = ['locale', 'settingsScope', 'slots', 'connection', 'sessions']

export function apply(ctx: Context): void {
  ctx.locale.register(NAMESPACE, dictionaries)
  const t = ctx.locale.bind(NAMESPACE) as unknown as Translate

  const scope = ctx.settingsScope.bind({ namespace: SETTINGS_NAMESPACE, decode: normalizeSection }) as unknown as BoundScope
  // The browser reaches the skills RPC through the connection service's api face
  // (the same `ctx.get('connection').api.skills` the `/`-trigger picker uses).
  const connection = ctx.get('connection') as unknown as { api?: { skills?: SkillsApiFace } } | undefined
  const api = connection?.api

  // The current session, for global-scope discovery. Defensive: the runtime
  // always provides it, but a minimal mount may not.
  let sessions: SessionsFace | undefined
  try {
    sessions = ctx.sessions as unknown as SessionsFace
  } catch {
    sessions = undefined
  }

  const slots = ctx.slots
  if (!slots) return

  injectStyles()

  registerSettingsSection(slots, t, scope, api, sessions)
  registerSessionTab(slots, t, scope, api)
  registerNewSessionControl(slots, t, scope, api)
  registerWorkspaceEntry(slots, t, scope, api)
}

function SkillPanel(props: {
  title: string
  scopeKind: ScopeKind
  scopeKey?: string
  sessionId?: string
  t: Translate
  scope: BoundScope
  api?: { skills?: SkillsApiFace }
  sessions?: SessionsFace
}): React.ReactElement {
  const { title, scopeKind, scopeKey, sessionId, t, scope, api, sessions } = props
  const [, force] = React.useReducer((n: number) => n + 1, 0)
  const [entries, setEntries] = React.useState<readonly SkillEntry[]>([])
  const [newName, setNewName] = React.useState('')
  const [selection, setSelection] = React.useState<ReadonlySet<string>>(new Set<string>())
  const [anchor, setAnchor] = React.useState<string | null>(null)

  React.useEffect(() => scope.subscribe(() => force()), [scope])

  // Follow the current session so the GLOBAL page lists the skills available
  // right now (the skill.list RPC is session-addressed).
  const [currentSessionId, setCurrentSessionId] = React.useState<string | undefined>(
    () => sessions?.list.getSnapshot().current,
  )
  React.useEffect(() => {
    if (!sessions) return
    return sessions.list.subscribe(() => setCurrentSessionId(sessions.list.getSnapshot().current))
  }, [sessions])

  // The session id used for skill discovery:
  //   - session: its own id;
  //   - global:  the current session (the RPC is session-addressed; its skills
  //              are filtered to global sources below);
  //   - workspace: a session accounted under that workspace, provided by the
  //                workspace entry owner.
  // Discovery address: session/global use a session id (the RPC resolves its
  // cwd), workspace uses the workspace path directly (a session-addressed
  // lookup needs an attached session, which a workspace may not have).
  const discoverySessionId =
    scopeKind === 'session' ? (scopeKey ?? sessionId)
    : scopeKind === 'global' ? currentSessionId
    : undefined
  const discoveryCwd = scopeKind === 'workspace' ? scopeKey : undefined

  React.useEffect(() => {
    if (!api?.skills) {
      setEntries([])
      return
    }
    const request = scopeKind === 'workspace'
      ? (discoveryCwd === undefined ? undefined : { cwd: discoveryCwd })
      : (discoverySessionId === undefined ? undefined : { sessionId: discoverySessionId })
    if (request === undefined) {
      setEntries([])
      return
    }
    const controller = new AbortController()
    api.skills.list(request, controller.signal)
      .then((r) => {
        if (r.result.ok && r.result.value) setEntries(r.result.value.skills)
      })
      .catch(() => {})
    return () => controller.abort()
  }, [api, scopeKind, discoverySessionId, discoveryCwd])

  const snapshot = scope.getSnapshot()
  const section = snapshot.value ?? {}
  const store = toStoreData(section)

  const view = { workspacePath: scopeKind === 'workspace' ? scopeKey : undefined, sessionId: scopeKind === 'session' ? (scopeKey ?? sessionId) : undefined }

  // Union of skill.list names and every name already carrying an override, so a
  // disabled skill stays visible (and re-enableable). Discovered names are
  // limited to the manager's sources; the GLOBAL page further limits to
  // globally-available (user-level) sources, since a workspace-scoped skill has
  // no meaning at the global scope.
  const names = new Set<string>()
  for (const entry of entries) {
    if (!isManagedSource(entry.source)) continue
    if (scopeKind === 'global' && !isGlobalSource(entry.source)) continue
    names.add(entry.name)
  }
  for (const name of Object.keys(section.global ?? {})) names.add(name)
  for (const scoped of Object.values(section.workspaces ?? {})) for (const name of Object.keys(scoped)) names.add(name)
  for (const scoped of Object.values(section.sessions ?? {})) for (const name of Object.keys(scoped)) names.add(name)
  const sortedNames = [...names].sort()
  const rows = sortedNames.map((name) => ({
    name,
    description: entries.find((e) => e.name === name)?.description ?? '',
    state: resolveSkillState(store, name, view),
  }))

  const toggle = (name: string, enabled: boolean) => {
    const { field, value } = setOverrideInSection(section, scopeKind, scopeKey ?? sessionId, name, enabled)
    scope.set(field, value).catch(() => {})
  }

  const toggleSelected = (enabled: boolean) => {
    const { field, value } = setOverridesInSection(section, scopeKind, scopeKey ?? sessionId, [...selection], enabled)
    scope.set(field, value).catch(() => {})
    setSelection(new Set<string>())
    setAnchor(null)
  }

  const clearSelection = () => {
    setSelection(new Set<string>())
    setAnchor(null)
  }

  const resetScope = () => {
    scope.unset(overrideFieldFor(scopeKind)).catch(() => {})
    clearSelection()
  }

  // Add a skill by name (useful for scopes where the session-addressed
  // skill.list is unavailable); the new override starts as "disabled" so it
  // appears in the list and can be toggled.
  const addSkill = () => {
    const name = newName.trim()
    if (!name) return
    const { field, value } = setOverrideInSection(section, scopeKind, scopeKey ?? sessionId, name, false)
    scope.set(field, value).catch(() => {})
    setNewName('')
  }

  // Shift = continuous range from the last anchor; Ctrl/Cmd = independent
  // toggle; plain click = single selection.
  const select = (name: string, event: { shiftKey?: boolean; ctrlKey?: boolean; metaKey?: boolean }) => {
    if (event.shiftKey && anchor) {
      const i1 = sortedNames.indexOf(anchor)
      const i2 = sortedNames.indexOf(name)
      if (i1 >= 0 && i2 >= 0) {
        const [lo, hi] = i1 < i2 ? [i1, i2] : [i2, i1]
        setSelection(new Set(sortedNames.slice(lo, hi + 1)))
        return
      }
    }
    if (event.ctrlKey || event.metaKey) {
      const next = new Set(selection)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      setSelection(next)
      setAnchor(name)
      return
    }
    setSelection(new Set([name]))
    setAnchor(name)
  }

  return React.createElement(
    'div',
    { className: 'skills-manager-panel' },
    React.createElement('header', { className: 'skills-manager-panel__header' },
      React.createElement('h2', null, title),
      React.createElement('p', { className: 'skills-manager-panel__description' }, t('page.description')),
    ),
    React.createElement('div', { className: 'skills-manager-toolbar' },
      selection.size > 0
        ? React.createElement(React.Fragment, null,
            React.createElement('button', { className: 'skills-manager-btn skills-manager-btn--primary', onClick: () => toggleSelected(true) }, t('action.enable-selected', { count: String(selection.size) })),
            React.createElement('button', { className: 'skills-manager-btn', onClick: () => toggleSelected(false) }, t('action.disable-selected', { count: String(selection.size) })),
            React.createElement('button', { className: 'skills-manager-btn', onClick: clearSelection }, t('action.clear-selection')),
          )
        : null,
      React.createElement('button', { className: 'skills-manager-btn', onClick: resetScope }, t('action.reset')),
      React.createElement('div', { className: 'skills-manager-add' },
        React.createElement('input', { value: newName, placeholder: 'skill-name', onChange: (e: { target: { value: string } }) => setNewName(e.target.value) }),
        React.createElement('button', { className: 'skills-manager-btn', onClick: addSkill }, t('action.add-skill')),
      ),
    ),
    rows.length === 0
      ? React.createElement('p', { className: 'skills-manager-empty' }, t('status.no-skills'))
      : React.createElement('ul', { className: 'skills-manager-list' }, rows.map((row) => {
          const selected = selection.has(row.name)
          const originLabel = row.state.origin === 'default'
            ? t('hint.default-enabled')
            : t('hint.inherited-from', { scope: t('scope.' + row.state.origin) })
          return React.createElement('li', {
            key: row.name,
            className: 'skills-manager-row' + (selected ? ' skills-manager-row--selected' : ''),
            title: [row.description, originLabel].filter(Boolean).join(' · ') || row.name,
            onClick: (e: { shiftKey?: boolean; ctrlKey?: boolean; metaKey?: boolean }) => select(row.name, e),
          },
            React.createElement('input', {
              type: 'checkbox',
              className: 'skills-manager-row__check',
              checked: selected,
              onChange: () => {},
              onClick: (e: { stopPropagation: () => void }) => {
                e.stopPropagation()
                select(row.name, { ctrlKey: true })
              },
            }),
            React.createElement('span', { className: 'skills-manager-row__name' }, row.name),
            React.createElement('span', {
              className: 'skills-manager-row__status' + (row.state.enabled ? ' skills-manager-row__status--enabled' : ' skills-manager-row__status--disabled'),
            }, row.state.enabled ? t('status.enabled') : t('status.disabled')),
            React.createElement('button', {
              className: 'skills-manager-btn',
              onClick: (e: { stopPropagation: () => void }) => { e.stopPropagation(); toggle(row.name, !row.state.enabled) },
            }, row.state.enabled ? t('action.disable') : t('action.enable')),
          )
        })),
  )
}

function registerSettingsSection(slots: Slots, t: Translate, scope: BoundScope, api?: { skills?: SkillsApiFace }, sessions?: SessionsFace): void {
  slots.register({ name: 'settings.section', id: 'skills-manager', order: 900, label: t('nav.settings-section') }, () =>
    React.createElement(SkillPanel, { title: t('page.global-title'), scopeKind: 'global', t, scope, api, sessions }),
  )
}

function registerSessionTab(slots: Slots, t: Translate, scope: BoundScope, api?: { skills?: SkillsApiFace }): void {
  slots.register({ name: 'conversation.view', id: 'skills', order: 200, label: t('nav.session-tab') }, (inject: { sessionId?: string }) =>
    React.createElement(SkillPanel, { title: t('page.session-title'), scopeKind: 'session', sessionId: inject.sessionId, t, scope, api }),
  )
}

function registerNewSessionControl(slots: Slots, t: Translate, scope: BoundScope, api?: { skills?: SkillsApiFace }): void {
  slots.register({ name: 'conversation.input.right', id: 'skills-manager', order: 100 }, (inject: { sessionId?: string }) =>
    React.createElement(SkillsTrigger, { t, scope, api, sessionId: inject.sessionId }),
  )
}

/**
 * A "技能" trigger beside the model selector for a (new) session: a
 * select-like button that pops a self-contained overlay hosting the session
 * skill panel.
 */
function SkillsTrigger(props: {
  t: Translate
  scope: BoundScope
  api?: { skills?: SkillsApiFace }
  sessionId?: string
}): React.ReactElement {
  const { t, scope, api, sessionId } = props
  const [open, setOpen] = React.useState(false)

  return React.createElement(
    React.Fragment,
    null,
    React.createElement('button', {
      className: 'skills-manager-trigger',
      onClick: () => setOpen(true),
      'aria-label': t('nav.new-session'),
      'aria-haspopup': 'dialog',
      'aria-expanded': open,
    },
      React.createElement('span', { className: 'skills-manager-trigger__label' }, t('nav.new-session')),
      React.createElement('svg', {
        width: 14,
        height: 14,
        viewBox: '0 0 14 14',
        fill: 'none',
        className: 'skills-manager-trigger__chevron' + (open ? ' skills-manager-trigger__chevron--open' : ''),
        'aria-hidden': true,
      },
        React.createElement('path', {
          d: 'M11.8486 5.5L11.4238 5.92383L8.69727 8.65137C8.44157 8.90706 8.21562 9.13382 8.01172 9.29785C7.79912 9.46883 7.55595 9.61756 7.25 9.66602C7.08435 9.69222 6.91565 9.69222 6.75 9.66602C6.44405 9.61756 6.20088 9.46883 5.98828 9.29785C5.78438 9.13382 5.55843 8.90706 5.30273 8.65137L2.57617 5.92383L2.15137 5.5L3 4.65137L3.42383 5.07617L6.15137 7.80273C6.42595 8.07732 6.59876 8.24849 6.74023 8.3623C6.87291 8.46904 6.92272 8.47813 6.9375 8.48047C6.97895 8.48703 7.02105 8.48703 7.0625 8.48047C7.07728 8.47813 7.12709 8.46904 7.25977 8.3623C7.40124 8.24849 7.57405 8.07732 7.84863 7.80273L10.5762 5.07617L11 4.65137L11.8486 5.5Z',
          fill: 'currentColor',
        }),
      ),
    ),
    open && React.createElement(
      'div',
      { className: 'skills-manager-overlay', onClick: () => setOpen(false) },
      React.createElement(
        'div',
        { className: 'skills-manager-modal', onClick: (event: { stopPropagation: () => void }) => event.stopPropagation() },
        React.createElement('button', { className: 'skills-manager-close', onClick: () => setOpen(false) }, t('action.close')),
        React.createElement(SkillPanel, { title: t('page.session-title'), scopeKind: 'session', sessionId, t, scope, api }),
      ),
    ),
  )
}

/**
 * Workspace-level entry: a per-workspace "技能" row rendered by the workspace
 * browser, styled like a session row. This needs a child slot the browser
 * declares (`sidebar.workspaces.entry`); the try/catch keeps the plugin
 * loading when an older workspace browser does not declare it.
 */
function registerWorkspaceEntry(
  slots: Slots,
  t: Translate,
  scope: BoundScope,
  api?: { skills?: SkillsApiFace },
): void {
  try {
    slots.register({ name: 'sidebar.workspaces.entry', id: 'skills-manager', label: t('nav.workspace-entry'), order: 100 }, (inject: { workspacePath?: string }) =>
      React.createElement(SkillPanel, { title: t('page.workspace-title'), scopeKind: 'workspace', scopeKey: inject.workspacePath, t, scope, api }),
    )
  } catch {
    // Slot not declared by the current workspace browser.
  }
}

/** Inject one scoped stylesheet (idempotent) matching dsh's design tokens. */
function injectStyles(): void {
  if (typeof document === 'undefined') return
  if (document.getElementById('skills-manager-styles')) return
  const style = document.createElement('style')
  style.id = 'skills-manager-styles'
  style.textContent = css
  document.head.appendChild(style)
}

const css = `.skills-manager-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  max-height: 80vh;
  overflow: hidden;
  box-sizing: border-box;
  color: var(--dsw-alias-label-primary);
  background: var(--dsw-alias-bg-layer-1);
  font: var(--dsw-font-xxs-12);
}
.skills-manager-panel__header {
  padding: 12px 16px;
  border-bottom: 1px solid var(--dsw-alias-border-l2);
}
.skills-manager-panel__header h2 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
}
.skills-manager-panel__description {
  margin: 4px 0 0;
  color: var(--dsw-alias-label-tertiary);
}
.skills-manager-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  row-gap: 6px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--dsw-alias-border-l2);
}
.skills-manager-btn {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 8px;
  border: 0;
  border-radius: 3px;
  color: var(--dsw-alias-label-tertiary);
  background: transparent;
  cursor: pointer;
  font: var(--dsw-font-xxs-12);
}
.skills-manager-btn:hover {
  color: var(--dsw-alias-label-primary);
  background: var(--dsw-alias-interactive-bg-hover);
}
.skills-manager-btn:focus-visible {
  outline: 1px solid var(--dsw-alias-state-business-primary);
  outline-offset: 1px;
}
.skills-manager-btn--primary {
  color: var(--dsw-alias-state-business-primary);
}
.skills-manager-add {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
}
.skills-manager-add input {
  height: 20px;
  padding: 0 6px;
  border: 1px solid var(--dsw-alias-border-l2);
  border-radius: 3px;
  color: var(--dsw-alias-label-primary);
  background: var(--dsw-alias-bg-layer-2);
  font: var(--dsw-font-xxs-12);
}
.skills-manager-list {
  flex: 1;
  min-height: 0;
  margin: 0;
  padding: 6px;
  overflow-y: auto;
  overflow-x: hidden;
  list-style: none;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 6px;
  align-content: start;
}
.skills-manager-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 32px;
  padding: 4px 10px;
  border: 1px solid var(--dsw-alias-border-l2);
  border-radius: 4px;
  cursor: pointer;
}
.skills-manager-row:hover {
  background: var(--dsw-alias-interactive-bg-hover);
}
.skills-manager-row--selected {
  background: var(--dsw-alias-interactive-bg-hover);
  border-color: var(--dsw-alias-state-business-primary);
}
.skills-manager-row__check {
  flex: none;
  width: 13px;
  height: 13px;
  margin: 0;
  accent-color: var(--dsw-alias-state-business-primary);
}
.skills-manager-row__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}
.skills-manager-row__status {
  flex: none;
  font-size: 11px;
}
.skills-manager-row__status--enabled {
  color: var(--dsw-alias-state-business-primary);
}
.skills-manager-row__status--disabled {
  color: var(--dsw-alias-label-dimmed);
}
.skills-manager-empty {
  padding: 16px;
  color: var(--dsw-alias-label-tertiary);
}
/* Composer trigger: a select-like chip beside the model selector
   (matches ui-model-selection's ToggleButton). */
.skills-manager-trigger {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  height: 28px;
  padding: 0 4px 0 8px;
  border: none;
  border-radius: 24px;
  outline: none;
  background: transparent;
  color: var(--dsw-alias-label-secondary);
  font-size: 13px;
  line-height: 20px;
  font-weight: 500;
  cursor: pointer;
}
.skills-manager-trigger:hover {
  background: var(--dsw-alias-interactive-bg-hover);
}
.skills-manager-trigger:focus-visible {
  box-shadow: 0 0 0 2px var(--dsw-alias-border-l3);
}
.skills-manager-trigger__label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.skills-manager-trigger__chevron {
  flex: 0 0 auto;
  color: var(--dsw-alias-label-caption);
  transition: transform 120ms ease;
}
.skills-manager-trigger__chevron--open {
  transform: rotate(180deg);
}
/* Centered overlay + dialog hosting the session panel (Modal primitive
   material: mask + blur, r24 dialog, layer-2 fill, inverted border). */
.skills-manager-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: var(--dsw-alias-bg-mask-1);
  backdrop-filter: var(--dsw-mask-blur);
}
.skills-manager-modal {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  width: min(560px, 90vw);
  max-height: 80vh;
  overflow: hidden;
  border: 1px solid var(--dsw-alias-border-inverted);
  border-radius: 24px;
  background: var(--dsw-alias-bg-layer-2);
  box-shadow: var(--dsw-shadow-lv3);
}
/* Let the hosted panel fill the dialog: the panel's own height:100% has
   no definite parent here, so turn it into a shrinkable flex item whose
   height is bounded by the dialog's max-height instead. */
.skills-manager-modal > .skills-manager-panel {
  height: auto;
  flex: 1 1 auto;
  min-height: 0;
  max-height: none;
}
.skills-manager-close {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 28px;
  padding: 0 12px;
  border: none;
  border-radius: 8px;
  background: var(--dsw-alias-bg-layer-2);
  color: var(--dsw-alias-label-secondary);
  font: var(--dsw-font-xxs-12);
  cursor: pointer;
}
.skills-manager-close:hover {
  background: var(--dsw-alias-interactive-bg-hover);
}
`

interface Slots {
  register(decl: object, component: (inject: Record<string, unknown>) => React.ReactElement): unknown
}
