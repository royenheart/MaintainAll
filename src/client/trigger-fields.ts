/**
 * Pure mapping between the Save dialog's source fields and the host's
 * `TaskTrigger.filter` contract.
 *
 * The engine reads filewatch/webhook paths from `filter.path`, exec commands
 * from `filter.command`, and docker/journald selectors from `filter.container`
 * and `filter.regex`. The host normalizes legacy `params.path`/`params.command`
 * before this client reads a task; this helper only reads canonical filters.
 */

/** The trigger sources the save dialog offers. */
export const TRIGGER_SOURCES = ['schedule', 'filewatch', 'docker', 'journald', 'webhook', 'exec'] as const
export type TriggerSource = (typeof TRIGGER_SOURCES)[number]

/** Which source-specific field the dialog shows. */
export type SourceField = 'path' | 'command' | 'regex'

export function sourceFieldOf(source: TriggerSource): SourceField {
  if (source === 'filewatch' || source === 'webhook') return 'path'
  if (source === 'exec') return 'command'
  return 'regex'
}

export interface TriggerFields {
  path: string
  regex: string
  token?: string
}

function firstString(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === 'string') return value
  }
  return ''
}

/** Read the editable source fields from the host-normalized filter. */
export function readTriggerFields(
  trigger: { filter?: Record<string, unknown> } | undefined,
  source?: TriggerSource,
): TriggerFields {
  const filter = trigger?.filter
  const path = source === 'exec'
    ? firstString(filter?.command, filter?.path)
    : source === 'webhook'
      // Legacy webhook assets stored a display-only `/hooks/...` value that
      // the engine never matched; the route trigger id is the selector.
      ? firstString(filter?.path)
      : firstString(filter?.path, filter?.command)
  return {
    path,
    regex: firstString(filter?.regex, filter?.container),
    ...(typeof filter?.token === 'string' ? { token: filter.token } : {}),
  }
}

/**
 * Build the host-facing filter for a non-schedule source. Existing
 * source-native fields are preserved; only the field edited by this dialog is
 * replaced. Empty selectors are removed rather than written as empty strings.
 */
export function buildTriggerFilter(
  source: Exclude<TriggerSource, 'schedule'>,
  fields: TriggerFields,
  base: Record<string, unknown> = {},
): Record<string, unknown> {
  const filter = { ...base }
  const set = (key: string, value: string): void => {
    if (value === '') delete filter[key]
    else filter[key] = value
  }
  switch (source) {
    case 'filewatch':
      set('path', fields.path)
      set('regex', fields.regex)
      break
    case 'webhook':
      // The trigger id selects the task; the path is an optional exact full
      // request pathname and the bearer token authenticates the call.
      set('path', fields.path)
      if (fields.token !== undefined) set('token', fields.token)
      break
    case 'exec':
      set('command', fields.path)
      break
    case 'docker':
      set('container', fields.regex)
      break
    case 'journald':
      set('regex', fields.regex)
      break
  }
  return filter
}
