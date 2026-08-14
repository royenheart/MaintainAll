/**
 * Pure i18n helpers for the skills-manager namespace. The host/client plugins
 * hand these dictionaries to `ctx.locale.register('skills-manager', dicts)`;
 * this module keeps the dictionaries and their validation free of any dsh
 * import so they can be unit-tested in isolation.
 */

import { SKILL_MANAGER_KEYS, type LocaleDict, type LocaleId, type SkillManagerKey } from './keys.ts'
import { zh } from './zh.ts'
import { en } from './en.ts'

/** All shipped dictionaries keyed by locale id, ready for `ctx.locale.register`.
 * Typed against the key union so it matches the dsh `LocaleDictOf<'skills-manager'>`. */
export const dictionaries: Record<LocaleId, Record<SkillManagerKey, string>> = { zh, en }

/** Namespace id used with `ctx.locale.register` / `ctx.locale.bind`. */
export const NAMESPACE = 'skills-manager'

/** Extract the `{placeholder}` names from a template string. */
export function placeholdersOf(template: string): string[] {
  const seen = new Set<string>()
  const re = /\{([a-zA-Z0-9_]+)\}/g
  let match: RegExpExecArray | null
  while ((match = re.exec(template)) !== null) seen.add(match[1])
  return [...seen].sort()
}

/**
 * Validate bilingual symmetry: identical key sets and matching placeholder
 * sets per key. Returns a list of human-readable problems (empty = valid).
 */
export function validateDictionaries(
  a: LocaleDict,
  b: LocaleDict,
): string[] {
  const problems: string[] = []
  const keys = SKILL_MANAGER_KEYS as readonly string[]
  for (const key of keys) {
    const av = a[key]
    const bv = b[key]
    if (av === undefined) problems.push(`missing key "${key}" in first dictionary`)
    if (bv === undefined) problems.push(`missing key "${key}" in second dictionary`)
    if (av !== undefined && bv !== undefined) {
      const ap = placeholdersOf(av).join(',')
      const bp = placeholdersOf(bv).join(',')
      if (ap !== bp) {
        problems.push(`placeholder mismatch for "${key}": [${ap}] vs [${bp}]`)
      }
    }
  }
  for (const key of Object.keys(a)) {
    if (!keys.includes(key)) problems.push(`extra key "${key}" in first dictionary`)
  }
  for (const key of Object.keys(b)) {
    if (!keys.includes(key)) problems.push(`extra key "${key}" in second dictionary`)
  }
  return problems
}

/**
 * Minimal `{placeholder}` interpolation (the same convention the framework's
 * translate function follows). Missing placeholders render verbatim.
 */
export function interpolate(template: string, params: Record<string, string> = {}): string {
  return template.replace(/\{([a-zA-Z0-9_]+)\}/g, (whole, name: string) => {
    return name in params ? params[name] : whole
  })
}
