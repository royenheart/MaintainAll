/**
 * Skill identification for the manager.
 *
 * The manager must only recognise skills coming from the shared `.agents`
 * directories and dsh's own skill directories. Skills discovered by other
 * agents (for example `.claude/skills`, `.codex/skills`, `.cursor/rules`, or
 * any third-party provider) are deliberately NOT managed.
 *
 * This mirrors the source taxonomy of `@deepseek-ai/dsh-skill`:
 *
 *   project-dsh    <projectRoot>/.dsh/skills        (dsh's own project dir)
 *   project-agents <projectRoot>/.agents/skills     (shared `.agents` dir)
 *   user-dsh       <dshHome>/skills                 (dsh's own user dir)
 *   user-agents    <agentsHome>/skills              (shared user `.agents`)
 *
 * Everything else (`runtime`, `custom`, `bundled`, and other agents' own
 * names) is out of scope for this manager.
 */

/** Sources the manager is allowed to manage. */
export const MANAGED_SOURCES = [
  'project-dsh',
  'project-agents',
  'user-dsh',
  'user-agents',
] as const

export type ManagedSource = (typeof MANAGED_SOURCES)[number]

const MANAGED_SOURCE_SET: ReadonlySet<string> = new Set(MANAGED_SOURCES)

/** Whether a source string is one the manager recognises and manages. */
export function isManagedSource(source: string): boolean {
  return MANAGED_SOURCE_SET.has(source)
}

/**
 * Globally-available (user-level) sources: present in every workspace, so a
 * GLOBAL override is meaningful for them. Project sources are workspace-scoped
 * and belong to the workspace/session panels instead.
 */
export const GLOBAL_SOURCES = ['user-dsh', 'user-agents'] as const

/** Workspace-scoped (project-level) sources: resolved against one project cwd. */
export const WORKSPACE_SOURCES = ['project-dsh', 'project-agents'] as const

const GLOBAL_SOURCE_SET: ReadonlySet<string> = new Set(GLOBAL_SOURCES)

/** Whether a source is globally available (user-level, not project-scoped). */
export function isGlobalSource(source: string): boolean {
  return GLOBAL_SOURCE_SET.has(source)
}

/**
 * The minimal skill shape the manager needs from the host skill registry.
 * Deliberately a subset of `@deepseek-ai/dsh-skill`'s `SkillSummary` so the
 * core stays dependency-free and unit-testable.
 */
export interface IdentifiedSkill {
  readonly name: string
  readonly source: string
  readonly description?: string
}

/**
 * Partition a discovered skill list into managed vs ignored, sorted by name.
 * A skill whose name is not kebab-case is also dropped (the filesystem provider
 * already enforces this, but the manager re-checks for robustness).
 */
export function identifySkills(skills: readonly IdentifiedSkill[]): {
  managed: IdentifiedSkill[]
  ignored: IdentifiedSkill[]
} {
  const managed: IdentifiedSkill[] = []
  const ignored: IdentifiedSkill[] = []
  for (const skill of skills) {
    if (isManagedSource(skill.source) && isSkillName(skill.name)) managed.push(skill)
    else ignored.push(skill)
  }
  managed.sort(byName)
  ignored.sort(byName)
  return { managed, ignored }
}

/** Return only the managed skills, sorted by name. */
export function managedSkills(skills: readonly IdentifiedSkill[]): IdentifiedSkill[] {
  return identifySkills(skills).managed
}

/**
 * Kebab-case skill-name grammar, matching `@deepseek-ai/dsh-skill`'s
 * `isSkillName`: lowercase letters, digits, and single hyphens between them.
 */
export function isSkillName(name: string): boolean {
  return /^[a-z0-9]+(-[a-z0-9]+)*$/.test(name)
}

/**
 * Apply the scoped override store to a discovered skill list and return the
 * names that stay enabled for a view, using managed-source identification.
 * `resolve` is injected so this stays free of a hard dependency on scope.ts
 * while remaining trivially composable with it.
 */
export function filterEnabledSkills(
  skills: readonly IdentifiedSkill[],
  isEnabled: (name: string) => boolean,
): IdentifiedSkill[] {
  return managedSkills(skills).filter((skill) => isEnabled(skill.name))
}

function byName(a: IdentifiedSkill, b: IdentifiedSkill): number {
  return a.name < b.name ? -1 : a.name > b.name ? 1 : 0
}
