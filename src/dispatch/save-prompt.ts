/**
 * Save and edit prompts injected into a dsh session when the user asks the
 * model to generate or reconfigure a task asset.
 *
 * Pure string construction so the trigger contract and the measured seed
 * budget stay testable without a dsh runtime.
 */

import type { TaskManifest, TaskTrigger } from '../core/contract.ts'
import { SAVE_PROMPT_TRIGGER_LINES } from './tool-contract.ts'

/** Optional metadata the Save dialog pinned for the generated task. */
export interface SavePromptWants {
  icon?: string
  color?: string
  naturalPrompt?: string
}

/** Measured replay-seed cost shown to the model before it saves a task. */
export interface SavePromptSeed {
  boundarySeq: number
  safeCopyBytes: number
  compactBytes: number
  safeCopyEventCount: number
  compactEventCount: number
  maxBytes: number
  maxEvents: number
}

/** Render one replay-seed budget bullet for a concrete capture mode. */
function concreteSeedLine(seed: SavePromptSeed, taskMode: string): string {
  const compact = taskMode === 'compact'
  const bytes = compact ? seed.compactBytes : seed.safeCopyBytes
  const eventCount = compact ? seed.compactEventCount : seed.safeCopyEventCount
  return `- Replay seed at \`boundarySeq\` ${seed.boundarySeq}: ${taskMode} stores ${bytes} bytes across ${eventCount} events; the host preflight confirmed it fits the ${seed.maxBytes} byte / ${seed.maxEvents} event cap.`
}

/** Render the `auto` mode budget bullet with explicit per-mode eligibility. */
function autoSeedLine(seed: SavePromptSeed): string {
  const safeFits = seed.safeCopyBytes <= seed.maxBytes && seed.safeCopyEventCount <= seed.maxEvents
  const compactFits = seed.compactBytes <= seed.maxBytes && seed.compactEventCount <= seed.maxEvents
  return `- Replay seed at \`boundarySeq\` ${seed.boundarySeq}: safe-copy ${seed.safeCopyBytes} bytes / ${seed.safeCopyEventCount} events (${safeFits ? 'fits' : 'exceeds'} the ${seed.maxBytes} byte / ${seed.maxEvents} event cap); compact ${seed.compactBytes} bytes / ${seed.compactEventCount} events (${compactFits ? 'fits' : 'exceeds'} the cap). Choose a mode marked "fits"; if neither fits choose \`fresh\`.`
}

/** Render the prompt that asks the model to generate a task asset. */
export function buildSavePrompt(
  description: string,
  boundarySeq: number,
  taskMode: string,
  wants?: SavePromptWants,
  seed?: SavePromptSeed,
  seedUnavailable?: string,
  continueSession?: boolean,
): string {
  const modeLine = taskMode === 'auto'
    ? '- `taskMode` is `auto`: choose `safe-copy` / `compact` / `fresh` yourself and pass it to `ops_save_task`'
    : `- \`taskMode\` must be ${JSON.stringify(taskMode)}`
  const desired = [
    wants?.icon === undefined ? null : `- \`icon\` must be ${JSON.stringify(wants.icon)}`,
    wants?.color === undefined ? null : `- \`color\` must be ${JSON.stringify(wants.color)}`,
    wants?.naturalPrompt === undefined || wants.naturalPrompt === ''
      ? null
      : `- \`naturalPrompt\` must be ${JSON.stringify(wants.naturalPrompt)}`,
  ].filter((line) => line !== null)
  const safeCopyFits = seed !== undefined
    && seed.safeCopyBytes <= seed.maxBytes
    && seed.safeCopyEventCount <= seed.maxEvents
  const compactFits = seed !== undefined
    && seed.compactBytes <= seed.maxBytes
    && seed.compactEventCount <= seed.maxEvents
  const autoCaptureFits = taskMode !== 'auto' || safeCopyFits || compactFits
  const seedLines = taskMode === 'fresh'
    ? []
    : seedUnavailable !== undefined
      ? [`- Replay seed cannot be captured at \`boundarySeq\` ${boundarySeq}: ${seedUnavailable}. Choose \`taskMode\` "fresh" and tell the user the run has no replay seed.`]
      : seed === undefined
        ? []
        : taskMode === 'auto'
          ? [autoSeedLine(seed)]
          : [concreteSeedLine(seed, taskMode)]
  const continuationLines = continueSession === true
    ? [
        '- This task continues the source session instead of creating a new Run session: pass `replayMode` `"continue-session"` to `ops_save_task`, keep `taskMode` `"fresh"`, and do not capture a replay seed.',
        '- Do not bind `agentPreset` or `permissionPreset`: the source session keeps its own agent preset, permissions, title, and working directory.',
        '- Write a self-contained runbook, because the run executes in the source session workspace rather than a materialized run directory; reference the task asset directory for scripts/skills when needed.',
      ]
    : []
  const seedBoundaryLines = taskMode === 'fresh'
    ? [
        '- `taskMode` is `fresh`: no replay seed is stored, so write a self-contained runbook and do not copy the conversation into the task.',
        `- Use \`boundarySeq\` ${boundarySeq} (required by the tool but unused for \`fresh\`)`,
      ]
    : seedUnavailable !== undefined
      ? [
          '- No replay seed can be captured for this session, so write a self-contained runbook and choose `fresh`.',
          `- Use \`boundarySeq\` ${boundarySeq} (required by the tool but unused when no seed is captured)`,
        ]
      : !autoCaptureFits
        ? [
            '- Neither safe-copy nor compact fits the seed budget at this boundary, so no replay seed will be stored: choose `fresh` and write a self-contained runbook.',
            `- Use \`boundarySeq\` ${boundarySeq} (required by the tool but unused when no seed is captured)`,
          ]
        : [
            '- The replay seed is a frozen snapshot cut at `boundarySeq`; later turns of the source session are not included. Make a recurring runbook discover its scope at run time instead of hardcoding volatile object lists.',
            ...(taskMode === 'auto'
              ? ['- Choose `safe-copy` or `compact` to store that seed; `fresh` stores no seed and needs a self-contained runbook.']
              : []),
            `- Use \`boundarySeq\` ${boundarySeq} (that trace and earlier become the replay seed${taskMode === 'auto' ? ', when a capture mode is chosen' : ''})`,
          ]
  return [
    continueSession === true
      ? 'Save the current session as an ops task that continues this source session.'
      : 'Save the current session as a replayable ops task.',
    '',
    "The user's natural-language task description:",
    description,
    '',
    continueSession === true
      ? 'Use `ops_save_task` with the description and runbook requirements; this task stores no replay seed. Requirements:'
      : 'Use `ops_save_task` with the successful trace before boundarySeq and the description. Requirements:',
    '- `id` uses lowercase letters, digits, and hyphens',
    '- Summarize `name` / `description` yourself',
    '- `instructions` is the runbook in AGENTS.md style, including execution steps, checks, and cautions',
    ...SAVE_PROMPT_TRIGGER_LINES,
    ...continuationLines,
    ...seedBoundaryLines,
    '- Set `naturalPrompt` to the user original natural-language task description (empty string when absent)',
    modeLine,
    ...seedLines,
    ...desired,
  ].join('\n')
}

/** Task asset fields the edit prompt needs. */
export interface EditableTaskPromptView {
  manifest: TaskManifest
  triggers: TaskTrigger[]
  agensMd: string
}

/** Render the prompt that asks the model to re-set an existing task. */
export function buildEditPrompt(
  task: EditableTaskPromptView,
  description: string,
  wants?: { icon?: string; color?: string; naturalPrompt?: string },
): string {
  const mode = task.manifest.taskMode ?? 'safe-copy'
  const desired = [
    wants?.icon === undefined ? null : `- \`icon\` must be ${JSON.stringify(wants.icon)}`,
    wants?.color === undefined ? null : `- \`color\` must be ${JSON.stringify(wants.color)}`,
    wants?.naturalPrompt === undefined || wants.naturalPrompt === ''
      ? null
      : `- \`naturalPrompt\` must be ${JSON.stringify(wants.naturalPrompt)}`,
  ].filter((line) => line !== null)
  return [
    `Reconfigure the ops task "${task.manifest.name}" (id: ${task.manifest.id}).`,
    '',
    "The user's new requirements in natural language:",
    description,
    '',
    'Current task information:',
    '```json',
    JSON.stringify({ manifest: task.manifest, triggers: task.triggers }, null, 2),
    '```',
    '',
    'Current runbook AGENTS.md:',
    '```markdown',
    task.agensMd,
    '```',
    '',
    'Update the task for the new requirements and save it by calling `ops_save_task`. Requirements:',
    `- \`id\` must remain ${JSON.stringify(task.manifest.id)}`,
    `- \`taskMode\` must remain ${JSON.stringify(mode)}; \`ops_save_task\` automatically preserves the existing replay seed, so do not rewrite the seed`,
    '- Preserve the existing `bindings` and replay target; `ops_save_task` keeps them on re-save.',
    ...(task.manifest.bindings?.continueSession === undefined
      ? []
      : ['- This task continues its source session: keep `replayMode` `"continue-session"` and do not add preset bindings.']),
    ...(desired.length === 0
      ? ['- Preserve `icon` / `color` / `naturalPrompt` unless the user explicitly asks to change them']
      : desired),
    '- Do not copy the original conversation; complete the edit in this new session and save it.',
  ].join('\n')
}
