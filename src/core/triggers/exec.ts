/**
 * Exec trigger edge detection.
 *
 * The exec source runs a command on a schedule and fires only when something
 * changed: the first observation, different stdout, or a different exit code.
 * Stderr changes alone do not fire (they are recorded for context). The host
 * owns command execution and scheduling; this class is pure state.
 */

export interface ExecObservation {
  stdout: string
  stderr: string
  exitCode: number
  /** ISO instant of the last observation, for persisted state. */
  observedAt: string
}

export class ExecEdgeDetector {
  private last?: ExecObservation

  /** Restore a previously persisted observation (without firing an edge). */
  constructor(state?: { stdout?: string; stderr?: string; exitCode?: number; observedAt?: string }) {
    if (
      state &&
      typeof state.stdout === 'string' &&
      typeof state.stderr === 'string' &&
      typeof state.exitCode === 'number'
    ) {
      this.last = {
        stdout: state.stdout,
        stderr: state.stderr,
        exitCode: state.exitCode,
        observedAt: state.observedAt ?? new Date(0).toISOString(),
      }
    }
  }

  /**
   * Record an observation. Returns true exactly on an edge: the first
   * observation, changed stdout, or changed exit code.
   */
  update(stdout: string, stderr: string, exitCode: number, now: Date): boolean {
    const edge =
      this.last === undefined ||
      this.last.stdout !== stdout ||
      this.last.exitCode !== exitCode
    this.last = { stdout, stderr, exitCode, observedAt: now.toISOString() }
    return edge
  }

  /** Current observation, e.g. for persisting to `TriggerState.exec`. */
  snapshot(): ExecObservation | undefined {
    return this.last ? { ...this.last } : undefined
  }
}
