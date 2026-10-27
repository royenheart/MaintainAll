/**
 * Backward-compatible normalization for source fields written by older Save
 * dialogs. The engine reads filewatch paths from `filter.path`, exec commands
 * from `filter.command`, and docker/journald selectors from `filter.*`; legacy
 * assets may still have `params.path`/`params.command`.
 */

import type { TaskTrigger } from '../contract.ts'

/** Move legacy source fields into `filter` and drop retired webhook paths. */
export function normalizeTriggerFilter(trigger: TaskTrigger): TaskTrigger {
  if (
    trigger.source !== 'filewatch'
    && trigger.source !== 'webhook'
    && trigger.source !== 'exec'
  ) {
    return trigger
  }
  const filter: Record<string, unknown> = trigger.filter === undefined ? {} : { ...trigger.filter }
  let changed = false
  if (trigger.source === 'webhook' && typeof filter.path === 'string') {
    // The old Save dialog wrote a display-only `/hooks/...` value that can
    // never equal the host request pathname. An explicit empty path also means
    // "no path filter"; omit it so the trigger id selects the route.
    if (filter.path === '' || filter.path === '/hooks' || filter.path.startsWith('/hooks/')) {
      delete filter.path
      changed = true
    }
  }
  const rawParams = trigger.params
  const params = rawParams !== null && typeof rawParams === 'object' && !Array.isArray(rawParams)
    ? rawParams
    : undefined
  const nextParams: Record<string, unknown> = params === undefined ? {} : { ...params }
  if (rawParams !== undefined && params === undefined) changed = true
  if (params !== undefined) {
    if (trigger.source === 'webhook' && typeof nextParams.path === 'string') {
      delete nextParams.path
      changed = true
    }
    if (
      trigger.source === 'filewatch'
      && (typeof filter.path !== 'string' || filter.path === '')
      && typeof params.path === 'string'
    ) {
      filter.path = params.path
      delete nextParams.path
      changed = true
    }
    if (
      trigger.source === 'exec'
      && (typeof filter.command !== 'string' || filter.command === '')
      && typeof params.command === 'string'
    ) {
      filter.command = params.command
      delete nextParams.command
      changed = true
    }
  }
  if (!changed) return trigger
  const next: TaskTrigger = { ...trigger }
  if (Object.keys(filter).length === 0) delete next.filter
  else next.filter = filter
  if (params === undefined) delete next.params
  else if (Object.keys(nextParams).length === 0) delete next.params
  else next.params = nextParams
  return next
}
