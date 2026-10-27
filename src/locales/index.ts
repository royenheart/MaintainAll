/**
 * Pure i18n surface for the maintainall namespace: key union plus the
 * symmetric zh/en dictionaries handed to `ctx.locale.register`. No dsh
 * imports, so the dictionaries are unit-testable with `node --test`.
 */

export { MAINTAINALL_KEYS } from './keys.ts'
export type { LocaleDict, LocaleId, MaintainAllKey } from './keys.ts'
export { zh } from './zh.ts'
export { en } from './en.ts'

import { zh } from './zh.ts'
import { en } from './en.ts'
import type { LocaleId, MaintainAllKey } from './keys.ts'

/** Namespace id used with `ctx.locale.register` / `ctx.locale.bind`. */
export const NAMESPACE = 'maintainall'

/** All shipped dictionaries keyed by locale id, ready for `ctx.locale.register`. */
export const dictionaries: Record<LocaleId, Record<MaintainAllKey, string>> = { zh, en }
