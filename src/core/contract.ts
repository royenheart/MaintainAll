/**
 * Shared types and data contracts for `@royenheart/dsh-plugin-maintainall`.
 * This module must stay dependency-free: it is imported by `src/core/`,
 * `src/index.ts`, and tests directly.
 */

/** Stable task id: lowercase letters, digits, hyphens. */
export type TaskId = string

/** CEL condition expression evaluated over a normalized `TriggerEvent`. */
export type CelExpression = string

/** Trigger sources that can be declared on a task; manual is event-only. */
export const TASK_TRIGGER_SOURCES = [
  'schedule',
  'filewatch',
  'docker',
  'journald',
  'webhook',
  'exec',
] as const

export type TaskTriggerSource = (typeof TASK_TRIGGER_SOURCES)[number]

/** Every normalized event source, including manual runs. */
export type TriggerSourceKind = TaskTriggerSource | 'manual'

/** Normalized trigger event produced by every source. */
export interface TriggerEvent {
  /** Source that produced the event. */
  source: TriggerSourceKind
  /** RFC 3339 UTC instant when the source observed the event. */
  occurredAt: string
  /** Source-specific, JSON-serializable event payload. */
  payload: Record<string, unknown>
}

/** Common scheduling and debounce settings for a trigger. */
export interface TriggerRateLimit {
  /** Minimum interval between two accepted firings, in seconds. */
  minIntervalSeconds: number
  /** Maximum accepted firings per rolling hour; 0 means no hourly cap. */
  maxPerHour: number
}

/** Serializable rate-limit state for one trigger. */
export interface RateState {
  lastFiredAt?: string
  fireTimestamps: string[]
}

/** One trigger declaration inside `triggers.yml`. */
export interface TaskTrigger {
  id: string
  source: TaskTriggerSource
  /** Source-native filter; exact fields depend on `source`. */
  filter?: Record<string, unknown>
  /** Optional deterministic CEL condition over `TriggerEvent`. */
  when?: CelExpression
  rate?: TriggerRateLimit
  /** Source-specific parameters; exact fields depend on `source`. */
  params?: Record<string, unknown>
  enabled: boolean
}

/** Machine-local bindings that import must re-resolve, never ship. */
export interface ManifestBindings {
  agentPreset?: { hint: string }
  permissionPreset?: { hint: string }
}

/** External requirements a task declares. */
export interface ManifestRequires {
  dsh?: string
  tools?: string[]
  mcpServers?: Array<{ name: string; optional: boolean }>
  secrets?: Array<{ name: string; env: string }>
}

/** `manifest.yml` contents. */
export type TaskMode = 'safe-copy' | 'compact' | 'fresh' | 'auto'

/** A task asset stores only a concrete creation mode; `auto` is request-only. */
export type PersistedTaskMode = Exclude<TaskMode, 'auto'>

export interface TaskManifest {
  format: 'dsh-opskit/1'
  id: TaskId
  name: string
  description: string
  version: string
  /** How the task was created / how runs should be seeded. */
  taskMode?: PersistedTaskMode
  /** Emoji shown in the Ops panel for this task. */
  icon?: string
  /** CSS color for the task name in the Ops panel. */
  color?: string
  /** Original natural-language description used to create the task. */
  naturalPrompt?: string
  requires?: ManifestRequires
  bindings?: ManifestBindings
  checksums?: Record<string, string>
}

/** One durable session event inside `seed/session.jsonl`. */
export interface SeedEvent {
  type: string
  seq: number
  /** Milliseconds since epoch; required by dsh session seeds. */
  time?: number
  /** Replay always appends this event; dsh surface replacement is not modeled yet. */
  surfaceOp?: 'append'
  data?: unknown
}

/** Compact replay seed file contents. */
export interface TaskSeed {
  /** Session header line equivalent: source cwd for import rewriting. */
  cwd: string
  events: SeedEvent[]
}

/** Registry record for one materialized task. */
export interface TaskRegistryRecord {
  id: TaskId
  name: string
  version: string
  enabled: boolean
  importedAt: string
  lastRunAt?: string
  icon?: string
  color?: string
}

/** Plugin state persisted to `storages/registry.json`. */
export interface RegistryState {
  version: 1
  tasks: Record<TaskId, TaskRegistryRecord>
}

/** Committed schedule target for one `schedule` trigger. */
export interface ScheduleTriggerState {
  /** RFC 3339 UTC instant of the next (or most recently committed) fire. */
  scheduledAt: string
  /** Normalized rule identity; a change resets the committed target. */
  ruleKey: string
  /** True once a one-shot fired or a recurring rule has no future target. */
  done?: boolean
}

/** Plugin state persisted to `storages/trigger-state.json`. */
export interface TriggerState {
  version: 2
  /** Per trigger id -> debounce/rate state. */
  triggers: Record<string, RateState>
  /** Per trigger id -> committed schedule target and one-shot completion. */
  schedules: Record<string, ScheduleTriggerState>
  /** Per trigger id -> absolute path -> filewatch offset. */
  filewatch: Record<string, Record<string, { offset: number; inode?: number }>>
  /** exec last output/exit keyed by task/trigger id. */
  exec: Record<string, { stdout?: string; stderr?: string; exitCode?: number }>
}

/** Run map persisted to `storages/run-map.json`. */
export interface RunMapState {
  version: 1
  runs: Record<string, { taskId: TaskId; sessionId: string; cwd: string; createdAt: string }>
}
