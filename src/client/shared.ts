/** Shared task/save-dialog types and selectors for both client surfaces. */

import type { ReactElement } from 'react'
import type { MaintainAllKey } from '../locales/keys.ts'
import { TRIGGER_SOURCES, readTriggerFields, type TriggerSource } from './trigger-fields.ts'

export type Translate = (key: MaintainAllKey, params?: Record<string, string>) => string

export type TaskMode = 'safe-copy' | 'compact' | 'fresh' | 'auto'
export const ICON_OPTIONS = ['📁', '🌐', '⚡', '🖥️', '🔧', '📡'] as const
export const COLOR_OPTIONS = ['#4f8cff', '#34c77b', '#f5a623', '#e5484d', '#9b8cff'] as const

export const TASK_MODES: Array<{ id: TaskMode; nameKey: MaintainAllKey; descKey: MaintainAllKey }> = [
  { id: 'safe-copy', nameKey: 'save.mode.safeCopy.name', descKey: 'save.mode.safeCopy.desc' },
  { id: 'compact', nameKey: 'save.mode.compact.name', descKey: 'save.mode.compact.desc' },
  { id: 'fresh', nameKey: 'save.mode.fresh.name', descKey: 'save.mode.fresh.desc' },
  { id: 'auto', nameKey: 'save.mode.auto.name', descKey: 'save.mode.auto.desc' },
]

/** Auto is a request mode for the model path, never a manual materialize mode. */
export const MANUAL_TASK_MODES = TASK_MODES.filter((mode) => mode.id !== 'auto')

export const SOURCE_LABELS: Record<TriggerSource, MaintainAllKey> = {
  schedule: 'save.source.schedule',
  filewatch: 'save.source.filewatch',
  docker: 'save.source.docker',
  journald: 'save.source.journald',
  webhook: 'save.source.webhook',
  exec: 'save.source.exec',
}

/** Wire shape of one task registry record returned by `GET /tasks`. */
export interface TaskRecord {
  id: string
  name: string
  version: string
  enabled: boolean
  icon?: string
  color?: string
}

/** Minimal slots-registry face this client consumes. */
export interface Slots {
  register(decl: object, component: (inject: Record<string, unknown>) => ReactElement): unknown
  inject(slot: string, effect: () => unknown): unknown
}

/**
 * "Save ops" capsule for the session header utilities row, plus the modal
 * save dialog it opens.
 */
export interface EditInitial {
  id: string
  name: string
  description: string
  instructions: string
  taskMode: TaskMode
  icon: string
  color: string
  naturalPrompt: string
  triggers: Array<{
    id: string
    source: string
    enabled: boolean
    when?: string
    params?: Record<string, unknown>
    filter?: Record<string, unknown>
    rate?: { minIntervalSeconds: number; maxPerHour: number }
  }>
}

export function initialModeIndex(taskMode: TaskMode): number {
  const index = TASK_MODES.findIndex((mode) => mode.id === taskMode)
  return index < 0 ? 0 : index
}

export function initialTrigger(initial: EditInitial): {
  id?: string
  enabled?: boolean
  source: TriggerSource
  path: string
  regex: string
  token?: string
  when: string
  debounceMinutes: number
  maxPerHour: number
} {
  const trigger = initial.triggers[0]
  const rawSource = trigger?.source ?? 'schedule'
  const source = (TRIGGER_SOURCES as readonly string[]).includes(rawSource)
    ? rawSource as TriggerSource
    : 'schedule'
  const rate = trigger?.rate
  const fields = readTriggerFields(trigger, source)
  return {
    id: trigger?.id,
    enabled: trigger?.enabled,
    source,
    path: fields.path,
    regex: fields.regex,
    ...(fields.token === undefined ? {} : { token: fields.token }),
    when: trigger?.when ?? '',
    debounceMinutes: (rate?.minIntervalSeconds ?? 0) / 60,
    maxPerHour: rate?.maxPerHour ?? 0,
  }
}
