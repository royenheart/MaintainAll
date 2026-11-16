/**
 * Client (browser) half of `@royenheart/dsh-plugin-maintainall`.
 *
 * Three surfaces, all plain fetch against the host routes (no custom RPC):
 *
 *   - `conversation.session.header.utilities`, order -1: a "Save ops" capsule
 *     styled like the Session log capsule; clicking opens a modal that
 *     collects task metadata and trigger parameters and posts them to
 *     `POST /save` (the host records the save request; the model generates
 *     the assets afterwards);
 *   - `sidebar.panellist` + `main`: one "Ops tasks" main panel that lists
 *     tasks from `GET /tasks` with task, trigger, and run actions;
 *   - `settings.section`: the plugin log viewer.
 *
 * All visible strings come from the single `maintainall` locale namespace;
 * `src/locales/keys.ts` is the key authority and `src/locales/index.ts`
 * registers the complete dictionaries.
 */

import * as React from 'react'
import type { Context } from '@deepseek-ai/cordis'
// Client-side service augmentations live in each package's `./client` types.
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-slots'

import { dictionaries, NAMESPACE } from './locales/index.ts'
import type { MaintainAllKey } from './locales/keys.ts'
import { OpsPanel, OpsPanelIcon } from './client/ops-panel.ts'
import { SaveOpsAction } from './client/save-dialog.ts'
import { OpsSettings } from './client/settings-log.ts'
import type { Slots, Translate } from './client/shared.ts'

// Merge the maintainall namespace into the locale key map so
// `ctx.locale.register('maintainall', ...)` type-checks.
declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    maintainall: MaintainAllKey
  }
}

/** Cordis plugin name. */
export const name = 'maintainall-client'

/** Cordis guard: direct `ctx.<name>` access requires declaring inject. */
export const inject = ['slots', 'locale', 'connection', 'uiWorkspace']

function installStyles(): void {
  if (typeof document === 'undefined') return
  if (document.getElementById('maintainall-styles') !== null) return
  const style = document.createElement('style')
  style.id = 'maintainall-styles'
  style.textContent = css
  document.head.appendChild(style)
}

const css = `
.maintainall-capsule {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 32px;
  padding: 6px 12px;
  gap: 4px;
  border: 1px solid var(--dsw-alias-border-l2);
  border-radius: 18px;
  color: var(--dsw-alias-label-primary);
  background: transparent;
  font-family: var(--dsw-font-family);
  font-size: 13px;
  font-weight: 400;
  line-height: 20px;
  cursor: pointer;
}
.maintainall-capsule:hover:not(:disabled) {
  background: var(--dsw-alias-interactive-bg-hover);
}
.maintainall-capsule:disabled {
  color: var(--dsw-alias-label-dimmed);
  cursor: wait;
}
.maintainall-capsule span,
.maintainall-capsule svg {
  flex: none;
}
.maintainall-capsule span {
  white-space: nowrap;
}
.maintainall-overlay {
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
.maintainall-modal {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: min(520px, 92vw);
  max-height: 84vh;
  overflow-y: auto;
  padding: 16px;
  border: 1px solid var(--dsw-alias-border-inverted);
  border-radius: 24px;
  background: var(--dsw-alias-bg-layer-2);
  box-shadow: var(--dsw-shadow-lv3);
  color: var(--dsw-alias-label-primary);
  font: var(--dsw-font-xxs-12);
}
.maintainall-modal__title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
}
.maintainall-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.maintainall-field--check {
  flex-direction: row;
  align-items: center;
  gap: 6px;
}
.maintainall-mode {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border: 1px solid var(--dsw-alias-border-l2);
  border-radius: 8px;
  background: var(--dsw-alias-bg-layer-2);
}
.maintainall-mode__text {
  flex: 1;
  min-width: 0;
}
.maintainall-mode__name {
  font-weight: 600;
  color: var(--dsw-alias-label-primary);
}
.maintainall-mode__desc {
  color: var(--dsw-alias-label-tertiary);
}
.maintainall-picker {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.maintainall-picker__item {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 28px;
  padding: 0 6px;
  border: 1px solid var(--dsw-alias-border-l2);
  border-radius: 6px;
  background: transparent;
  color: var(--dsw-alias-label-primary);
  cursor: pointer;
}
.maintainall-picker__item--selected {
  border-color: var(--dsw-alias-state-business-primary);
  box-shadow: 0 0 0 1px var(--dsw-alias-state-business-primary);
}
.maintainall-picker__item--color {
  padding: 0;
  width: 28px;
}
.maintainall-field__label {
  color: var(--dsw-alias-label-tertiary);
}
.maintainall-input {
  height: 26px;
  padding: 0 8px;
  border: 1px solid var(--dsw-alias-border-l2);
  border-radius: 6px;
  color: var(--dsw-alias-label-primary);
  background: var(--dsw-alias-bg-layer-2);
  font: var(--dsw-font-xxs-12);
}
.maintainall-textarea {
  height: auto;
  min-height: 56px;
  padding: 6px 8px;
  resize: vertical;
  font-family: var(--dsw-font-family-code, monospace);
}
.maintainall-error {
  color: var(--dsw-alias-label-danger, #e5484d);
  font: var(--dsw-font-xxs-12);
}
.maintainall-modal__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}
.maintainall-btn {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 12px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--dsw-alias-label-secondary);
  font: var(--dsw-font-xxs-12);
  cursor: pointer;
}
.maintainall-btn:hover {
  background: var(--dsw-alias-interactive-bg-hover);
  color: var(--dsw-alias-label-primary);
}
.maintainall-btn--primary {
  color: var(--dsw-alias-state-business-primary);
}
.maintainall-btn--icon {
  width: 24px;
  height: 24px;
  padding: 0;
  justify-content: center;
}
.maintainall-menu-wrap {
  position: relative;
  flex: none;
}
.maintainall-menu {
  position: absolute;
  top: 26px;
  right: 0;
  z-index: 20;
  min-width: 120px;
  padding: 4px;
  border: 1px solid var(--dsw-alias-border-l2);
  border-radius: 8px;
  background: var(--dsw-alias-bg-layer-2);
  box-shadow: var(--dsw-shadow-lv2);
}
.maintainall-menu__item {
  display: flex;
  width: 100%;
  padding: 6px 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--dsw-alias-label-primary);
  font: var(--dsw-font-xxs-12);
  text-align: left;
  cursor: pointer;
}
.maintainall-menu__item:hover {
  background: var(--dsw-alias-interactive-bg-hover);
}
.maintainall-menu__item--danger {
  color: var(--dsw-alias-state-danger);
}
.maintainall-panel {
  box-sizing: border-box;
  width: 100%;
  max-width: 960px;
  min-height: 100%;
  margin: 0 auto;
  padding: 28px 24px 40px;
  display: flex;
  flex-direction: column;
  color: var(--dsw-alias-label-primary);
  font-family: var(--dsw-font-family);
  font-size: 13px;
}
.maintainall-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--dsw-alias-border-l2);
}
.maintainall-panel__title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  line-height: 28px;
}
.maintainall-panel__error {
  margin: 8px 0 0;
  color: var(--dsw-alias-state-danger);
}
.maintainall-panel .maintainall-task-list {
  flex: none;
  min-height: 0;
  overflow: visible;
}
.maintainall-empty {
  padding: 16px 4px;
  color: var(--dsw-alias-label-tertiary);
}
.maintainall-task-list {
  flex: 1;
  min-height: 0;
  margin: 0;
  padding: 8px 0;
  overflow-y: auto;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.maintainall-task-row {
  display: flex;
  align-items: center;
  height: 34px;
  box-sizing: border-box;
  gap: 6px;
  padding: 0 8px;
  border-radius: 8px;
  color: var(--dsw-alias-label-primary);
  cursor: pointer;
  user-select: none;
}
.maintainall-task-row:hover {
  background: var(--dsw-alias-interactive-bg-hover);
}
.maintainall-task-row__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 16px;
  height: 16px;
}
.maintainall-task-row__emoji {
  font-size: 13px;
  line-height: 16px;
}
.maintainall-task-row__chevron {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 16px;
  height: 20px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--dsw-alias-label-tertiary);
  cursor: pointer;
}
.maintainall-task-row__chevron svg {
  transition: transform 120ms var(--ds-ease-in-out);
}
.maintainall-task-row__chevron--open {
  transform: rotate(90deg);
}
.maintainall-task-row__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  line-height: 20px;
}
.maintainall-task-row__status {
  flex: none;
  font-size: 11px;
  color: var(--dsw-alias-label-dimmed);
}
.maintainall-task-row__status--enabled {
  color: var(--dsw-alias-state-business-primary);
}
.maintainall-task-detail {
  margin: 0 0 4px 22px;
  padding: 8px;
  border-left: 2px solid var(--dsw-alias-border-l2);
  color: var(--dsw-alias-label-primary);
  font-family: var(--dsw-font-family);
  font-size: 13px;
  line-height: 20px;
}
.maintainall-task-detail__description {
  margin: 0 0 6px;
  color: var(--dsw-alias-label-primary);
}
.maintainall-task-detail__section {
  margin-top: 6px;
}
.maintainall-task-detail__section h4 {
  margin: 0 0 2px;
  font-size: 13px;
  line-height: 20px;
  font-weight: 600;
  color: var(--dsw-alias-label-primary);
}
.maintainall-task-detail__triggers {
  margin: 0;
  padding-left: 20px;
}
.maintainall-run-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.maintainall-run-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 4px 6px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--dsw-alias-label-primary);
  font-size: 12px;
  line-height: 20px;
  text-align: left;
  cursor: pointer;
}
.maintainall-run-row:hover {
  background: var(--dsw-alias-interactive-bg-hover);
}
.maintainall-run-row__time {
  flex: none;
  color: var(--dsw-alias-label-tertiary);
}
.maintainall-run-row__id {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.maintainall-task-detail__instructions {
  margin: 0;
  padding: 6px;
  overflow-x: auto;
  border: 1px solid var(--dsw-alias-border-l2);
  border-radius: 6px;
  background: var(--dsw-alias-bg-layer-2);
  font-family: var(--dsw-font-family-code, monospace);
  font-size: 13px;
  line-height: 20px;
  white-space: pre-wrap;
}
.maintainall-settings {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 0;
}
.maintainall-log-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
  padding: 8px;
  list-style: none;
  overflow-y: auto;
  max-height: 60vh;
  border: 1px solid var(--dsw-alias-border-l2);
  border-radius: 8px;
  background: var(--dsw-alias-bg-layer-2);
}
.maintainall-log-list li {
  display: flex;
  gap: 6px;
  align-items: baseline;
}
.maintainall-log-row__ts {
  flex: none;
  color: var(--dsw-alias-label-tertiary);
  font-family: var(--dsw-font-family-code, monospace);
  font-size: 12px;
  line-height: 20px;
}
.maintainall-log-row__level {
  flex: none;
  padding: 0 6px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 20px;
}
.maintainall-log-row__level--info {
  color: var(--dsw-alias-state-business-primary);
}
.maintainall-log-row__level--warn {
  color: var(--dsw-alias-state-warning);
}
.maintainall-log-row__level--error {
  color: var(--dsw-alias-state-danger);
}
.maintainall-log-row__msg {
  min-width: 0;
  color: var(--dsw-alias-label-primary);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
`

/**
 * Register the locale namespace and both slots.
 * @param ctx - browser root context carrying slots, locale, and connection.
 */
interface ClientWorkspaceFace {
  openSession(id: string): void
}

export function apply(ctx: Context): void {
  ctx.effect(() => {
    const disposeLocale = ctx.locale.register(NAMESPACE, dictionaries)
    installStyles()
    return () => {
      disposeLocale()
      document.getElementById('maintainall-styles')?.remove()
    }
  }, 'maintainall-client: locale and styles')
  const t = ctx.locale.bind(NAMESPACE) as unknown as Translate
  const slots = (ctx as unknown as { slots: Slots }).slots
  const workspace = (ctx as unknown as { uiWorkspace?: ClientWorkspaceFace }).uiWorkspace

  ctx.effect(() => {
    const disposeSave = slots.inject('conversation.session.header.utilities', () =>
      slots.register(
        { name: 'conversation.session.header.utilities', id: 'maintainall-save', order: -1 },
        (injected: Record<string, unknown>) =>
          React.createElement(SaveOpsAction, {
            t,
            sessionId: typeof injected.sessionId === 'string' ? injected.sessionId : undefined,
          }),
      ),
    ) as () => void
    const disposeMain = slots.inject('main', () =>
      slots.register(
        { name: 'main', key: 'maintainall', locale: NAMESPACE },
        () => React.createElement(OpsPanel, {
          t,
          onOpen: (sessionId: string) => { workspace?.openSession(sessionId) },
        }),
      ),
    ) as () => void
    const disposePanel = slots.inject('sidebar.panellist', () =>
      slots.register(
        {
          name: 'sidebar.panellist',
          id: 'maintainall',
          order: 20,
          locale: NAMESPACE,
          label: () => t('ops.title'),
        },
        (injected: Record<string, unknown>) => React.createElement(OpsPanelIcon, {
          size: typeof injected.size === 'number' ? injected.size : 16,
        }),
      ),
    ) as () => void
    const disposeSettings = slots.inject('settings.section', () =>
      slots.register(
        { name: 'settings.section', id: 'maintainall', order: 900, label: () => t('settings.title') },
        () => React.createElement(OpsSettings, { t }),
      ),
    ) as () => void
    return () => {
      disposeSave()
      disposeMain()
      disposePanel()
      disposeSettings()
    }
  }, 'maintainall-client: slots')
}
