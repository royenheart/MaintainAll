/**
 * Engine-facing load/save helpers for `storages/trigger-state.json`.
 *
 * Thin wrappers over the core storage functions that pin the `TriggerState`
 * contract from `src/core/contract.ts` and guarantee all default sections
 * exist, so the trigger engine never deals with partially populated state.
 */

import type { TriggerState } from '../core/contract.ts'
import { loadTriggerState, saveTriggerState } from '../core/storage.ts'

/** Fresh, empty trigger state with every section present. */
export function emptyTriggerState(): TriggerState {
  return { version: 2, triggers: {}, schedules: {}, filewatch: {}, exec: {} }
}

/**
 * Load `storages/trigger-state.json` under `root`, falling back to
 * {@link emptyTriggerState} when the file is absent and filling any missing
 * sections with defaults.
 */
export function loadTriggerStateFile(root: string): TriggerState {
  const state = loadTriggerState(root)
  return { ...emptyTriggerState(), ...state }
}

/** Atomically persist trigger state under `root`. */
export function saveTriggerStateFile(root: string, state: TriggerState): void {
  saveTriggerState(root, state)
}
