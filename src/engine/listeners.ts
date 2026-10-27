/**
 * Long-running source listeners for docker and journald triggers.
 *
 * These spawn the native CLIs (`docker events`, `journalctl -f`) and feed
 * their stdout lines into the {@link TriggerEngine}. Webhook routing is not
 * covered here — the host service registers one webhook route and calls
 * `engine.onWebhookRequest` directly.
 */

import { spawn, type ChildProcess } from 'node:child_process'
import { createInterface } from 'node:readline'
import type { TriggerEngine } from './trigger-engine.ts'

/** How long a listener child may take to exit after SIGTERM before SIGKILL. */
const CHILD_STOP_TIMEOUT_MS = 2000

/**
 * Split a UTF-8 stream into lines and feed each non-empty line to `onLine`.
 * Returns a closer so teardown releases the readline interface even when the
 * child process exits slowly or ignores SIGTERM.
 */
function pumpLines(
  stream: NodeJS.ReadableStream,
  onLine: (line: string) => void,
  onError: (error: Error) => void,
): () => void {
  const rl = createInterface({ input: stream })
  rl.on('line', (line) => {
    if (line.trim() !== '') onLine(line)
  })
  rl.on('error', onError)
  return () => { rl.close() }
}

/**
 * Close a listener's line readers, ask the child to stop, and wait briefly.
 * A child that ignores SIGTERM is killed after {@link CHILD_STOP_TIMEOUT_MS}.
 */
async function stopChild(child: ChildProcess, closers: readonly (() => void)[]): Promise<void> {
  for (const close of closers) close()
  if (child.exitCode !== null || child.signalCode !== null) return

  await new Promise<void>((resolve) => {
    let settled = false
    let timer: NodeJS.Timeout | undefined
    const finish = (): void => {
      if (settled) return
      settled = true
      if (timer !== undefined) clearTimeout(timer)
      child.removeListener('exit', finish)
      resolve()
    }
    timer = setTimeout(() => {
      if (child.exitCode === null && child.signalCode === null) {
        try {
          child.kill('SIGKILL')
        } catch {
          // The process may have exited between the check and the signal.
        }
      }
      finish()
    }, CHILD_STOP_TIMEOUT_MS)
    timer.unref()
    child.once('exit', finish)
    try {
      if (!child.kill('SIGTERM')) finish()
    } catch {
      finish()
    }
  })
}

/** Start `docker events --format '{{json .}}'` and feed parsed lines. */
export function startDockerListener(
  engine: TriggerEngine,
  opts: { dockerPath?: string; onError?: (error: Error) => void } = {},
): () => Promise<void> {
  const child: ChildProcess = spawn(opts.dockerPath ?? 'docker', ['events', '--format', '{{json .}}'], {
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  const onError = opts.onError ?? ((error: Error) => { console.error('[maintainall] source listener:', error) })
  let stopping = false
  child.on('error', onError)
  child.on('exit', (code, signal) => {
    if (!stopping) onError(new Error(`docker events exited (code ${String(code)}, signal ${String(signal)})`))
  })
  const closers: Array<() => void> = []
  if (child.stdout !== null) closers.push(pumpLines(child.stdout, (line) => { void engine.onDockerEvent(line).catch(onError) }, onError))
  if (child.stderr !== null) closers.push(pumpLines(child.stderr, () => {}, onError))
  return async () => { stopping = true; await stopChild(child, closers) }
}

/** Start `journalctl -f -o json` and feed parsed lines. */
export function startJournaldListener(
  engine: TriggerEngine,
  opts: { journalctlPath?: string; onError?: (error: Error) => void } = {},
): () => Promise<void> {
  const child: ChildProcess = spawn(opts.journalctlPath ?? 'journalctl', ['-f', '-o', 'json'], {
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  const onError = opts.onError ?? ((error: Error) => { console.error('[maintainall] source listener:', error) })
  let stopping = false
  child.on('error', onError)
  child.on('exit', (code, signal) => {
    if (!stopping) onError(new Error(`journalctl exited (code ${String(code)}, signal ${String(signal)})`))
  })
  const closers: Array<() => void> = []
  if (child.stdout !== null) closers.push(pumpLines(child.stdout, (line) => { void engine.onJournaldLine(line).catch(onError) }, onError))
  if (child.stderr !== null) closers.push(pumpLines(child.stderr, () => {}, onError))
  return async () => { stopping = true; await stopChild(child, closers) }
}
