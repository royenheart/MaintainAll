/** Ops task panel: task list, run history, and task actions. */

import * as React from 'react'
import type { ReactElement } from 'react'
import {
  IconChevronRightOutlineRegular,
  IconEllipsisOutlineRegular,
  IconFolderCloseRegular,
} from '@deepseek-ai/dsh-client-ui-primitives'

import { ROUTE_BASE, postJson } from './api.ts'
import { SaveOpsAction } from './save-dialog.ts'
import type { EditInitial, TaskRecord, Translate } from './shared.ts'

export function OpsPanel(props: { t: Translate; onOpen?: (sessionId: string) => void }): ReactElement {
  const { t, onOpen } = props
  const [tasks, setTasks] = React.useState<TaskRecord[]>([])
  const [expandedId, setExpandedId] = React.useState<string | null>(null)
  const [runs, setRuns] = React.useState<Array<{ runId: string; sessionId: string; createdAt: string }>>([])
  const [runOffset, setRunOffset] = React.useState(0)
  const [hasMoreRuns, setHasMoreRuns] = React.useState(false)
  const [menuTaskId, setMenuTaskId] = React.useState<string | null>(null)
  const [editingTask, setEditingTask] = React.useState<EditInitial | null>(null)
  const [pending, setPending] = React.useState<string | null>(null)
  const [error, setError] = React.useState('')
  const [runsError, setRunsError] = React.useState(false)
  const [loaded, setLoaded] = React.useState(false)
  const [loadFailed, setLoadFailed] = React.useState(false)
  const expandedRef = React.useRef<string | null>(null)
  const runsRequest = React.useRef(0)

  const reload = React.useCallback(() => {
    void fetch(`${ROUTE_BASE}/tasks`)
      .then(async (response) => {
        const body = (await response.json()) as { ok?: unknown; tasks?: unknown }
        if (body.ok === true && Array.isArray(body.tasks)) {
          setTasks(body.tasks as TaskRecord[])
          setError('')
          setLoadFailed(false)
          setLoaded(true)
        } else {
          setError(t('ops.error'))
          setLoadFailed(true)
          setLoaded(true)
        }
      })
      .catch(() => {
        setError(t('ops.error'))
        setLoadFailed(true)
        setLoaded(true)
      })
  }, [])

  React.useEffect(() => {
    reload()
  }, [reload])

  const stop = (fn: () => void) => (event: { stopPropagation: () => void }) => {
    event.stopPropagation()
    fn()
  }

  const fetchRuns = React.useCallback((task: TaskRecord, offset: number) => {
    const request = ++runsRequest.current
    void fetch(`${ROUTE_BASE}/tasks/${encodeURIComponent(task.id)}/runs?limit=10&offset=${offset}`)
      .then(async (response) => {
        const body = (await response.json()) as { ok?: unknown; runs?: unknown; hasMore?: unknown }
        if (request !== runsRequest.current || expandedRef.current !== task.id) return
        if (body.ok === true && Array.isArray(body.runs)) {
          const next = body.runs as Array<{ runId: string; sessionId: string; createdAt: string }>
          setRuns((previous) => (offset === 0 ? next : [...previous, ...next]))
          setRunOffset(offset + next.length)
          setHasMoreRuns(body.hasMore === true)
          setRunsError(false)
        } else {
          setRunsError(true)
        }
      })
      .catch(() => {
        if (request === runsRequest.current) setRunsError(true)
      })
  }, [t])

  const expand = (task: TaskRecord) => {
    runsRequest.current += 1
    setRunsError(false)
    if (expandedId === task.id) {
      expandedRef.current = null
      setExpandedId(null)
      setRuns([])
      setHasMoreRuns(false)
      setRunOffset(0)
      return
    }
    expandedRef.current = task.id
    setExpandedId(task.id)
    setRuns([])
    setHasMoreRuns(false)
    setRunOffset(0)
    fetchRuns(task, 0)
  }

  const action = (task: TaskRecord, key: string, call: () => Promise<boolean>, after?: () => void) => {
    setPending(key)
    setError('')
    void call()
      .then((ok) => {
        if (!ok) setError(t('ops.error'))
        else {
          reload()
          after?.()
        }
      })
      .catch(() => setError(t('ops.error')))
      .finally(() => setPending(null))
  }

  const toggle = (task: TaskRecord) => {
    const next = task.enabled ? 'disable' : 'enable'
    action(task, `toggle:${task.id}`, () => postJson(`${ROUTE_BASE}/triggers/${encodeURIComponent(task.id)}/${next}`, {}))
  }

  const runOnce = (task: TaskRecord) => {
    action(task, `run:${task.id}`, () => postJson(`${ROUTE_BASE}/tasks/${encodeURIComponent(task.id)}/run`, {}), () => {
      if (expandedRef.current === task.id) fetchRuns(task, 0)
    })
  }

  const editTask = (task: TaskRecord) => {
    setError('')
    void fetch(`${ROUTE_BASE}/tasks/${encodeURIComponent(task.id)}`)
      .then(async (response) => {
        const body = (await response.json()) as { ok?: unknown; task?: unknown }
        if (!response.ok || body.ok !== true || body.task === undefined || typeof body.task !== 'object') {
          setError(t('ops.error'))
          return
        }
        setEditingTask(body.task as EditInitial)
      })
      .catch(() => setError(t('ops.error')))
  }

  const deleteTask = (task: TaskRecord) => {
    if (!window.confirm(t('ops.deleteConfirm'))) return
    action(task, `delete:${task.id}`, () => postJson(`${ROUTE_BASE}/tasks/${encodeURIComponent(task.id)}/delete`, {}))
  }

  const renderIcon = (task: TaskRecord) =>
    task.icon !== undefined && task.icon !== ''
      ? React.createElement('span', { className: 'maintainall-task-row__emoji' }, task.icon)
      : React.createElement(IconFolderCloseRegular, { size: 16 })

  return React.createElement(
    React.Fragment,
    null,
    React.createElement(
      'section',
      { className: 'maintainall-panel', 'aria-label': t('ops.title'), 'aria-busy': pending === null ? undefined : true },
      React.createElement(
        'header',
        { className: 'maintainall-panel__header' },
        React.createElement('h1', { className: 'maintainall-panel__title' }, t('ops.title')),
      ),
      error === ''
        ? null
        : React.createElement('p', { className: 'maintainall-panel__error', role: 'alert' }, error),
          !loaded
            ? React.createElement('p', { className: 'maintainall-empty' }, t('ops.loading'))
            : loadFailed && tasks.length === 0
            ? null
            : tasks.length === 0
            ? React.createElement('p', { className: 'maintainall-empty' }, t('ops.empty'))
            : React.createElement(
                'ul',
                { className: 'maintainall-task-list' },
                tasks.map((task) =>
                  React.createElement(
                    'li',
                    { key: task.id },
                    React.createElement(
                      'div',
                      { className: 'maintainall-task-row' },
                      React.createElement(
                        'button',
                        {
                          type: 'button',
                          className: 'maintainall-task-row__chevron',
                          'aria-label': t('ops.menu'),
                          onClick: stop(() => expand(task)),
                        },
                        React.createElement(
                          IconChevronRightOutlineRegular,
                          { size: 14, className: expandedId === task.id ? 'maintainall-task-row__chevron--open' : undefined },
                        ),
                      ),
                      React.createElement(
                        'span',
                        { className: 'maintainall-task-row__icon' },
                        renderIcon(task),
                      ),
                      React.createElement(
                        'span',
                        {
                          className: 'maintainall-task-row__name',
                          title: task.id,
                          ...(task.color === undefined || task.color === ''
                            ? {}
                            : { style: { color: task.color } }),
                        },
                        task.name,
                      ),
                      React.createElement(
                        'span',
                        {
                          className:
                            'maintainall-task-row__status' +
                            (task.enabled ? ' maintainall-task-row__status--enabled' : ''),
                        },
                        t(task.enabled ? 'ops.enabled' : 'ops.disabled'),
                      ),
                      React.createElement(
                        'div',
                        { className: 'maintainall-menu-wrap' },
                        React.createElement(
                          'button',
                          {
                            type: 'button',
                            className: 'maintainall-btn maintainall-btn--icon',
                            'aria-label': t('ops.menu'),
                            onClick: stop(() => setMenuTaskId(menuTaskId === task.id ? null : task.id)),
                          },
                          React.createElement(IconEllipsisOutlineRegular, { size: 14 }),
                        ),
                        menuTaskId === task.id
                          ? React.createElement(
                              'div',
                              { className: 'maintainall-menu' },
                              React.createElement(
                                'button',
                                {
                                  type: 'button',
                                  className: 'maintainall-menu__item',
                                  disabled: pending !== null,
                                  onClick: stop(() => { setMenuTaskId(null); runOnce(task) }),
                                },
                                t('ops.runOnce'),
                              ),
                              React.createElement(
                                'button',
                                {
                                  type: 'button',
                                  className: 'maintainall-menu__item',
                                  disabled: pending !== null,
                                  onClick: stop(() => { setMenuTaskId(null); editTask(task) }),
                                },
                                t('ops.edit'),
                              ),
                              React.createElement(
                                'button',
                                {
                                  type: 'button',
                                  className: 'maintainall-menu__item',
                                  disabled: pending !== null,
                                  onClick: stop(() => { setMenuTaskId(null); toggle(task) }),
                                },
                                t(task.enabled ? 'ops.disable' : 'ops.enable'),
                              ),
                              React.createElement(
                                'button',
                                {
                                  type: 'button',
                                  className: 'maintainall-menu__item maintainall-menu__item--danger',
                                  disabled: pending !== null,
                                  onClick: stop(() => { setMenuTaskId(null); deleteTask(task) }),
                                },
                                t('ops.delete'),
                              ),
                            )
                          : null,
                      ),
                    ),
                    expandedId === task.id
                      ? React.createElement(
                          'div',
                          { className: 'maintainall-task-detail' },
                          runsError
                            ? React.createElement('p', { className: 'maintainall-panel__error', role: 'alert' }, t('ops.error'))
                            : null,
                          runs.length === 0
                            ? runsError
                              ? null
                              : React.createElement('p', { className: 'maintainall-empty' }, t('ops.noRuns'))
                            : React.createElement(
                                'ul',
                                { className: 'maintainall-run-list' },
                                runs.map((run) =>
                                  React.createElement(
                                    'li',
                                    { key: run.runId },
                                    React.createElement(
                                      'button',
                                      {
                                        type: 'button',
                                        className: 'maintainall-run-row',
                                        onClick: stop(() => onOpen?.(run.sessionId)),
                                      },
                                      React.createElement('span', { className: 'maintainall-run-row__time' }, run.createdAt),
                                      React.createElement('span', { className: 'maintainall-run-row__id' }, run.sessionId),
                                    ),
                                  ),
                                ),
                              ),
                          hasMoreRuns
                            ? React.createElement(
                                'button',
                                { type: 'button', className: 'maintainall-btn', onClick: stop(() => fetchRuns(task, runOffset)) },
                                t('ops.earlier'),
                              )
                            : null,
                        )
                      : null,
                  ),
                ),
              ),
    ),
    editingTask !== null
      ? React.createElement(SaveOpsAction, {
          t,
          initial: editingTask,
          onSession: (id: string) => onOpen?.(id),
          onClose: () => {
            setEditingTask(null)
            reload()
          },
        })
      : null,
  )
}

/** Decorative folder glyph for the Ops sidebar panel entry. */
export function OpsPanelIcon({ size }: { size: number }): ReactElement {
  return React.createElement(IconFolderCloseRegular, { size })
}

/** Inject one scoped stylesheet (idempotent) matching dsh's design tokens. */
