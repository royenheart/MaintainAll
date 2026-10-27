/**
 * Task manifest parsing, validation, checksums, and import rewriting.
 * Dependency-free core module: the only external dependency is `yaml`.
 */

import { createHash } from 'node:crypto'
import { parse as parseYaml } from 'yaml'
import type { ManifestBindings, TaskManifest } from './contract.ts'

/** The only manifest format this plugin reads and writes. */
export const MANIFEST_FORMAT = 'dsh-opskit/1'

/** Stable task id: lowercase letters, digits, hyphens; must not start with a hyphen. */
export const TASK_ID_RE = /^[a-z0-9][a-z0-9-]*$/

/** Reject a task id before using it in a filesystem path. */
export function assertTaskId(id: string): void {
  if (!TASK_ID_RE.test(id)) throw new Error(`invalid task id: ${JSON.stringify(id)}`)
}

/** Semver (with optional pre-release/build) as required by the asset format. */
const SEMVER_RE = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/

function fail(field: string, reason: string): never {
  throw new Error(`invalid task manifest: ${field} ${reason}`)
}

function optionalStringArray(value: unknown, field: string): string[] | undefined {
  if (value === undefined) return undefined
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) {
    fail(field, 'must be an array of strings')
  }
  return value as string[]
}

/**
 * Parse `manifest.yml` text into a validated {@link TaskManifest}.
 * Throws on YAML syntax errors and on schema violations.
 */
export function parseManifest(text: string): TaskManifest {
  const manifest = validateManifest(parseYaml(text))
  // `auto` was a supported persisted mode before it became request-only. It
  // always materialized without a seed, so read it as the equivalent `fresh`.
  if ((manifest as { taskMode?: unknown }).taskMode === 'auto') {
    return { ...manifest, taskMode: 'fresh' }
  }
  return manifest
}

/**
 * Validate an unknown value as a {@link TaskManifest}.
 * Throws a descriptive error on invalid `format`/`id`/`name`/`version`
 * (and on malformed optional sections); returns the value typed on success.
 */
export function validateManifest(manifest: unknown): TaskManifest {
  if (typeof manifest !== 'object' || manifest === null || Array.isArray(manifest)) {
    fail('manifest', 'must be a mapping')
  }
  const m = manifest as Record<string, unknown>

  if (m.format !== MANIFEST_FORMAT) {
    fail('format', `must be ${JSON.stringify(MANIFEST_FORMAT)}, got ${JSON.stringify(m.format)}`)
  }
  if (typeof m.id !== 'string') fail('id', 'must be a string')
  try {
    assertTaskId(m.id)
  } catch {
    fail('id', `must match ${TASK_ID_RE.source}, got ${JSON.stringify(m.id)}`)
  }
  if (typeof m.name !== 'string' || m.name.trim() === '') {
    fail('name', 'must be a non-empty string')
  }
  if (typeof m.version !== 'string' || !SEMVER_RE.test(m.version)) {
    fail('version', `must be a semver string, got ${JSON.stringify(m.version)}`)
  }
  if (m.description !== undefined && typeof m.description !== 'string') {
    fail('description', 'must be a string when present')
  }
  for (const field of ['icon', 'color', 'naturalPrompt'] as const) {
    if (m[field] !== undefined && typeof m[field] !== 'string') {
      fail(field, 'must be a string when present')
    }
  }
  if (m.taskMode !== undefined && m.taskMode !== 'safe-copy' && m.taskMode !== 'compact' && m.taskMode !== 'fresh' && m.taskMode !== 'auto') {
    fail('taskMode', 'must be safe-copy, compact, fresh, or legacy auto')
  }

  if (m.requires !== undefined) {
    if (typeof m.requires !== 'object' || m.requires === null || Array.isArray(m.requires)) {
      fail('requires', 'must be a mapping')
    }
    const requires = m.requires as Record<string, unknown>
    if (requires.dsh !== undefined && typeof requires.dsh !== 'string') {
      fail('requires.dsh', 'must be a string when present')
    }
    optionalStringArray(requires.tools, 'requires.tools')
    if (requires.mcpServers !== undefined) {
      if (
        !Array.isArray(requires.mcpServers) ||
        requires.mcpServers.some(
          (s) =>
            typeof s !== 'object' ||
            s === null ||
            typeof (s as Record<string, unknown>).name !== 'string' ||
            typeof (s as Record<string, unknown>).optional !== 'boolean',
        )
      ) {
        fail('requires.mcpServers', 'must be an array of { name: string, optional: boolean }')
      }
    }
    if (requires.secrets !== undefined) {
      if (
        !Array.isArray(requires.secrets) ||
        requires.secrets.some(
          (s) =>
            typeof s !== 'object' ||
            s === null ||
            typeof (s as Record<string, unknown>).name !== 'string' ||
            typeof (s as Record<string, unknown>).env !== 'string',
        )
      ) {
        fail('requires.secrets', 'must be an array of { name: string, env: string }')
      }
    }
  }

  if (m.bindings !== undefined) {
    if (typeof m.bindings !== 'object' || m.bindings === null || Array.isArray(m.bindings)) {
      fail('bindings', 'must be a mapping')
    }
    for (const key of ['agentPreset', 'permissionPreset'] as const) {
      const binding = (m.bindings as Record<string, unknown>)[key]
      if (binding === undefined) continue
      if (
        typeof binding !== 'object' ||
        binding === null ||
        typeof (binding as Record<string, unknown>).hint !== 'string'
      ) {
        fail(`bindings.${key}`, 'must be { hint: string } when present')
      }
    }
  }

  if (m.checksums !== undefined) {
    if (
      typeof m.checksums !== 'object' ||
      m.checksums === null ||
      Array.isArray(m.checksums) ||
      Object.values(m.checksums).some((v) => typeof v !== 'string')
    ) {
      fail('checksums', 'must be a mapping of path to sha256 hex')
    }
  }

  return { description: '', ...m } as unknown as TaskManifest
}

/** sha256 hex digest of a string. */
export function sha256Hex(content: string): string {
  return createHash('sha256').update(content, 'utf8').digest('hex')
}

/**
 * Compute sha256 hex checksums for every file content in `files`,
 * keyed by the same (task-relative) path.
 */
export function computeChecksums(files: Map<string, string>): Record<string, string> {
  const checksums: Record<string, string> = {}
  for (const [path, content] of files) {
    checksums[path] = sha256Hex(content)
  }
  return checksums
}

/** Local bindings resolved on the importing machine. */
export interface ImportBindings {
  agentPreset?: string
  permissionPreset?: string
}

/**
 * Return a new manifest for import: `bindings` are replaced with the
 * provided machine-local bindings (never shipped inside an exported asset),
 * while `requires.secrets` — and everything else — is carried over unchanged.
 * The input manifest is not mutated.
 */
export function rewriteManifestForImport(
  manifest: TaskManifest,
  bindings: ImportBindings,
): TaskManifest {
  const copy = JSON.parse(JSON.stringify(manifest)) as TaskManifest
  const next: ManifestBindings = {}
  if (bindings.agentPreset !== undefined) next.agentPreset = { hint: bindings.agentPreset }
  if (bindings.permissionPreset !== undefined) next.permissionPreset = { hint: bindings.permissionPreset }
  if (Object.keys(next).length > 0) {
    copy.bindings = next
  } else {
    delete copy.bindings
  }
  return copy
}
