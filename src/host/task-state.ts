/**
 * Owns the plugin's two JSON state files. Domain code mutates the returned
 * objects and calls the matching save method; loading and atomic persistence
 * stay in one place instead of being scattered across host handlers.
 */

import type { RegistryState, RunMapState, TaskRegistryRecord } from '../core/contract.ts'
import {
  loadRegistryState,
  loadRunMapState,
  saveRegistryState,
  saveRunMapState,
} from '../core/storage.ts'

export class TaskStateStore {
  private registryState: RegistryState
  private runMapState: RunMapState

  constructor(private readonly root: string) {
    this.registryState = loadRegistryState(root)
    this.runMapState = loadRunMapState(root)
  }

  get registry(): RegistryState {
    return this.registryState
  }

  get runMap(): RunMapState {
    return this.runMapState
  }

  reloadRegistry(): void {
    this.registryState = loadRegistryState(this.root)
  }

  reloadRuns(): void {
    this.runMapState = loadRunMapState(this.root)
  }

  saveRegistry(): void {
    saveRegistryState(this.root, this.registryState)
  }

  saveRuns(): void {
    saveRunMapState(this.root, this.runMapState)
  }

  task(taskId: string): TaskRegistryRecord | undefined {
    return this.registryState.tasks[taskId]
  }

  tasks(): TaskRegistryRecord[] {
    return Object.values(this.registryState.tasks)
  }
}
