/**
 * Owns the trigger engine and its host listeners. The host service supplies
 * task discovery and replay dispatch; this class owns start/stop, reload,
 * webhook admission, and the derived trigger-id index.
 */

import { exec } from 'node:child_process'
import { TriggerEngine, type EngineTask } from '../engine/trigger-engine.ts'
import { startDockerListener, startJournaldListener } from '../engine/listeners.ts'
import type { TriggerEvent } from '../core/contract.ts'

interface RuntimeLogger {
  warn(message: string, ...args: unknown[]): void
}

export class TriggerRuntime {
  private engine?: TriggerEngine
  private stopDocker?: () => Promise<void>
  private stopJournald?: () => Promise<void>

  constructor(
    private readonly root: string,
    private readonly tasks: () => EngineTask[],
    private readonly dispatch: (taskId: string, event: TriggerEvent) => Promise<void>,
    private readonly logger: RuntimeLogger,
    private readonly onEngineError: (error: Error) => void,
  ) {}

  get active(): boolean {
    return this.engine !== undefined
  }

  async start(): Promise<void> {
    this.engine = new TriggerEngine({
      root: this.root,
      tasks: this.tasks,
      exec: (command) => new Promise((resolve) => {
        exec(command, {
          cwd: this.root,
          timeout: 60_000,
          killSignal: 'SIGKILL',
          maxBuffer: 1024 * 1024,
          windowsHide: true,
        }, (error, stdout, stderr) => {
          let exitCode = 0
          if (error !== null) {
            const code = (error as { code?: unknown }).code
            exitCode = error.killed === true && error.signal === 'SIGKILL'
              ? 124
              : typeof code === 'number' ? code : code === 'ENOENT' ? 127 : 1
          }
          resolve({ stdout: String(stdout ?? ''), stderr: String(stderr ?? ''), exitCode })
        })
      }),
      onError: this.onEngineError,
      dispatch: this.dispatch,
    })
    await this.engine.start()
    this.stopDocker = startDockerListener(this.engine, {
      onError: (error) => this.logger.warn('maintainall: docker listener: %s', error.message),
    })
    this.stopJournald = startJournaldListener(this.engine, {
      onError: (error) => this.logger.warn('maintainall: journald listener: %s', error.message),
    })
  }

  async stop(): Promise<void> {
    const engineStopping = this.engine?.stop()
    try {
      await Promise.all([this.stopJournald?.(), this.stopDocker?.()])
    } finally {
      this.stopJournald = undefined
      this.stopDocker = undefined
      try {
        await engineStopping
      } finally {
        this.engine = undefined
      }
    }
  }

  reload(): void {
    this.engine?.reload()
  }

  forget(triggerIds: readonly string[]): void {
    if (triggerIds.length > 0) this.engine?.forgetTriggers(triggerIds)
  }

  triggerIdsForTask(taskId: string): string[] {
    return this.engine?.triggerIdsForTask(taskId) ?? []
  }

  webhook(
    triggerId: string,
    path: string,
    headers: Record<string, string | string[] | undefined>,
    body: string,
  ): Promise<boolean> {
    return this.engine === undefined
      ? Promise.resolve(false)
      : this.engine.onWebhookRequest(triggerId, path, headers, body)
  }
}
