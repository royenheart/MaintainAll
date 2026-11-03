/**
 * Pure request payload builders for the Save dialog.
 *
 * Keeping the wire payloads out of the React component makes the
 * creation-time continuation contract testable: continuation requests always
 * send `taskMode: "fresh"` and `continueSession: true`, while both edit paths
 * never change the replay target. No dsh imports and no React.
 */

import type { TaskMode } from '../core/contract.ts'

/** Trigger shape the dialog submits to the host. */
export interface TriggerRequestPayload {
  id: string
  source: string
  enabled: boolean
  when?: string
  params?: Record<string, unknown>
  filter?: Record<string, unknown>
  rate?: { minIntervalSeconds: number; maxPerHour: number }
}

/** Shared creation fields collected by the Save dialog. */
export interface CreateSaveFields {
  sessionId: string
  mode: string
  continueSession: boolean
  icon: string
  color: string
  naturalPrompt: string
}

/** New-task fields for the manual materialize path. */
export interface ManualCreateFields extends CreateSaveFields {
  taskId: string
  name: string
  description: string
  trigger: TriggerRequestPayload
}

/** New-task fields for the model-driven auto path. */
export interface AutoCreateFields extends CreateSaveFields {
  description: string
}

/** Creation mode actually sent to the host; continuation always stores no seed. */
export function effectiveCreateTaskMode(continueSession: boolean, mode: string): TaskMode {
  return continueSession ? 'fresh' : (mode as TaskMode)
}

/** POST /save body for the model-driven create path. */
export function buildAutoCreateSaveRequest(fields: AutoCreateFields): {
  sessionId: string
  boundarySeq: number
  meta: Record<string, unknown>
} {
  return {
    sessionId: fields.sessionId,
    boundarySeq: 0,
    meta: {
      auto: true,
      description: fields.description,
      taskMode: effectiveCreateTaskMode(fields.continueSession, fields.mode),
      continueSession: fields.continueSession,
      icon: fields.icon,
      color: fields.color,
      naturalPrompt: fields.naturalPrompt,
    },
  }
}

/** POST /save body for the manual materialize create path. */
export function buildManualCreateSaveRequest(fields: ManualCreateFields): {
  sessionId: string
  boundarySeq: number
  meta: Record<string, unknown>
} {
  return {
    sessionId: fields.sessionId,
    boundarySeq: 0,
    meta: {
      id: fields.taskId,
      name: fields.name,
      description: fields.description,
      materialize: true,
      taskMode: effectiveCreateTaskMode(fields.continueSession, fields.mode),
      continueSession: fields.continueSession,
      icon: fields.icon,
      color: fields.color,
      naturalPrompt: fields.naturalPrompt,
      triggers: [fields.trigger],
    },
  }
}

/** POST /tasks/<id>/edit body for the natural-language edit path. */
export function buildEditLlmRequest(fields: {
  description: string
  icon: string
  color: string
  naturalPrompt: string
}): Record<string, unknown> {
  return {
    description: fields.description,
    icon: fields.icon,
    color: fields.color,
    naturalPrompt: fields.naturalPrompt,
  }
}

/** POST /tasks/<id>/edit body for the metadata-only edit path. */
export function buildEditMaterializeRequest(fields: {
  name: string
  description: string
  triggers: TriggerRequestPayload[]
  icon: string
  color: string
  naturalPrompt: string
}): Record<string, unknown> {
  return {
    materialize: true,
    meta: {
      name: fields.name,
      description: fields.description,
      triggers: fields.triggers,
      icon: fields.icon,
      color: fields.color,
      naturalPrompt: fields.naturalPrompt,
    },
  }
}
