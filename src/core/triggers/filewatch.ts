/**
 * File-watch log delta poller.
 *
 * The poller is intentionally IO-agnostic: callers inject `stat` and `read`
 * functions, so tests use fakes and the host wires real filesystem calls.
 * It tracks a byte offset per path, detects rotation (file shrank or inode
 * changed), and emits only complete new lines. Debounce and rate limiting
 * belong to the caller (`rate.ts`); the poller just reports deltas.
 */

export interface FileStatResult {
  size: number
  mtimeMs: number
  inode?: number
}

export interface FileWatchRead {
  /** Complete lines (ending at the last newline) from `start`. */
  text: string
  /** Raw bytes consumed for `text`; never a decoded character count. */
  bytes: number
}

export interface FileWatchIO {
  stat(path: string): Promise<FileStatResult>
  /** Read complete lines starting at byte offset `start`. */
  read(path: string, start: number): Promise<FileWatchRead>
}

export interface FileWatchPollResult {
  /** Complete new lines since the last poll, after the regex filter. */
  lines: string[]
  /** Byte offset to resume from on the next poll. */
  offset: number
  inode?: number
}

export interface FileWatchPollerOptions {
  /** Only emit lines matching this regex; the offset still advances. */
  regex?: string
  /** Resume position (from persisted trigger state). */
  initialOffset?: number
  initialInode?: number
}

export class FileWatchPoller {
  private readonly io: FileWatchIO
  private readonly filter?: RegExp
  private offset: number
  private inode?: number

  constructor(io: FileWatchIO, opts: FileWatchPollerOptions = {}) {
    this.io = io
    if (opts.regex !== undefined) {
      this.filter = new RegExp(opts.regex)
    }
    this.offset = opts.initialOffset ?? 0
    if (opts.initialInode !== undefined) {
      this.inode = opts.initialInode
    }
  }

  /** Current tracked offset, e.g. for persisting to trigger state. */
  get currentOffset(): number {
    return this.offset
  }

  /** Forget tracked position; the next poll reads from offset 0. */
  reset(): void {
    this.offset = 0
    delete this.inode
  }

  /**
   * Poll `path` once. Returns complete new lines (optionally regex-filtered)
   * and the new offset. A trailing partial line (no newline yet) is held
   * back until it completes. Rotation resets the offset to 0 before reading.
   */
  /** Adopt the current end of file without reading its historical content. */
  async prime(path: string): Promise<FileWatchPollResult> {
    const stat = await this.io.stat(path)
    this.offset = stat.size
    if (stat.inode !== undefined) this.inode = stat.inode
    return this.result([], this.offset)
  }

  async poll(path: string): Promise<FileWatchPollResult> {
    const stat = await this.io.stat(path)

    const rotated =
      stat.size < this.offset ||
      (stat.inode !== undefined && this.inode !== undefined && stat.inode !== this.inode)
    if (rotated) {
      this.offset = 0
    }
    if (stat.inode !== undefined) {
      this.inode = stat.inode
    }

    if (stat.size === this.offset) {
      return this.result([], this.offset)
    }

    const content = await this.io.read(path, this.offset)
    // The reader returns only complete lines; a trailing partial line is held
    // back until it completes.
    const complete = content.text.split('\n').slice(0, -1)
    this.offset += content.bytes

    const lines = this.filter ? complete.filter((line) => this.filter!.test(line)) : complete
    return this.result(lines, this.offset)
  }

  private result(lines: string[], offset: number): FileWatchPollResult {
    const result: FileWatchPollResult = { lines, offset }
    if (this.inode !== undefined) {
      result.inode = this.inode
    }
    return result
  }
}
