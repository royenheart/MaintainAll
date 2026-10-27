/**
 * Compact replay seed extraction and rewrite.
 * Pure logic over {@link SeedEvent} / {@link TaskSeed}; no dsh imports.
 */

import { posix, win32 } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import type { SeedEvent, TaskSeed } from './contract.ts'

/** Replay seed and command scan limits. Keep replay memory and CPU bounded. */
export const MAX_SEED_BYTES = 16 * 1024 * 1024
export const MAX_CWD_BYTES = 4096
export const MAX_EVENT_COUNT = 100_000
export const MAX_STRING_SCAN_CHARS = 2_000_000
export const MAX_ARGUMENT_DEPTH = 64

/** True for a UNC share root, including extended/device namespace spellings. */
function isUncShareRoot(value: string): boolean {
  const normalized = value.replace(/\//g, '\\').replace(/\\+$/, '')
  return /^\\\\\?\\UNC\\[^\\]+\\[^\\]+$/i.test(normalized)
    || /^\\\\\.\\UNC\\[^\\]+\\[^\\]+$/i.test(normalized)
    || (/^\\\\[^\\]+\\[^\\]+$/i.test(normalized) && !/^\\\\[?.]\\/i.test(normalized))
}

/** Validate an absolute seed cwd and its byte budget. */
export function validateSeedCwd(cwd: unknown): string {
  if (typeof cwd !== 'string' || cwd.trim() === '') throw new Error('invalid seed: cwd must be non-empty')
  if (/[\0\r\n]/.test(cwd)) throw new Error('invalid seed: cwd contains a control character')
  if (Buffer.byteLength(cwd, 'utf8') > MAX_CWD_BYTES) throw new Error('invalid seed: cwd is too long')
  const absolute = cwd.startsWith('/') || /^[A-Za-z]:[\\/]/.test(cwd) || cwd.startsWith('\\\\')
  if (!absolute) throw new Error('invalid seed: cwd must be absolute')
  const windows = isWindowsCwd(cwd)
  const normalized = windows ? win32.normalize(cwd) : posix.normalize(cwd)
  if (normalized === '/' || normalized === '\\') {
    throw new Error('invalid seed: cwd must not be a filesystem root')
  }
  if (windows) {
    const root = win32.parse(cwd).root
    if (root !== '' && win32.normalize(root) === normalized) {
      throw new Error('invalid seed: cwd must not be a filesystem root')
    }
    if (isUncShareRoot(normalized)) {
      throw new Error('invalid seed: cwd must not be a filesystem root')
    }
  }
  return cwd
}

/** Validate a parsed seed against event-count and byte budgets. */
export function validateSeedBounds(seed: TaskSeed, seedBytes?: number): void {
  validateSeedCwd(seed.cwd)
  if (seed.events.length > MAX_EVENT_COUNT) {
    throw new Error(`invalid seed: too many events (${seed.events.length} > ${MAX_EVENT_COUNT})`)
  }
  if (seedBytes !== undefined && seedBytes > MAX_SEED_BYTES) {
    throw new Error(`invalid seed: seed is too large (${seedBytes} > ${MAX_SEED_BYTES} bytes)`)
  }
}

/** Durable event types retained in `seed/session.jsonl`. */
export const DURABLE_EVENT_TYPES: ReadonlySet<string> = new Set([
  'turn/start',
  'step/start',
  'user/message',
  'assistant/message',
  'tool/call',
  'tool/result',
  'step/end',
  'turn/end',
])

/**
 * Validate that `events` have contiguous, strictly increasing `seq`
 * (each event's seq equals the previous event's seq + 1).
 * Throws on the first gap, duplicate, or regression.
 */
function assertContiguousSeq(events: SeedEvent[]): void {
  for (let i = 1; i < events.length; i++) {
    const prev = events[i - 1].seq
    const seq = events[i].seq
    if (seq !== prev + 1) {
      throw new Error(
        `invalid seed: seq must be contiguous, got seq ${seq} after seq ${prev} (index ${i})`,
      )
    }
  }
}

/**
 * Extract the durable seed prefix of a session event stream:
 * keep only durable event types with `seq <= boundarySeq`, preserving order.
 * The input sequence must be contiguous; a gap throws.
 */
export function extractSeedEvents(events: SeedEvent[], boundarySeq: number): SeedEvent[] {
  const prefix = events.filter((event) => event.seq <= boundarySeq)
  assertContiguousSeq(prefix)
  // A constructor seed must end at a durable turn boundary. A boundary inside
  // an open turn would leave an assistant tool call without its result, which
  // providers reject on the first replay request.
  let end = -1
  for (let index = prefix.length - 1; index >= 0; index--) {
    if (prefix[index]!.type === 'turn/end') {
      end = index
      break
    }
  }
  if (end < 0) return []
  return prefix.filter(
    (event) => event.seq <= prefix[end]!.seq && DURABLE_EVENT_TYPES.has(event.type),
  )
}

/**
 * Deterministic compaction for `taskMode: 'compact'`: strip reasoning blocks
 * from `assistant/message` content and drop assistant messages left empty.
 * Tool calls, tool results, and user messages are preserved.
 */
export function compactSeedEvents(events: SeedEvent[]): SeedEvent[] {
  return events.flatMap((event) => {
    if (event.type !== 'assistant/message' || typeof event.data !== 'object' || event.data === null) {
      return [event]
    }
    const data = event.data as { message?: { content?: unknown[] } }
    const content = Array.isArray(data.message?.content) ? data.message.content : []
    const kept = content.filter((block) => {
      if (typeof block !== 'object' || block === null) return true
      return (block as { type?: string }).type !== 'reasoning'
    })
    if (kept.length === 0) return []
    return [{ ...event, data: { ...data, message: { ...data.message, content: kept }, stream: [] } }]
  })
}

const LEFT_DELIMITERS: ReadonlySet<string> = new Set([
  '=', '<', '>', '(', '[', '{', ',', ';', '|', '&',
])
const RIGHT_DELIMITERS: ReadonlySet<string> = new Set([
  '"', "'", '`', '=', ':', ';', ')', ']', '}', '>', '|', '&', '<', '?', '#',
  '!', ',', '/',
])

type QuoteMode = 'outside' | 'single' | 'double'

interface ShellContext {
  mode: QuoteMode
  /** A `$(...)` or backtick command-substitution context. */
  command: boolean
  close?: ')' | '`'
  parenDepth: number
  nested?: boolean
  /** `$'...'` uses ANSI-C backslash escaping inside single quotes. */
  ansiC?: boolean
}

interface ParameterFrame {
  bracketDepth: number
  /** Whether the expansion began inside double quotes. */
  quoted?: boolean
  /** Index just past the default/alternate operator, when seen. */
  opEnd?: number
}

function isWhitespace(ch: string): boolean {
  const code = ch.charCodeAt(0)
  return code === 0x20 || code === 0x09 || code === 0x0a || code === 0x0d
    || code === 0x0b || code === 0x0c || code === 0xa0 || code === 0x1680
    || (code >= 0x2000 && code <= 0x200a) || code === 0x2028 || code === 0x2029
    || code === 0x202f || code === 0x205f || code === 0x3000 || code === 0xfeff
}

function isPathBoundaryChar(ch: string): boolean {
  return isWhitespace(ch) || LEFT_DELIMITERS.has(ch)
    || ch === ':' || ch === '-' || ch === '+'
}

function trimTrailingSeparators(value: string): string {
  let end = value.length
  while (end > 0) {
    const ch = value[end - 1]
    if (ch !== '/' && ch !== '\\') break
    end--
  }
  return value.slice(0, end)
}

function isAsciiLetter(ch: string): boolean {
  const code = ch.charCodeAt(0)
  return (code >= 65 && code <= 90) || (code >= 97 && code <= 122)
}

function isDriveRoot(value: string): boolean {
  return value.length === 2 && value[1] === ':' && isAsciiLetter(value[0]!)
}

/** True when the quote is a real `$'`/`$"` prefix, not escaped or part of `$$`. */
function isDollarQuote(text: string, quoteIndex: number): boolean {
  if (quoteIndex < 1 || text[quoteIndex - 1] !== '$') return false
  let dollars = 0
  for (let i = quoteIndex - 1; i >= 0 && text[i] === '$'; i--) {
    let backslashes = 0
    for (let j = i - 1; j >= 0 && text[j] === '\\'; j--) backslashes++
    if (backslashes % 2 === 1) break
    dollars++
  }
  return dollars % 2 === 1
}

/** O(1) lookahead for a nested different quote before the enclosing quote. */
class QuoteLookahead {
  private readonly nextSingle: Int32Array
  private readonly nextDouble: Int32Array

  constructor(text: string) {
    const length = text.length
    const escaped = new Uint8Array(length)
    let escapedNext = false
    for (let i = 0; i < length; i++) {
      if (escapedNext) {
        escaped[i] = 1
        escapedNext = false
      } else if (text[i] === '\\') {
        escapedNext = true
      }
    }
    this.nextSingle = new Int32Array(length + 1)
    this.nextDouble = new Int32Array(length + 1)
    let single = length
    let double = length
    for (let i = length - 1; i >= 0; i--) {
      if (escaped[i] === 0 && text[i] === "'") single = i
      if (escaped[i] === 0 && text[i] === '"') double = i
      this.nextSingle[i] = single
      this.nextDouble[i] = double
    }
  }

  hasNested(start: number, quote: "'" | '"', enclosing: "'" | '"'): boolean {
    const next = quote === "'" ? this.nextSingle : this.nextDouble
    const stop = enclosing === "'" ? this.nextSingle : this.nextDouble
    const quoteAt = next[start]
    const stopAt = stop[start]
    return quoteAt < next.length && (stopAt >= next.length || quoteAt < stopAt)
  }
}

/** True when the path is a local file URI target, not a remote authority. */
function isLocalFilePrefix(text: string, index: number, platform: 'posix' | 'windows'): boolean {
  const prefix = text.slice(Math.max(0, index - 8), index).toLowerCase()
  if (platform === 'posix') {
    // file:///path: the third slash is the local path root. file://host/path
    // stays remote; file:/path is handled by the colon branch.
    return prefix.endsWith('file://')
  }
  // Windows local forms, including the WHATWG-normalized file://C:/....
  return prefix.endsWith('file:/') || prefix.endsWith('file:///') || prefix.endsWith('file://')
}

/** True when the seed cwd uses Windows drive or UNC syntax. */
function isWindowsCwd(base: string): boolean {
  if (base.startsWith('\\\\')) return true
  return base.length >= 3 && isAsciiLetter(base[0]!) && base[1] === ':'
    && (base[2] === '/' || base[2] === '\\')
}

/** Lexical state carried across one linear pass over the text. */
class PathScannerState {
  private readonly contexts: ShellContext[] = [{ mode: 'outside', command: false, parenDepth: 0 }]
  private readonly lookahead: QuoteLookahead
  escaped = false
  /** Last quote that changed the quote mode, if any. */
  lastQuote: { index: number; opening: boolean } | undefined
  /** Last backtick that opened or closed a command substitution. */
  lastBacktick: { index: number; opening: boolean } | undefined
  readonly params: ParameterFrame[] = []

  constructor(text: string) {
    this.lookahead = new QuoteLookahead(text)
  }

  private get top(): ShellContext {
    return this.contexts[this.contexts.length - 1]!
  }

  get mode(): QuoteMode {
    return this.top.mode
  }

  get parameterQuoted(): boolean {
    return this.params[this.params.length - 1]?.quoted === true
  }

  consume(ch: string, index: number, next: string | undefined, text: string): void {
    if (this.escaped) {
      this.escaped = false
      return
    }
    if (ch === '\\' && (this.mode !== 'single' || this.top.ansiC === true)) {
      this.escaped = true
      return
    }

    const top = this.top
    if (top.command && top.mode === 'outside') {
      if (ch === ')' && top.close === ')' && top.parenDepth === 0) {
        this.contexts.pop()
        return
      }
      if (ch === ')' && top.close === ')' && top.parenDepth > 0) {
        top.parenDepth--
        return
      }
      if (ch === '`' && top.close === '`') {
        this.contexts.pop()
        this.lastBacktick = { index, opening: false }
        return
      }
      if (ch === '(') {
        if (text[index - 1] === '$') {
          this.contexts.push({ mode: 'outside', command: true, close: ')', parenDepth: 0 })
        } else if (top.close === ')') {
          top.parenDepth++
        }
        return
      }
      if (ch === '`') {
        this.contexts.push({ mode: 'outside', command: true, close: '`', parenDepth: 0 })
        this.lastBacktick = { index, opening: true }
        return
      }
      if (ch === '$' && next === '{') {
        this.params.push({ bracketDepth: 0, quoted: this.mode === 'double' })
        return
      }
    } else if (top.command && top.mode !== 'single') {
      if (ch === '(' && text[index - 1] === '$') {
        this.contexts.push({ mode: 'outside', command: true, close: ')', parenDepth: 0 })
        return
      }
      if (ch === '`') {
        this.contexts.push({ mode: 'outside', command: true, close: '`', parenDepth: 0 })
        this.lastBacktick = { index, opening: true }
        return
      }
      if (ch === '$' && next === '{') {
        this.params.push({ bracketDepth: 0, quoted: this.mode === 'double' })
        return
      }
    } else if (!top.command && top.mode !== 'single') {
      if (ch === '(' && text[index - 1] === '$') {
        this.contexts.push({ mode: 'outside', command: true, close: ')', parenDepth: 0 })
        return
      }
      if (ch === '`') {
        this.contexts.push({ mode: 'outside', command: true, close: '`', parenDepth: 0 })
        this.lastBacktick = { index, opening: true }
        return
      }
      if (ch === '$' && next === '{') {
        this.params.push({ bracketDepth: 0, quoted: this.mode === 'double' })
        return
      }
    }

    // Parameter-expansion brackets/operators are active outside single
    // quotes and inside double quotes or command substitutions.
    if (this.mode !== 'single' && this.params.length > 0) {
      const frame = this.params[this.params.length - 1]!
      if (ch === '}') {
        this.params.pop()
        return
      }
      if (ch === '[') {
        frame.bracketDepth++
        return
      }
      if (ch === ']') {
        if (frame.bracketDepth > 0) frame.bracketDepth--
        return
      }
      if (frame.bracketDepth === 0 && frame.opEnd === undefined) {
        if (ch === ':' && (next === '-' || next === '=' || next === '+')) {
          frame.opEnd = index + 2
        } else if (ch === '-' || ch === '=' || ch === '+') {
          frame.opEnd = index + 1
        }
      }
    }

    // Quote state. `$'...'` and `$"..."` open their quoted form directly.
    if (this.mode === 'outside') {
      const dollarQuote = (ch === "'" || ch === '"') && isDollarQuote(text, index)
      if (dollarQuote && ch === "'") {
        this.top.mode = 'single'
        this.top.ansiC = true
        this.lastQuote = { index, opening: true }
      } else if (dollarQuote && ch === '"') {
        this.top.mode = 'double'
        this.lastQuote = { index, opening: true }
      } else if (ch === "'") {
        this.top.mode = 'single'
        this.top.ansiC = false
        this.lastQuote = { index, opening: true }
      } else if (ch === '"') {
        this.top.mode = 'double'
        this.lastQuote = { index, opening: true }
      }
      return
    }

    if (this.mode === 'single') {
      if (ch === "'") {
        if (this.top.nested === true) this.contexts.pop()
        else this.top.mode = 'outside'
        this.top.ansiC = false
        this.lastQuote = { index, opening: false }
      } else if (this.top.ansiC !== true && ch === '"' && this.lookahead.hasNested(index + 1, '"', "'")) {
        this.contexts.push({ mode: 'double', command: false, parenDepth: 0, nested: true })
        this.lastQuote = { index, opening: true }
      }
      return
    }

    // double
    if (ch === '"') {
      if (this.top.nested === true) this.contexts.pop()
      else this.top.mode = 'outside'
      this.lastQuote = { index, opening: false }
    } else if (ch === "'" && this.lookahead.hasNested(index + 1, "'", '"')) {
      this.contexts.push({ mode: 'single', command: false, parenDepth: 0, nested: true })
      this.lastQuote = { index, opening: true }
    }
  }
}

/** True for a real local `file:` scheme colon at a word/URI boundary. */
function isPosixSchemeColon(text: string, colonIndex: number): boolean {
  const schemeStart = colonIndex - 4
  if (schemeStart < 0 || text.slice(schemeStart, colonIndex).toLowerCase() !== 'file') return false
  if (schemeStart === 0) return true
  const before = text[schemeStart - 1]!
  return isPathBoundaryChar(before) || before === '"' || before === "'"
    || before === '`' || before === '$'
}

function isLeftBoundary(
  text: string,
  index: number,
  platform: 'posix' | 'windows',
  state: PathScannerState,
): boolean {
  if (index === 0) return true
  const prev = text[index - 1]!
  if (prev === '"' || prev === "'") {
    const quote = state.lastQuote
    if (quote === undefined || quote.index !== index - 1) return false
    if (!quote.opening) return false
    if (index - 2 < 0) return true
    const before = text[index - 2]!
    if (before === '$') {
      if (index - 3 < 0) return true
      const beforeDollar = text[index - 3]!
      if (beforeDollar === '`') {
        return state.lastBacktick?.index === index - 3 && state.lastBacktick.opening === true
      }
      return isPathBoundaryChar(beforeDollar)
    }
    if (before === '`') {
      return state.lastBacktick?.index === index - 2 && state.lastBacktick.opening === true
    }
    if (before === ':') {
      if (platform === 'windows') return true
      return isPosixSchemeColon(text, index - 2)
    }
    return isPathBoundaryChar(before)
  }
  if (prev === '`') {
    return state.lastBacktick?.index === index - 1 && state.lastBacktick.opening === true
  }
  if (prev === '/') return isLocalFilePrefix(text, index, platform)
  if (prev === ':') {
    if (platform === 'windows') return true
    // POSIX colon lists and Windows drive paths are indistinguishable. Do not
    // guess: only a local file-scheme colon is recognized.
    return isPosixSchemeColon(text, index - 1)
  }
  if (prev === '-' || prev === '+') {
    const frame = state.params[state.params.length - 1]
    return frame?.opEnd === index
  }
  if (prev === ']' || prev === '}' || prev === '~' || prev === '$' || prev === '#'
    || prev === '%' || prev === '*' || prev === '?' || prev === '!' || prev === ')'
    || prev === '\\') return false
  return isWhitespace(prev) || LEFT_DELIMITERS.has(prev)
}

function isFileUriPathBoundary(ch: string, mode: QuoteMode, parameterQuoted: boolean): boolean {
  if (mode === 'single') return ch === '\'' || ch === '/' || ch === '?' || ch === '#'
  if (mode === 'double') {
    return ch === '"' || ch === '/' || ch === '?' || ch === '#' || (parameterQuoted && ch === '}')
  }
  if (ch === '/' || ch === '?' || ch === '#' || ch === ')' || ch === ']' || ch === '}') return true
  if (ch === '>' || ch === '<' || ch === '|' || ch === '&' || ch === ';') return true
  return isWhitespace(ch) || ch === '"' || ch === "'" || ch === '`'
}

function isRightBoundary(
  text: string,
  index: number,
  platform: 'posix' | 'windows',
  fileUriPath = false,
  mode: QuoteMode = 'outside',
  parameterQuoted = false,
): boolean {
  if (index >= text.length) return true
  const ch = text[index]!
  if (ch === '\\') return platform === 'windows'
  if (fileUriPath) return isFileUriPathBoundary(ch, mode, parameterQuoted)
  return isWhitespace(ch) || RIGHT_DELIMITERS.has(ch)
}

/** True when a path starts at a local file-scheme URI path position. */
function isFileUriPathStart(text: string, index: number): boolean {
  for (const scheme of ['file:///', 'file://', 'file:/', 'file:']) {
    const start = index - scheme.length
    if (start < 0 || text.slice(start, index).toLowerCase() !== scheme) continue
    if (start === 0) return true
    const before = text[start - 1]!
    return isPathBoundaryChar(before) || before === '"' || before === "'"
      || before === '`' || before === '$'
  }
  return false
}

/** Encode a URI path without turning reserved filename characters into delimiters. */
function encodeUriPath(value: string, preserveDriveColon = false, preserveAllColons = false): string | undefined {
  try {
    return value.split('/').map((segment, index) => {
      const encoded = encodeURIComponent(segment)
      if (preserveAllColons || (preserveDriveColon && index === 0)) return encoded.replace(/%3A/gi, ':')
      return encoded
    }).join('/')
  } catch {
    return undefined
  }
}

/**
 * Replace cwd occurrences only where the cwd is a complete path prefix. One
 * linear lexer pass tracks quote/escape state, parameter-expansion defaults,
 * and local file URIs; it never re-scans a prefix and never uses a dynamic
 * RegExp.
 */
function replacePathOccurrences(text: string, from: string, to: string, shell = false): string {
  const base = trimTrailingSeparators(from)
  if (base === '' || base === '/' || base === '\\' || isDriveRoot(base)) return text
  const platform: 'posix' | 'windows' = isWindowsCwd(base) ? 'windows' : 'posix'
  const variants: Array<{ match: string; replacement: string; fileUriOnly?: boolean; encoded?: boolean }> = [
    { match: base, replacement: to },
  ]
  if (platform === 'windows') {
    const forward = base.split('\\').join('/')
    if (forward !== base) variants.push({ match: forward, replacement: to })
    const native = base.split('/').join('\\')
    if (native !== base) variants.push({ match: native, replacement: to.split('/').join('\\') })
    const encoded = encodeUriPath(forward, true)
    const encodedTarget = encoded === undefined ? undefined : encodeUriPath(to.split('\\').join('/'), true)
    if (encoded !== undefined && encodedTarget !== undefined && encoded !== forward) {
      variants.push({ match: encoded, replacement: encodedTarget, fileUriOnly: true, encoded: true })
    }
  } else {
    for (const preserveColons of [false, true]) {
      const encoded = encodeUriPath(base, false, preserveColons)
      const encodedTarget = encoded === undefined ? undefined : encodeUriPath(to, false, preserveColons)
      if (encoded !== undefined && encodedTarget !== undefined && encoded !== base
        && !variants.some((variant) => variant.match === encoded)) {
        variants.push({ match: encoded, replacement: encodedTarget, fileUriOnly: true, encoded: true })
      }
    }
  }

  if (text.length > MAX_STRING_SCAN_CHARS) return text
  const haystack = platform === 'windows' ? text.toLowerCase() : text
  if (!variants.some((variant) => haystack.includes(platform === 'windows' ? variant.match.toLowerCase() : variant.match))) return text
  const state = new PathScannerState(text)
  let output = ''
  let index = 0
  while (index < text.length) {
    let match = ''
    let replacement = to
    for (const variant of variants) {
      if (variant.fileUriOnly === true && !isFileUriPathStart(text, index)) continue
      const window = text.slice(index, index + variant.match.length)
      const candidate = platform === 'windows' ? variant.match.toLowerCase() : variant.match
      if ((platform === 'windows' ? window.toLowerCase() : window) === candidate) {
        match = variant.match
        replacement = variant.replacement
        break
      }
    }
    const fileUriPath = isFileUriPathStart(text, index)
    if (match !== '' && isLeftBoundary(text, index, platform, state)
      && isRightBoundary(text, index + match.length, platform, fileUriPath, state.mode, state.parameterQuoted)) {
      if (fileUriPath && variants.find((variant) => variant.match === match)?.encoded !== true) {
        const target = platform === 'windows' ? replacement.split('\\').join('/') : replacement
        replacement = encodeUriPath(target, platform === 'windows') ?? replacement
      }
      if (shell && (platform === 'windows' ? SHELL_UNSAFE_WINDOWS : SHELL_UNSAFE_POSIX).test(replacement)) {
        throw new Error(
          'cannot rewrite executable shell arguments: replay cwd contains shell metacharacters',
        )
      }
      output += replacement
      index += match.length
      if ((replacement.endsWith('/') || replacement.endsWith('\\')) && text[index] === replacement.at(-1)) index++
      continue
    }
    const ch = text[index]!
    output += ch
    state.consume(ch, index, text[index + 1], text)
    index++
  }
  return output
}

const SHELL_ARGUMENT_KEYS: ReadonlySet<string> = new Set([
  'command', 'cmd', 'command_line', 'commandline', 'script', 'commands',
])
const DATA_ARGUMENT_KEYS: ReadonlySet<string> = new Set([
  'content', 'file_text', 'text', 'body', 'data', 'old_string', 'new_string',
  'old_str', 'new_str', 'pattern', 'include', 'regex', 'query', 'sql',
  'description', 'title', 'name', 'reason', 'justification', 'prompt', 'message', 'id',
])
const TOOL_BLOCK_KIND = /^tool[-_](call|use|result)$/

interface RewriteContext {
  from: string
  to: string
  platform: 'posix' | 'windows'
}

interface WalkResult {
  value: unknown
  changed: boolean
}

function normalizedPath(value: string, platform: 'posix' | 'windows'): string {
  if (platform === 'posix') return value
  return value.replace(/\\/g, '/').toLowerCase()
}

/** Return the length of the old-cwd prefix when `value` is that path or below it. */
function pathPrefixLength(value: string, context: RewriteContext): number | undefined {
  const base = trimTrailingSeparators(context.from)
  if (base === '' || base === '/' || base === '\\' || isDriveRoot(base)) return undefined
  const normalizedBase = normalizedPath(base, context.platform)
  const normalizedValue = normalizedPath(value, context.platform)
  if (normalizedValue === normalizedBase) return base.length
  if (normalizedValue.startsWith(`${normalizedBase}/`)) return base.length
  return undefined
}

function appendPathSuffix(target: string, suffix: string): string {
  if (suffix === '') return target
  const separator = target.endsWith('/') ? '/' : target.endsWith('\\') ? '\\' : ''
  if (separator !== '' && suffix.startsWith(separator)) return `${target}${suffix.slice(1)}`
  return `${target}${suffix}`
}

function rewritePlainPath(value: string, context: RewriteContext): string | undefined {
  const length = pathPrefixLength(value, context)
  if (length === undefined) return undefined
  return appendPathSuffix(context.to, value.slice(length))
}

/** Rewrite a whole local file URI, preserving query and fragment. */
function rewriteFileUri(value: string, context: RewriteContext): string | undefined {
  if (!/^file:/i.test(value)) return undefined
  let url: URL
  try {
    url = new URL(value)
  } catch {
    return undefined
  }
  if (url.protocol !== 'file:') return undefined
  if (url.hostname !== '' && url.hostname.toLowerCase() !== 'localhost') return undefined
  let path: string
  try {
    path = fileURLToPath(url, { windows: context.platform === 'windows' })
  } catch {
    return undefined
  }
  const length = pathPrefixLength(path, context)
  if (length === undefined) return undefined
  const target = appendPathSuffix(context.to, path.slice(length))
  try {
    return `${pathToFileURL(target).href}${url.search}${url.hash}`
  } catch {
    return undefined
  }
}

const SHELL_UNSAFE_POSIX = /[\s&|;<>()$`"'*?[\]{}!#~]/
const SHELL_UNSAFE_WINDOWS = /[\s&|;<>()$`"'*?[\]{}!#~%^]/

function rewriteArgumentString(value: string, key: string, context: RewriteContext): string {
  if (DATA_ARGUMENT_KEYS.has(key)) return value
  if (SHELL_ARGUMENT_KEYS.has(key)) {
    return replacePathOccurrences(value, context.from, context.to, true)
  }
  return rewriteFileUri(value, context) ?? rewritePlainPath(value, context) ?? value
}

function rewriteArgumentValue(
  value: unknown,
  key: string,
  context: RewriteContext,
  depth: number,
): WalkResult {
  if (depth > MAX_ARGUMENT_DEPTH) return { value, changed: false }
  if (DATA_ARGUMENT_KEYS.has(key)) return { value, changed: false }
  if (typeof value === 'string') {
    const next = rewriteArgumentString(value, key, context)
    return { value: next, changed: next !== value }
  }
  if (Array.isArray(value)) {
    let changed = false
    const out = value.map((item) => {
      const result = rewriteArgumentValue(item, key, context, depth + 1)
      if (result.changed) changed = true
      return result.value
    })
    return { value: changed ? out : value, changed }
  }
  if (typeof value === 'object' && value !== null) {
    let changed = false
    const out: Record<string, unknown> = Object.create(null) as Record<string, unknown>
    for (const [entryKey, entryValue] of Object.entries(value)) {
      const result = rewriteArgumentValue(entryValue, entryKey.toLowerCase().replace(/-/g, '_'), context, depth + 1)
      if (result.changed) changed = true
      out[entryKey] = result.value
    }
    return { value: changed ? out : value, changed }
  }
  return { value, changed: false }
}

interface DecimalLiteral {
  sign: '-' | ''
  digits: string
  exponent: number
}

/** Normalize a JSON decimal literal to sign/digits/exponent for value comparison. */
function decimalLiteral(token: string): DecimalLiteral | undefined {
  const match = token.match(/^(-?)(\d+)(?:\.(\d+))?(?:[eE]([+-]?\d+))?$/)
  if (match === null) return undefined
  const sign = match[1] === '-' ? '-' : ''
  const fraction = match[3] ?? ''
  let digits = `${match[2]}${fraction}`.replace(/^0+/, '')
  let exponent = Number(match[4] ?? 0) - fraction.length
  if (digits === '') return { sign, digits: '0', exponent: 0 }
  const trimmed = digits.replace(/0+$/, '')
  exponent += digits.length - trimmed.length
  digits = trimmed
  return { sign, digits, exponent }
}

function sameDecimal(a: DecimalLiteral, b: DecimalLiteral): boolean {
  return a.sign === b.sign && a.digits === b.digits && a.exponent === b.exponent
}

/** Detect numeric literals outside JSON strings that cannot survive parse/stringify. */
function hasUnsafeJsonNumber(raw: string): boolean {
  let inString = false
  let escaped = false
  for (let index = 0; index < raw.length; index++) {
    const ch = raw[index]!
    if (inString) {
      if (escaped) escaped = false
      else if (ch === '\\') escaped = true
      else if (ch === '"') inString = false
      continue
    }
    if (ch === '"') {
      inString = true
      continue
    }
    if (ch !== '-' && (ch < '0' || ch > '9')) continue
    const match = raw.slice(index).match(/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/)
    if (match === null) continue
    const token = match[0]
    const value = Number(token)
    if (!Number.isFinite(value)) return true
    if (!/[.eE]/.test(token)) {
      try {
        if (BigInt(value) !== BigInt(token)) return true
      } catch {
        return true
      }
    }
    const original = decimalLiteral(token)
    const canonical = decimalLiteral(String(value))
    if (original === undefined || canonical === undefined || !sameDecimal(original, canonical)) return true
    index += token.length - 1
  }
  return false
}

/** Rewrite one raw JSON `arguments` string; leave malformed or unchanged values untouched. */
function rewriteArgumentsJson(raw: string, context: RewriteContext): string {
  if (raw.length > MAX_STRING_SCAN_CHARS) return raw
  if (hasUnsafeJsonNumber(raw)) return raw
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return raw
  }
  const result = rewriteArgumentValue(parsed, '', context, 0)
  return result.changed ? JSON.stringify(result.value) : raw
}

function rewriteLegacyCommand(data: Record<string, unknown>, context: RewriteContext): Record<string, unknown> | undefined {
  const command = data.command
  if (typeof command !== 'string') return undefined
  const next = replacePathOccurrences(command, context.from, context.to)
  return next === command ? undefined : { ...data, command: next }
}

function rewriteToolCallData(
  data: unknown,
  context: RewriteContext,
  cache: Map<string, string>,
): unknown {
  if (typeof data !== 'object' || data === null) return data
  const record = data as Record<string, unknown>
  let changed: Record<string, unknown> | undefined = rewriteLegacyCommand(record, context)
  if (typeof record.arguments === 'string') {
    const next = rewriteArgumentsJson(record.arguments, context)
    if (next !== record.arguments) {
      changed = { ...(changed ?? record), arguments: next }
    }
  }
  if (changed !== undefined) {
    const id = callIdOf(record)
    if (id !== undefined && typeof changed.arguments === 'string') cache.set(id, changed.arguments)
    return changed
  }
  return data
}

function rewriteAssistantData(
  data: unknown,
  context: RewriteContext,
  cache: Map<string, string>,
): unknown {
  if (typeof data !== 'object' || data === null) return data
  const record = data as Record<string, unknown>
  const message = typeof record.message === 'object' && record.message !== null
    ? record.message as Record<string, unknown>
    : undefined
  const container = message ?? record
  if (!Array.isArray(container.content)) return data
  let changed = false
  const content = container.content.map((block) => {
    if (typeof block !== 'object' || block === null) return block
    const b = block as Record<string, unknown>
    if (typeof b.type !== 'string' || !TOOL_BLOCK_KIND.test(b.type) || typeof b.arguments !== 'string') return block
    const id = callIdOf(b)
    const cached = id === undefined ? undefined : cache.get(id)
    const next = cached ?? rewriteArgumentsJson(b.arguments, context)
    if (id !== undefined) cache.set(id, next)
    if (next === b.arguments) return block
    changed = true
    return { ...b, arguments: next }
  })
  if (!changed) return data
  const nextContainer = { ...container, content }
  const cleared = record.stream === undefined ? {} : { stream: [] }
  if (message === undefined) return { ...record, content, ...cleared }
  return { ...record, message: nextContainer, ...cleared }
}

/**
 * Return a new seed with the header cwd and executable tool-call arguments
 * remapped to `newCwd`. Historical prose, tool results, and tool-private
 * `meta` stay unchanged. An assistant message whose tool-call arguments are
 * remapped has its timed stream cleared because the stream still carries the
 * old arguments; untouched messages keep their stream.
 */
export function rewriteSeedCwd(seed: TaskSeed, oldCwd: string, newCwd: string): TaskSeed {
  validateSeedBounds(seed)
  const from = trimTrailingSeparators(validateSeedCwd(oldCwd))
  const rawTo = validateSeedCwd(newCwd)
  const trimmedTo = trimTrailingSeparators(rawTo)
  const to = trimmedTo === '' || isDriveRoot(trimmedTo) ? rawTo : trimmedTo
  if (from === '' || from === '/' || from === '\\' || isDriveRoot(from)) {
    return { cwd: newCwd, events: seed.events.slice() }
  }
  const context: RewriteContext = {
    from,
    to,
    platform: isWindowsCwd(from) ? 'windows' : 'posix',
  }
  const cache = new Map<string, string>()
  const events = seed.events.map((event) => {
    if (event.type === 'tool/call') {
      const data = rewriteToolCallData(event.data, context, cache)
      return data === event.data ? event : { ...event, data }
    }
    if (event.type === 'assistant/message') {
      const data = rewriteAssistantData(event.data, context, cache)
      return data === event.data ? event : { ...event, data }
    }
    return event
  })
  return { cwd: newCwd, events }
}

/** Drop capture-session environment context that dsh regenerates for the new run. */
export function filterRegeneratedContext(events: SeedEvent[]): SeedEvent[] {
  return events.filter((event) => {
    if (event.type !== 'user/message' || typeof event.data !== 'object' || event.data === null) return true
    const data = event.data as Record<string, unknown>
    const message = typeof data.message === 'object' && data.message !== null
      ? data.message as Record<string, unknown>
      : undefined
    const source = (message?.source ?? data.source)
    if (typeof source !== 'object' || source === null || Array.isArray(source)) return true
    const record = source as Record<string, unknown>
    if (record.form === 'snapshot' || record.form === 'catalog') return false
    return record.kind !== 'agent-instructions' && record.kind !== 'runtime-context'
  })
}

/** Read a tool-call id out of loosely typed event data. */
function callIdOf(data: unknown): string | undefined {
  if (typeof data !== 'object' || data === null) return undefined
  const record = data as Record<string, unknown>
  const candidates = [record]
  if (typeof record.message === 'object' && record.message !== null) {
    candidates.push(record.message as Record<string, unknown>)
  }
  for (const candidate of candidates) {
    for (const key of ['toolCallId', 'callId'] as const) {
      if (typeof candidate[key] === 'string') return candidate[key] as string
    }
    const source = candidate.source
    if (typeof source === 'object' && source !== null && !Array.isArray(source)) {
      const callId = (source as Record<string, unknown>).callId
      if (typeof callId === 'string') return callId
    }
    if (typeof candidate.id === 'string') return candidate.id
  }
  return undefined
}

/**
 * Remove assistant-message content blocks that reference a dropped tool call.
 * Blocks are objects inside `data.content`; a block references a call via
 * `id`/`callId`/`toolCallId` and a tool-ish `type` (`tool-call`, `tool_call`,
 * `tool-use`, `tool_use`, `tool-result`, `tool_result`).
 */
const TOOL_BLOCK_RE = /^tool[-_](call|use|result)$/

function stripDroppedToolBlocks(data: unknown, dropped: ReadonlySet<string>, availableTools: ReadonlySet<string>): unknown {
  if (typeof data !== 'object' || data === null) return data
  const record = data as Record<string, unknown>
  const message = typeof record.message === 'object' && record.message !== null
    ? record.message as Record<string, unknown>
    : undefined
  const container = message ?? record
  if (!Array.isArray(container.content)) return data
  const content = container.content.filter((block) => {
    if (typeof block !== 'object' || block === null) return true
    const b = block as Record<string, unknown>
    if (typeof b.type !== 'string' || !TOOL_BLOCK_RE.test(b.type)) return true
    const id = callIdOf(b)
    if (id !== undefined) return !dropped.has(id)
    return typeof b.name !== 'string' || availableTools.has(b.name)
  })
  if (content.length === container.content.length) return data
  return message === undefined
    ? { ...record, content }
    : { ...record, message: { ...message, content } }
}

/**
 * Filter a seed event stream down to the tools available on the importing
 * machine: drop `tool/call` events whose `data.name` is not in
 * `availableTools`, drop the matching `tool/result` events, and strip
 * tool-call blocks referencing dropped calls from assistant messages.
 * Event order and all other events are preserved.
 */
export function filterSeedTools(events: SeedEvent[], availableTools: Set<string>): SeedEvent[] {
  const dropped = new Set<string>()
  for (const event of events) {
    if (event.type !== 'tool/call') continue
    const data = event.data as Record<string, unknown> | undefined
    const name = typeof data?.name === 'string' ? data.name : undefined
    if (name === undefined || !availableTools.has(name)) {
      const id = callIdOf(event.data)
      if (id !== undefined) dropped.add(id)
    }
  }
  const out: SeedEvent[] = []
  for (const event of events) {
    if (event.type === 'tool/call') {
      const id = callIdOf(event.data)
      if (id !== undefined && dropped.has(id)) continue
      // Calls without an id were already accounted for above by name.
      const data = event.data as Record<string, unknown> | undefined
      if (typeof data?.name === 'string' && !availableTools.has(data.name)) continue
    }
    if (event.type === 'tool/result') {
      const id = callIdOf(event.data)
      if (id !== undefined && dropped.has(id)) continue
    }
    if (event.type === 'assistant/message') {
      out.push({ ...event, data: stripDroppedToolBlocks(event.data, dropped, availableTools) })
      continue
    }
    out.push(event)
  }
  return out
}
