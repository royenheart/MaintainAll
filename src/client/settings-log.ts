/** Settings-page log viewer for the plugin-owned JSONL log. */

import * as React from 'react'
import type { ReactElement } from 'react'

import { ROUTE_BASE } from './api.ts'
import type { Translate } from './shared.ts'

interface LogEntry {
  ts: string
  level: 'info' | 'warn' | 'error'
  msg: string
}

/** Settings-page log viewer: lazy-loads newest-first log pages from the host. */
export function OpsSettings(props: { t: Translate }): ReactElement {
  const { t } = props
  const [entries, setEntries] = React.useState<LogEntry[]>([])
  const [hasMore, setHasMore] = React.useState(false)
  const [offset, setOffset] = React.useState(0)

  const load = React.useCallback((nextOffset: number) => {
    void fetch(`${ROUTE_BASE}/logs?limit=200&offset=${nextOffset}`)
      .then(async (response) => {
        const body = (await response.json()) as { ok?: unknown; entries?: unknown; hasMore?: unknown }
        if (body.ok === true && Array.isArray(body.entries)) {
          const next = body.entries as LogEntry[]
          setEntries((previous) => (nextOffset === 0 ? next : [...previous, ...next]))
          setHasMore(body.hasMore === true)
          setOffset(nextOffset + next.length)
        }
      })
      .catch(() => {})
  }, [])

  React.useEffect(() => { load(0) }, [load])

  return React.createElement(
    'div',
    { className: 'maintainall-settings' },
    React.createElement('h2', { className: 'maintainall-modal__title' }, t('settings.logs')),
    entries.length === 0
      ? React.createElement('p', { className: 'maintainall-empty' }, t('settings.noLogs'))
      : React.createElement(
          'ul',
          { className: 'maintainall-log-list' },
          entries.map((entry) =>
            React.createElement(
              'li',
              { key: `${entry.ts}-${entry.msg}` },
              React.createElement('span', { className: 'maintainall-log-row__ts' }, entry.ts),
              React.createElement(
                'span',
                { className: `maintainall-log-row__level maintainall-log-row__level--${entry.level}` },
                entry.level,
              ),
              React.createElement('span', { className: 'maintainall-log-row__msg' }, entry.msg),
            ),
          ),
        ),
    hasMore
      ? React.createElement(
          'button',
          { type: 'button', className: 'maintainall-btn', onClick: () => load(offset) },
          t('settings.loadMore'),
        )
      : null,
  )
}
