/**
 * The maintainall locale namespace key list. Single source of truth for
 * bilingual completeness: `zh.ts` and `en.ts` are typed against it, and the
 * i18n unit test asserts both dictionaries cover exactly these keys with
 * matching `{placeholder}` sets.
 */

export const MAINTAINALL_KEYS = [
  // save capsule + dialog
  'save.button',
  'save.title',
  'save.naturalDescription',
  'save.auto',
  'save.mode.safeCopy.name',
  'save.mode.safeCopy.desc',
  'save.mode.compact.name',
  'save.mode.compact.desc',
  'save.mode.fresh.name',
  'save.mode.fresh.desc',
  'save.mode.auto.name',
  'save.mode.auto.desc',
  'save.mode.prev',
  'save.mode.next',
  'save.icon',
  'save.color',
  'save.taskId',
  'save.name',
  'save.description',
  'save.triggerSource',
  'save.cron',
  'save.scheduleKind',
  'save.scheduleKind.cron',
  'save.scheduleKind.daily',
  'save.scheduleKind.weekly',
  'save.scheduleKind.every',
  'save.scheduleKind.after',
  'save.scheduleKind.at',
  'save.timeZone',
  'save.time',
  'save.weekdays',
  'save.everySeconds',
  'save.afterSeconds',
  'save.at',
  'save.path',
  'save.webhookPath',
  'save.webhookToken',
  'save.command',
  'save.regex',
  'save.container',
  'save.when',
  'save.debounceMinutes',
  'save.maxPerHour',
  'save.submit',
  'save.cancel',
  'save.error',

  // Ops panel
  'ops.title',
  'ops.empty',
  'ops.error',
  'ops.loading',
  'ops.enable',
  'ops.disable',
  'ops.enabled',
  'ops.disabled',
  'ops.runOnce',
  'ops.menu',
  'ops.edit',
  'ops.earlier',
  'ops.delete',
  'ops.deleteConfirm',
  'ops.noDescription',
  'ops.noRuns',

  // settings page
  'settings.title',
  'settings.logs',
  'settings.loadMore',
  'settings.noLogs',
  'save.source.schedule',
  'save.source.filewatch',
  'save.source.docker',
  'save.source.journald',
  'save.source.webhook',
  'save.source.exec',
  'save.editTitle',
  'save.autoEdit',
] as const

export type MaintainAllKey = (typeof MAINTAINALL_KEYS)[number]

/** Flat locale dictionary shape (key -> template string with {name} placeholders). */
export type LocaleDict = Record<string, string>

/** The two shipped locales, mirroring `@deepseek-ai/dsh-client-locale`'s `LocaleId`. */
export type LocaleId = 'zh' | 'en'
