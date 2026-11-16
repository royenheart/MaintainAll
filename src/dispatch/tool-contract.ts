/**
 * Model-facing contract for `ops_save_task` triggers.
 *
 * The host validates the same shape with `validateTaskTriggers`. Keeping the
 * JSON schema, the tool-description guide, and the Save prompt lines in one
 * module prevents the model from guessing that `source` is a cron expression,
 * path, or command — the exact ambiguity that made a long save turn fail
 * repeatedly in the field. The accepted source names come from
 * `TASK_TRIGGER_SOURCES`, so the schema, guide, prompt, and validator cannot
 * drift independently.
 */

import { TASK_TRIGGER_SOURCES } from '../core/contract.ts'
import type { TaskTrigger } from '../core/contract.ts'

/** Human-readable suffix list, e.g. `schedule / filewatch / ...`. */
const SOURCE_LIST = TASK_TRIGGER_SOURCES.join(' / ')

/** JSON schema for one trigger item passed to `ops_save_task`. */
export const OPS_SAVE_TASK_TRIGGER_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['id', 'source', 'enabled'],
  properties: {
    id: {
      type: 'string',
      description: 'Unique trigger id. Webhook trigger ids must additionally be URL-safe.',
    },
    source: {
      type: 'string',
      enum: [...TASK_TRIGGER_SOURCES],
      description: 'Trigger kind. This is never a path, command, or schedule expression.',
    },
    enabled: { type: 'boolean' },
    params: {
      type: 'object',
      additionalProperties: true,
      description:
        'Schedule rules only: exactly one of cron, daily, weekly, everySeconds, afterSeconds, or at.',
    },
    filter: {
      type: 'object',
      additionalProperties: true,
      description:
        'Source-native selectors: filewatch path, exec command, docker container/events, '
        + 'journald regex, webhook token (+ optional path).',
    },
    when: {
      type: 'string',
      description: 'Optional deterministic CEL condition over the normalized trigger event.',
    },
    rate: {
      type: 'object',
      additionalProperties: false,
      required: ['minIntervalSeconds', 'maxPerHour'],
      properties: {
        minIntervalSeconds: { type: 'number', minimum: 0 },
        maxPerHour: { type: 'number', minimum: 0 },
      },
    },
  },
}

/** One labeled trigger example shown to the model. */
interface TriggerExample {
  label: string
  trigger: TaskTrigger
}

/**
 * Trigger examples that pass host validation for every documented shape. The
 * guide renders these examples directly, and the contract test parses the
 * rendered JSON back and revalidates it.
 */
export const TRIGGER_EXAMPLES: TriggerExample[] = [
  {
    label: 'every 30 minutes',
    trigger: { id: 'every-30m', source: 'schedule', enabled: true, params: { everySeconds: 1800 } },
  },
  {
    label: 'daily cron',
    trigger: {
      id: 'nightly',
      source: 'schedule',
      enabled: true,
      params: { cron: { expression: '0 21 * * *', time_zone: 'Asia/Shanghai' } },
    },
  },
  {
    label: 'daily wall clock',
    trigger: {
      id: 'daily-0900',
      source: 'schedule',
      enabled: true,
      params: { daily: { time: '09:00:00', time_zone: 'Asia/Shanghai' } },
    },
  },
  {
    label: 'weekly ISO weekdays (Monday=1)',
    trigger: {
      id: 'weekly-mon-wed-fri',
      source: 'schedule',
      enabled: true,
      params: { weekly: { time: '09:00:00', time_zone: 'Asia/Shanghai', weekdays: [1, 3, 5] } },
    },
  },
  {
    label: 'one-shot after delay',
    trigger: { id: 'after-10m', source: 'schedule', enabled: true, params: { afterSeconds: 600 } },
  },
  {
    label: 'one-shot absolute instant',
    trigger: {
      id: 'at-2026-11-03',
      source: 'schedule',
      enabled: true,
      params: { at: { date: '2026-11-03', time: '09:00:00', time_zone: 'Asia/Shanghai' } },
    },
  },
  {
    label: 'config file',
    trigger: {
      id: 'watch-nginx-config',
      source: 'filewatch',
      enabled: true,
      filter: { path: '/etc/nginx/nginx.conf' },
    },
  },
  {
    label: 'container event',
    trigger: {
      id: 'restart-after-docker-event',
      source: 'docker',
      enabled: true,
      filter: { events: ['start'], container: 'nginx' },
    },
  },
  {
    label: 'journal errors',
    trigger: {
      id: 'journald-errors',
      source: 'journald',
      enabled: true,
      filter: { regex: 'error' },
    },
  },
  {
    label: 'webhook',
    trigger: {
      id: 'webhook-deploy',
      source: 'webhook',
      enabled: true,
      filter: { token: 'replace-with-a-random-token' },
    },
  },
  {
    label: 'command edge',
    trigger: { id: 'check-disk', source: 'exec', enabled: true, filter: { command: 'df -h /' } },
  },
]

/** Rendered `- label: {json}` example lines used by the guide and its test. */
export const TRIGGER_EXAMPLE_LINES: readonly string[] = TRIGGER_EXAMPLES.map(
  (example) => `- ${example.label}: ${JSON.stringify(example.trigger)}`,
)

/**
 * Short contract embedded in the `ops_save_task` tool description. Every
 * source name, `params`, and `filter` must appear here: the model reads this
 * description, not the host validator.
 */
export const OPS_SAVE_TASK_TRIGGER_GUIDE = [
  'Each trigger is one object: {id, source, enabled} plus params for schedule and filter',
  `for the other sources. \`source\` is the trigger kind (${SOURCE_LIST}), never a cron`,
  'expression, path, command, or schedule string.',
  '',
  'Schedule `params` holds exactly one rule:',
  '- cron: {"cron":{"expression":"0 21 * * *","time_zone":"Asia/Shanghai"}}',
  '- daily: {"daily":{"time":"09:00:00","time_zone":"Asia/Shanghai"}}',
  '- weekly: {"weekly":{"time":"09:00:00","time_zone":"Asia/Shanghai","weekdays":[1,3,5]}} (ISO weekdays, Monday=1, Sunday=7)',
  '- fixed interval: {"everySeconds":1800} (integer >= 60)',
  '- one-shot delay: {"afterSeconds":600} (positive integer)',
  '- one-shot instant: {"at":"2026-11-03T09:00:00+08:00"} or {"at":{"date":"2026-11-03","time":"09:00:00","time_zone":"Asia/Shanghai"}}',
  '',
  'Examples:',
  ...TRIGGER_EXAMPLE_LINES,
  '`when` is an optional CEL expression over the trigger event; `rate` is an optional',
  '{minIntervalSeconds, maxPerHour} object.',
].join('\n')

/** Trigger-contract bullets embedded in the Save prompt. */
export const SAVE_PROMPT_TRIGGER_LINES: readonly string[] = [
  `- \`triggers\` is an array; each item is \`{id, source, enabled}\` plus \`params\` for schedule and \`filter\` for the other sources. \`source\` is the trigger kind (${SOURCE_LIST}), not a cron expression, path, command, or schedule string.`,
  '- Schedule uses exactly one rule in `params`: `everySeconds` (integer >= 60), `cron: {expression, time_zone}`, `daily: {time, time_zone}`, `weekly: {time, time_zone, weekdays}`, `at` (RFC 3339 string with offset or `{date, time, time_zone}`), or `afterSeconds` (positive integer). ISO weekdays are Monday=1 through Sunday=7. Example: `{"id":"every-30m","source":"schedule","enabled":true,"params":{"everySeconds":1800}}`.',
  '- filewatch uses `filter.path`; exec uses `filter.command`; docker uses `filter.container` + `filter.events`; journald uses `filter.regex`; webhook uses `filter.token` (+ optional `filter.path`). `when` is an optional CEL expression; `rate` is `{minIntervalSeconds, maxPerHour}`.',
]
