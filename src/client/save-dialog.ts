/**
 * "Save ops" header capsule and its create/edit dialog.
 */

import * as React from 'react'
import type { ReactElement } from 'react'
import type { MaintainAllKey } from '../locales/keys.ts'
import {
  IconChevronLeftOutlineRegular,
  IconChevronRightOutlineRegular,
  IconPlusOutlineRegular,
} from '@deepseek-ai/dsh-client-ui-primitives'

import {
  SCHEDULE_KINDS,
  TIME_ZONE_OPTIONS,
  defaultScheduleForm,
  scheduleFormOf,
  scheduleParamsOf,
  type ScheduleForm,
  type ScheduleKind,
} from './schedule-form.ts'
import { ROUTE_BASE, postJsonEdit, postJsonError } from './api.ts'
import {
  TRIGGER_SOURCES,
  buildTriggerFilter,
  readTriggerFields,
  sourceFieldOf,
  type TriggerSource,
} from './trigger-fields.ts'
import {
  COLOR_OPTIONS,
  ICON_OPTIONS,
  MANUAL_TASK_MODES,
  SOURCE_LABELS,
  TASK_MODES,
  initialModeIndex,
  initialTrigger,
  type EditInitial,
  type Translate,
} from './shared.ts'

function newWebhookToken(): string {
  try {
    return crypto.randomUUID().replaceAll('-', '')
  } catch {
    return Math.random().toString(36).slice(2) + Date.now().toString(36)
  }
}

export function SaveOpsAction(props: {
  t: Translate
  sessionId?: string
  initial?: EditInitial | null
  onClose?: () => void
  onSession?: (sessionId: string) => void
}): ReactElement {
  const { t, sessionId, initial, onClose, onSession } = props
  const [open, setOpen] = React.useState(initial !== undefined && initial !== null)
  const [auto, setAuto] = React.useState(initial === undefined || initial === null || initial.naturalPrompt !== '')
  const [naturalDescription, setNaturalDescription] = React.useState(initial?.naturalPrompt ?? '')
  const [taskId, setTaskId] = React.useState(initial?.id ?? '')
  const [taskName, setTaskName] = React.useState(initial?.name ?? '')
  const [description, setDescription] = React.useState(initial?.description ?? '')
  const [source, setSource] = React.useState<TriggerSource>(
    initial === undefined || initial === null ? 'schedule' : initialTrigger(initial).source,
  )
  const [schedule, setSchedule] = React.useState<ScheduleForm>(
    () => initial === undefined || initial === null
      ? defaultScheduleForm()
      : scheduleFormOf(initial.triggers[0]),
  )
  const [path, setPath] = React.useState(initial === undefined || initial === null ? '' : initialTrigger(initial).path)
  const [regex, setRegex] = React.useState(initial === undefined || initial === null ? '' : initialTrigger(initial).regex)
  const [token, setToken] = React.useState(initial === undefined || initial === null
    ? newWebhookToken()
    : (initialTrigger(initial).token ?? newWebhookToken()))
  const [when, setWhen] = React.useState(initial === undefined || initial === null ? '' : initialTrigger(initial).when)
  const [debounceMinutes, setDebounceMinutes] = React.useState(
    initial === undefined || initial === null ? 0 : initialTrigger(initial).debounceMinutes,
  )
  const [maxPerHour, setMaxPerHour] = React.useState(
    initial === undefined || initial === null ? 0 : initialTrigger(initial).maxPerHour,
  )
  const [modeIndex, setModeIndex] = React.useState(initial === undefined || initial === null ? 0 : initialModeIndex(initial.taskMode))
  const [icon, setIcon] = React.useState<string>(
    initial === undefined || initial === null ? '📁' : (initial.icon ?? ''),
  )
  const [color, setColor] = React.useState<string>(initial?.color || '')
  const [error, setError] = React.useState('')
  const submittingRef = React.useRef(false)
  const [submitting, setSubmitting] = React.useState(false)

  const field = sourceFieldOf(source)
  const patchSchedule = (patch: Partial<ScheduleForm>) =>
    setSchedule((previous) => ({ ...previous, ...patch, dirty: true }))
  const originalSource = initial === undefined || initial === null ? undefined : initialTrigger(initial).source
  const originalFields = initial === undefined || initial === null || originalSource === undefined
    ? undefined
    : readTriggerFields(initial.triggers[0], originalSource)
  const availableModes = initial === undefined || initial === null
    ? (auto ? TASK_MODES : MANUAL_TASK_MODES)
    : TASK_MODES
  const mode = availableModes[modeIndex] ?? availableModes[0]
  const shiftMode = (delta: number) => {
    setModeIndex((previous) => (previous + delta + availableModes.length) % availableModes.length)
  }

  const close = () => {
    setOpen(false)
    setError('')
    if (onClose !== undefined) onClose()
  }

  const requestClose = () => {
    if (!submittingRef.current) close()
  }

  const submit = async () => {
    if (submittingRef.current) return
    submittingRef.current = true
    setSubmitting(true)
    try {
    setError('')
    const initialSource = initial !== undefined && initial !== null ? initialTrigger(initial).source : undefined
    const firstTrigger = initial?.triggers[0]
    const previousFilter = firstTrigger?.filter
    const baseFilter = initial !== undefined && initial !== null && source === initialSource && previousFilter !== undefined
      ? { ...previousFilter }
      : {}
    const trigger = {
      id: firstTrigger?.id ?? `${(initial?.id ?? taskId) || 'task'}-t1`,
      source,
      enabled: firstTrigger?.enabled ?? true,
      ...(when !== '' ? { when } : {}),
      ...(debounceMinutes > 0 || maxPerHour > 0
        ? { rate: { minIntervalSeconds: Math.round(debounceMinutes * 60), maxPerHour } }
        : {}),
      ...(source === 'schedule'
        ? { params: scheduleParamsOf(schedule) }
        : {
            filter: buildTriggerFilter(source, { path, regex, token }, baseFilter),
          }),
    }

    // Editing an existing task: the seed and `taskMode` were captured at
    // creation time and are not editable from this dialog. Manual edits go
    // straight to the task asset; natural-language edits open a fresh
    // session that re-sets metadata and runbook only.
    const triggers = initial !== undefined && initial !== null
      ? [trigger, ...initial.triggers.slice(1)]
      : [trigger]
    if (initial !== undefined && initial !== null) {
      if (auto) {
        const result = await postJsonEdit(`${ROUTE_BASE}/tasks/${encodeURIComponent(initial.id)}/edit`, {
          description: naturalDescription,
          icon,
          color,
          naturalPrompt: naturalDescription,
        }, t('save.error'))
        if (result.error !== null) {
          setError(result.error)
          return
        }
        if (result.sessionId !== undefined) onSession?.(result.sessionId)
        close()
        return
      }
      const failure = await postJsonError(`${ROUTE_BASE}/tasks/${encodeURIComponent(initial.id)}/edit`, {
        materialize: true,
        meta: {
          name: taskName,
          description,
          triggers,
          icon,
          color,
          naturalPrompt: initial.naturalPrompt ?? '',
        },
      }, t('save.error'))
      if (failure !== null) {
        setError(failure)
        return
      }
      close()
      return
    }

    const failure = auto
      ? await postJsonError(`${ROUTE_BASE}/save`, {
          sessionId: sessionId ?? '',
          boundarySeq: 0,
          meta: {
            auto: true,
            description: naturalDescription,
            taskMode: mode?.id ?? 'safe-copy',
            icon,
            color,
            naturalPrompt: naturalDescription,
          },
        }, t('save.error'))
      : await postJsonError(`${ROUTE_BASE}/save`, {
          sessionId: sessionId ?? '',
          // 0 = "up to the latest event"; the host cuts the seed boundary there.
          boundarySeq: 0,
          meta: {
            id: taskId,
            name: taskName,
            description,
            materialize: true,
            taskMode: mode?.id ?? 'safe-copy',
            icon,
            color,
            naturalPrompt: naturalDescription,
            triggers: [trigger],
          },
        }, t('save.error'))
    if (failure !== null) {
      setError(failure)
      return
    }
    close()
    } finally {
      submittingRef.current = false
      setSubmitting(false)
    }
  }

  const input = (
    key: string,
    value: string,
    onChange: (next: string) => void,
  ): ReactElement =>
    React.createElement('input', {
      key,
      className: 'maintainall-input',
      value,
      onChange: (event: { target: { value: string } }) => onChange(event.target.value),
    })

  const row = (labelKey: MaintainAllKey, control: ReactElement): ReactElement =>
    React.createElement(
      'label',
      { key: labelKey, className: 'maintainall-field' },
      React.createElement('span', { className: 'maintainall-field__label' }, t(labelKey)),
      control,
    )

  return React.createElement(
    React.Fragment,
    null,
    initial === undefined || initial === null
      ? React.createElement(
          'button',
          {
            type: 'button',
            className: 'maintainall-capsule',
            onClick: () => setOpen(true),
            'aria-haspopup': 'dialog',
            'aria-expanded': open,
          },
          React.createElement(IconPlusOutlineRegular, { size: 12 }),
          React.createElement('span', null, t('save.button')),
        )
      : null,
    open
      ? React.createElement(
          'div',
          { className: 'maintainall-overlay', onClick: requestClose },
          React.createElement(
            'div',
            {
              className: 'maintainall-modal',
              role: 'dialog',
              'aria-label': t(initial === undefined || initial === null ? 'save.title' : 'save.editTitle'),
              onClick: (event: { stopPropagation: () => void }) => event.stopPropagation(),
            },
            React.createElement('h2', { className: 'maintainall-modal__title' }, t(initial === undefined || initial === null ? 'save.title' : 'save.editTitle')),
            React.createElement(
              'label',
              { className: 'maintainall-field maintainall-field--check' },
              React.createElement('input', {
                type: 'checkbox',
                checked: auto,
                onChange: (event: { target: { checked: boolean } }) => {
                  const checked = event.target.checked
                  setAuto(checked)
                  if (!checked && mode.id === 'auto') setModeIndex(0)
                },
              }),
              React.createElement('span', null, t(initial === undefined || initial === null ? 'save.auto' : 'save.autoEdit')),
            ),
            initial === undefined || initial === null
              ? React.createElement(
                  'div',
                  { className: 'maintainall-mode' },
                  React.createElement(
                    'button',
                    {
                      type: 'button',
                      className: 'maintainall-btn maintainall-btn--icon',
                      'aria-label': t('save.mode.prev'),
                      onClick: () => shiftMode(-1),
                    },
                    React.createElement(IconChevronLeftOutlineRegular, { size: 14 }),
                  ),
                  React.createElement(
                    'div',
                    { className: 'maintainall-mode__text' },
                    React.createElement('div', { className: 'maintainall-mode__name' }, t(mode.nameKey)),
                    React.createElement('div', { className: 'maintainall-mode__desc' }, t(mode.descKey)),
                  ),
                  React.createElement(
                    'button',
                    {
                      type: 'button',
                      className: 'maintainall-btn maintainall-btn--icon',
                      'aria-label': t('save.mode.next'),
                      onClick: () => shiftMode(1),
                    },
                    React.createElement(IconChevronRightOutlineRegular, { size: 14 }),
                  ),
                )
              : React.createElement(
                  'div',
                  { className: 'maintainall-mode maintainall-mode--fixed' },
                  React.createElement(
                    'div',
                    { className: 'maintainall-mode__text' },
                    React.createElement('div', { className: 'maintainall-mode__name' }, t(mode.nameKey)),
                    React.createElement('div', { className: 'maintainall-mode__desc' }, t(mode.descKey)),
                  ),
                ),
            row(
              'save.icon',
              React.createElement(
                'div',
                { className: 'maintainall-picker' },
                ICON_OPTIONS.map((option) =>
                  React.createElement(
                    'button',
                    {
                      key: option,
                      type: 'button',
                      className:
                        'maintainall-picker__item' +
                        (icon === option ? ' maintainall-picker__item--selected' : ''),
                      onClick: () => setIcon(option),
                    },
                    option,
                  ),
                ),
              ),
            ),
            row(
              'save.color',
              React.createElement(
                'div',
                { className: 'maintainall-picker' },
                COLOR_OPTIONS.map((option) =>
                  React.createElement(
                    'button',
                    {
                      key: option || 'default',
                      type: 'button',
                      className:
                        'maintainall-picker__item maintainall-picker__item--color' +
                        (color === option ? ' maintainall-picker__item--selected' : ''),
                      style: { background: option },
                      onClick: () => setColor(option),
                    },
                  ),
                ),
              ),
            ),
            auto
              ? row(
                  'save.naturalDescription',
                  React.createElement('textarea', {
                    className: 'maintainall-input maintainall-textarea',
                    value: naturalDescription,
                    onChange: (event: { target: { value: string } }) =>
                      setNaturalDescription(event.target.value),
                  }),
                )
              : React.createElement(
                  React.Fragment,
                  null,
                  row(
                    'save.taskId',
                    initial !== undefined && initial !== null
                      ? React.createElement('input', {
                          className: 'maintainall-input',
                          value: taskId,
                          readOnly: true,
                        })
                      : input('taskId', taskId, setTaskId),
                  ),
                  row('save.name', input('name', taskName, setTaskName)),
                  row('save.description', input('description', description, setDescription)),
                  row(
                    'save.triggerSource',
                    React.createElement(
                      'select',
                      {
                        className: 'maintainall-input',
                        value: source,
                        onChange: (event: { target: { value: string } }) => {
                          const next = event.target.value as TriggerSource
                          setSource(next)
                          if (next === originalSource) {
                            setPath(originalFields?.path ?? '')
                            setRegex(originalFields?.regex ?? '')
                          } else {
                            setPath('')
                            setRegex('')
                          }
                        },
                      },
                      TRIGGER_SOURCES.map((kind) =>
                        React.createElement('option', { key: kind, value: kind }, t(SOURCE_LABELS[kind])),
                      ),
                    ),
                  ),
                  source === 'schedule'
                    ? React.createElement(
                        React.Fragment,
                        null,
                        row(
                          'save.scheduleKind',
                          React.createElement(
                            'select',
                            {
                              className: 'maintainall-input',
                              value: schedule.kind,
                              onChange: (event: { target: { value: string } }) =>
                                patchSchedule({ kind: event.target.value as ScheduleKind }),
                            },
                            SCHEDULE_KINDS.map((kind) =>
                              React.createElement(
                                'option',
                                { key: kind.id, value: kind.id },
                                t(kind.labelKey),
                              ),
                            ),
                          ),
                        ),
                        schedule.kind === 'cron'
                          ? row('save.cron', input('cron', schedule.cron, (value) => patchSchedule({ cron: value })))
                          : null,
                        schedule.kind === 'cron' || schedule.kind === 'daily' || schedule.kind === 'weekly' || schedule.kind === 'at'
                          ? row(
                              'save.timeZone',
                              React.createElement('input', {
                                className: 'maintainall-input',
                                list: 'maintainall-time-zones',
                                value: schedule.timeZone,
                                onChange: (event: { target: { value: string } }) =>
                                  patchSchedule({ timeZone: event.target.value }),
                              }),
                            )
                          : null,
                        schedule.kind === 'daily' || schedule.kind === 'weekly'
                          ? row(
                              'save.time',
                              React.createElement('input', {
                                type: 'time',
                                step: 1,
                                className: 'maintainall-input',
                                value: schedule.time,
                                onChange: (event: { target: { value: string } }) =>
                                  patchSchedule({ time: event.target.value }),
                              }),
                            )
                          : null,
                        schedule.kind === 'weekly'
                          ? row('save.weekdays', input('weekdays', schedule.weekdays, (value) => patchSchedule({ weekdays: value })))
                          : null,
                        schedule.kind === 'every'
                          ? row(
                              'save.everySeconds',
                              React.createElement('input', {
                                type: 'number',
                                min: 60,
                                className: 'maintainall-input',
                                value: String(schedule.everySeconds),
                                onChange: (event: { target: { value: string } }) =>
                                  patchSchedule({ everySeconds: Math.max(0, Number(event.target.value) || 0) }),
                              }),
                            )
                          : null,
                        schedule.kind === 'after'
                          ? row(
                              'save.afterSeconds',
                              React.createElement('input', {
                                type: 'number',
                                min: 1,
                                className: 'maintainall-input',
                                value: String(schedule.afterSeconds),
                                onChange: (event: { target: { value: string } }) =>
                                  patchSchedule({ afterSeconds: Math.max(1, Number(event.target.value) || 1) }),
                              }),
                            )
                          : null,
                        schedule.kind === 'at'
                          ? row(
                              'save.at',
                              React.createElement('input', {
                                type: 'datetime-local',
                                step: 1,
                                className: 'maintainall-input',
                                value: schedule.atLocal,
                                onChange: (event: { target: { value: string } }) =>
                                  patchSchedule({ atLocal: event.target.value }),
                              }),
                            )
                          : null,
                        React.createElement(
                          'datalist',
                          { id: 'maintainall-time-zones' },
                          TIME_ZONE_OPTIONS.map((zone) =>
                            React.createElement('option', { key: zone, value: zone }),
                          ),
                        ),
                      )
                    : null,
                  source !== 'schedule' && field === 'path'
                    ? row(source === 'webhook' ? 'save.webhookPath' : 'save.path', input('path', path, setPath))
                    : null,
                  source === 'webhook'
                    ? row('save.webhookToken', input('token', token, setToken))
                    : null,
                  source !== 'schedule' && field === 'command'
                    ? row('save.command', input('command', path, setPath))
                    : null,
                  source !== 'schedule' && field === 'regex'
                    ? row(source === 'docker' ? 'save.container' : 'save.regex', input('regex', regex, setRegex))
                    : null,
                  row(
                    'save.when',
                    React.createElement('textarea', {
                      className: 'maintainall-input maintainall-textarea',
                      value: when,
                      onChange: (event: { target: { value: string } }) => setWhen(event.target.value),
                    }),
                  ),
                  row(
                    'save.debounceMinutes',
                    React.createElement('input', {
                      type: 'number',
                      min: 0,
                      className: 'maintainall-input',
                      value: String(debounceMinutes),
                      onChange: (event: { target: { value: string } }) =>
                        setDebounceMinutes(Math.max(0, Number(event.target.value) || 0)),
                    }),
                  ),
                  row(
                    'save.maxPerHour',
                    React.createElement('input', {
                      type: 'number',
                      min: 0,
                      className: 'maintainall-input',
                      value: String(maxPerHour),
                      onChange: (event: { target: { value: string } }) =>
                        setMaxPerHour(Math.max(0, Number(event.target.value) || 0)),
                    }),
                  ),
                ),
            error !== ''
              ? React.createElement('div', { className: 'maintainall-error', role: 'alert' }, error)
              : null,
            React.createElement(
              'div',
              { className: 'maintainall-modal__actions' },
              React.createElement(
                'button',
                { type: 'button', className: 'maintainall-btn', onClick: requestClose },
                t('save.cancel'),
              ),
              React.createElement(
                'button',
                {
                  type: 'button',
                  className: 'maintainall-btn maintainall-btn--primary',
                  disabled: submitting,
                  onClick: submit,
                },
                t('save.submit'),
              ),
            ),
          ),
        )
      : null,
  )
}
