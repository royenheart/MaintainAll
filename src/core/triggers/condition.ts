/**
 * Safe CEL-subset evaluator for trigger `when` expressions.
 *
 * Supported constructs:
 * - literals: strings ('single' or "double" quoted), numbers, `true`,
 *   `false`, `null`
 * - identifiers rooted at `event` (with dot access, e.g.
 *   `event.payload.level`) plus the shorthands `payload`, `occurredAt`,
 *   `source`
 * - comparisons: `== != < <= > >=` (strict equality; ordering only between
 *   two numbers or two strings)
 * - logic: `&& || !` (operands must be booleans) and parentheses
 * - whitelisted functions: `matches(value, regex)`, `startsWith(value,
 *   prefix)`, `endsWith(value, suffix)`, `contains(value, substr)`
 *
 * Everything else — unknown identifiers, unknown functions, member access on
 * non-objects, type mismatches, trailing tokens — throws. The evaluator never
 * touches `eval`, `Function`, IO, or any Node API beyond `RegExp`.
 */

import type { TriggerEvent } from '../contract.ts'

// ---------------------------------------------------------------------------
// Tokenizer
// ---------------------------------------------------------------------------

type Token =
  | { kind: 'number'; value: number }
  | { kind: 'string'; value: string }
  | { kind: 'ident'; value: string }
  | { kind: 'op'; value: string }
  | { kind: 'eof' }

const OPERATORS = ['&&', '||', '==', '!=', '<=', '>=', '<', '>', '!', '(', ')', '.', ',']

function tokenize(input: string): Token[] {
  const tokens: Token[] = []
  let i = 0
  while (i < input.length) {
    const ch = input[i]!
    if (ch === ' ' || ch === '\t' || ch === '\n' || ch === '\r') {
      i++
      continue
    }
    if (ch === "'" || ch === '"') {
      const quote = ch
      let j = i + 1
      let value = ''
      while (j < input.length && input[j] !== quote) {
        if (input[j] === '\\') {
          const esc = input[j + 1]
          if (esc === undefined) throw new Error('unterminated string literal')
          if (esc === 'n') value += '\n'
          else if (esc === 't') value += '\t'
          else if (esc === 'r') value += '\r'
          else if (esc === '\\') value += '\\'
          else if (esc === "'") value += "'"
          else if (esc === '"') value += '"'
          else throw new Error(`unsupported escape sequence: \\${esc}`)
          j += 2
        } else {
          value += input[j]
          j++
        }
      }
      if (j >= input.length) throw new Error('unterminated string literal')
      tokens.push({ kind: 'string', value })
      i = j + 1
      continue
    }
    if ((ch >= '0' && ch <= '9') || (ch === '.' && input[i + 1] !== undefined && input[i + 1]! >= '0' && input[i + 1]! <= '9')) {
      let j = i
      let seenDot = false
      while (j < input.length) {
        const c = input[j]!
        if (c >= '0' && c <= '9') j++
        else if (c === '.' && !seenDot) { seenDot = true; j++ }
        else break
      }
      const raw = input.slice(i, j)
      const value = Number(raw)
      if (Number.isNaN(value)) throw new Error(`invalid number literal: ${raw}`)
      tokens.push({ kind: 'number', value })
      i = j
      continue
    }
    if ((ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') || ch === '_') {
      let j = i + 1
      while (j < input.length) {
        const c = input[j]!
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c === '_') j++
        else break
      }
      tokens.push({ kind: 'ident', value: input.slice(i, j) })
      i = j
      continue
    }
    const two = input.slice(i, i + 2)
    if (OPERATORS.includes(two)) {
      tokens.push({ kind: 'op', value: two })
      i += 2
      continue
    }
    if (OPERATORS.includes(ch)) {
      tokens.push({ kind: 'op', value: ch })
      i++
      continue
    }
    throw new Error(`unexpected character in expression: ${JSON.stringify(ch)}`)
  }
  tokens.push({ kind: 'eof' })
  return tokens
}

// ---------------------------------------------------------------------------
// Parser (recursive descent)
// ---------------------------------------------------------------------------

type Expr =
  | { kind: 'literal'; value: unknown }
  | { kind: 'ident'; name: string }
  | { kind: 'member'; object: Expr; property: string }
  | { kind: 'call'; name: string; args: Expr[] }
  | { kind: 'not'; operand: Expr }
  | { kind: 'binary'; op: string; left: Expr; right: Expr }

class Parser {
  private pos = 0
  private readonly tokens: Token[]

  constructor(tokens: Token[]) {
    this.tokens = tokens
  }

  private peek(): Token {
    return this.tokens[this.pos]!
  }

  private next(): Token {
    const token = this.tokens[this.pos]!
    this.pos++
    return token
  }

  private expectOp(value: string): void {
    const token = this.next()
    if (token.kind !== 'op' || token.value !== value) {
      throw new Error(`expected '${value}' but found ${describeToken(token)}`)
    }
  }

  parseExpression(): Expr {
    return this.parseOr()
  }

  private parseOr(): Expr {
    let left = this.parseAnd()
    while (this.peek().kind === 'op' && (this.peek() as { value: string }).value === '||') {
      this.next()
      left = { kind: 'binary', op: '||', left, right: this.parseAnd() }
    }
    return left
  }

  private parseAnd(): Expr {
    let left = this.parseUnary()
    while (this.peek().kind === 'op' && (this.peek() as { value: string }).value === '&&') {
      this.next()
      left = { kind: 'binary', op: '&&', left, right: this.parseUnary() }
    }
    return left
  }

  private parseUnary(): Expr {
    const token = this.peek()
    if (token.kind === 'op' && token.value === '!') {
      this.next()
      return { kind: 'not', operand: this.parseUnary() }
    }
    return this.parseComparison()
  }

  private parseComparison(): Expr {
    const left = this.parsePrimary()
    const token = this.peek()
    if (token.kind === 'op' && ['==', '!=', '<', '<=', '>', '>='].includes(token.value)) {
      this.next()
      return { kind: 'binary', op: token.value, left, right: this.parsePrimary() }
    }
    return left
  }

  private parsePrimary(): Expr {
    const token = this.next()
    if (token.kind === 'number' || token.kind === 'string') {
      return { kind: 'literal', value: token.value }
    }
    if (token.kind === 'op' && token.value === '(') {
      const inner = this.parseExpression()
      this.expectOp(')')
      return inner
    }
    if (token.kind === 'ident') {
      if (token.value === 'true') return { kind: 'literal', value: true }
      if (token.value === 'false') return { kind: 'literal', value: false }
      if (token.value === 'null') return { kind: 'literal', value: null }
      // Function call?
      if (this.peek().kind === 'op' && (this.peek() as { value: string }).value === '(') {
        this.next()
        const args: Expr[] = []
        if (!(this.peek().kind === 'op' && (this.peek() as { value: string }).value === ')')) {
          args.push(this.parseExpression())
          while (this.peek().kind === 'op' && (this.peek() as { value: string }).value === ',') {
            this.next()
            args.push(this.parseExpression())
          }
        }
        this.expectOp(')')
        return { kind: 'call', name: token.value, args }
      }
      let expr: Expr = { kind: 'ident', name: token.value }
      while (this.peek().kind === 'op' && (this.peek() as { value: string }).value === '.') {
        this.next()
        const prop = this.next()
        if (prop.kind !== 'ident') {
          throw new Error(`expected property name after '.' but found ${describeToken(prop)}`)
        }
        expr = { kind: 'member', object: expr, property: prop.value }
      }
      return expr
    }
    throw new Error(`unexpected token: ${describeToken(token)}`)
  }

  assertEnd(): void {
    const token = this.peek()
    if (token.kind !== 'eof') {
      throw new Error(`unexpected trailing token: ${describeToken(token)}`)
    }
  }
}

function describeToken(token: Token): string {
  if (token.kind === 'eof') return 'end of expression'
  return `'${token.value}'`
}

// ---------------------------------------------------------------------------
// Evaluator
// ---------------------------------------------------------------------------

const ROOTS = new Set(['event', 'payload', 'occurredAt', 'source'])

type FunctionImpl = (args: unknown[]) => boolean

function requireString(value: unknown, fn: string, position: string): string {
  if (typeof value !== 'string') {
    throw new Error(`${fn}: ${position} argument must be a string`)
  }
  return value
}

function arity(args: unknown[], fn: string, count: number): void {
  if (args.length !== count) {
    throw new Error(`${fn}: expected ${count} arguments, got ${args.length}`)
  }
}

const FUNCTIONS: Record<string, FunctionImpl> = {
  matches(args) {
    arity(args, 'matches', 2)
    const value = requireString(args[0], 'matches', 'first')
    const pattern = requireString(args[1], 'matches', 'second')
    return regexFor(pattern).test(value)
  },
  startsWith(args) {
    arity(args, 'startsWith', 2)
    return requireString(args[0], 'startsWith', 'first').startsWith(
      requireString(args[1], 'startsWith', 'second'),
    )
  },
  endsWith(args) {
    arity(args, 'endsWith', 2)
    return requireString(args[0], 'endsWith', 'first').endsWith(
      requireString(args[1], 'endsWith', 'second'),
    )
  },
  contains(args) {
    arity(args, 'contains', 2)
    return requireString(args[0], 'contains', 'first').includes(
      requireString(args[1], 'contains', 'second'),
    )
  },
}

const AST_CACHE = new Map<string, Expr>()
const REGEX_CACHE = new Map<string, RegExp>()
const MAX_CACHE_ENTRIES = 256

function regexFor(pattern: string): RegExp {
  const cached = REGEX_CACHE.get(pattern)
  if (cached !== undefined) return cached
  const compiled = new RegExp(pattern)
  if (REGEX_CACHE.size >= MAX_CACHE_ENTRIES) REGEX_CACHE.clear()
  REGEX_CACHE.set(pattern, compiled)
  return compiled
}

function parseCel(expression: string): Expr {
  const cached = AST_CACHE.get(expression)
  if (cached !== undefined) return cached
  const parser = new Parser(tokenize(expression))
  const ast = parser.parseExpression()
  parser.assertEnd()
  if (AST_CACHE.size >= MAX_CACHE_ENTRIES) AST_CACHE.clear()
  AST_CACHE.set(expression, ast)
  return ast
}

function evaluate(expr: Expr, event: TriggerEvent): unknown {
  switch (expr.kind) {
    case 'literal':
      return expr.value
    case 'ident': {
      if (!ROOTS.has(expr.name)) {
        throw new Error(`unknown identifier: ${expr.name}`)
      }
      if (expr.name === 'event') return event
      if (expr.name === 'payload') return event.payload
      if (expr.name === 'occurredAt') return event.occurredAt
      return event.source
    }
    case 'member': {
      const object = evaluate(expr.object, event)
      if (typeof object !== 'object' || object === null || Array.isArray(object)) {
        throw new Error(`cannot access property '${expr.property}' on a non-object value`)
      }
      return (object as Record<string, unknown>)[expr.property]
    }
    case 'call': {
      const fn = Object.hasOwn(FUNCTIONS, expr.name) ? FUNCTIONS[expr.name] : undefined
      if (!fn) {
        throw new Error(`function not whitelisted: ${expr.name}`)
      }
      return fn(expr.args.map((arg) => evaluate(arg, event)))
    }
    case 'not': {
      const operand = evaluate(expr.operand, event)
      if (typeof operand !== 'boolean') {
        throw new Error("'!' operand must be a boolean")
      }
      return !operand
    }
    case 'binary':
      return evaluateBinary(expr, event)
  }
}

function evaluateBinary(expr: Extract<Expr, { kind: 'binary' }>, event: TriggerEvent): unknown {
  if (expr.op === '&&' || expr.op === '||') {
    const left = evaluate(expr.left, event)
    if (typeof left !== 'boolean') {
      throw new Error(`'${expr.op}' left operand must be a boolean`)
    }
    if (expr.op === '&&' && !left) return false
    if (expr.op === '||' && left) return true
    const right = evaluate(expr.right, event)
    if (typeof right !== 'boolean') {
      throw new Error(`'${expr.op}' right operand must be a boolean`)
    }
    return right
  }
  const left = evaluate(expr.left, event)
  const right = evaluate(expr.right, event)
  switch (expr.op) {
    case '==':
      return left === right
    case '!=':
      return left !== right
    case '<':
    case '<=':
    case '>':
    case '>=': {
      const bothNumbers = typeof left === 'number' && typeof right === 'number'
      const bothStrings = typeof left === 'string' && typeof right === 'string'
      if (!bothNumbers && !bothStrings) {
        throw new Error(`'${expr.op}' requires two numbers or two strings`)
      }
      if (expr.op === '<') return left < right
      if (expr.op === '<=') return left <= right
      if (expr.op === '>') return left > right
      return left >= right
    }
    /* istanbul ignore next -- parser only emits known ops */
    default:
      throw new Error(`unsupported operator: ${expr.op}`)
  }
}

/** Validate identifiers, whitelisted functions, and literal regex patterns without an event. */
function validateExpr(expr: Expr): void {
  switch (expr.kind) {
    case 'literal':
      return
    case 'ident':
      if (!ROOTS.has(expr.name)) throw new Error(`unknown identifier: ${expr.name}`)
      return
    case 'member':
      validateExpr(expr.object)
      return
    case 'call': {
      if (!Object.hasOwn(FUNCTIONS, expr.name)) throw new Error(`function not whitelisted: ${expr.name}`)
      if (expr.args.length !== 2) {
        throw new Error(`${expr.name}: expected 2 arguments, got ${expr.args.length}`)
      }
      for (const [index, arg] of expr.args.entries()) {
        validateExpr(arg)
        if (arg.kind === 'literal' && typeof arg.value !== 'string') {
          throw new Error(`${expr.name}: ${index === 0 ? 'first' : 'second'} argument must be a string`)
        }
      }
      if (expr.name === 'matches' && expr.args[1]?.kind === 'literal'
        && typeof expr.args[1].value === 'string') {
        try {
          regexFor(expr.args[1].value)
        } catch (error) {
          throw new Error(`matches: invalid regular expression: ${error instanceof Error ? error.message : String(error)}`)
        }
      }
      return
    }
    case 'not':
      validateExpr(expr.operand)
      return
    case 'binary':
      validateExpr(expr.left)
      validateExpr(expr.right)
      return
  }
}

/** Parse-only validation for a CEL condition; no event is evaluated. */
export function validateCel(expression: string | undefined): void {
  if (expression === undefined || expression.trim() === '') return
  const ast = parseCel(expression)
  validateExpr(ast)
}

/**
 * Evaluate a CEL `when` expression against a normalized `TriggerEvent`.
 *
 * An empty or whitespace-only expression returns `true` (no condition). Any
 * syntax error, unknown identifier/function, type mismatch, or non-boolean
 * result throws.
 */
export function evaluateCel(expression: string | undefined, event: TriggerEvent): boolean {
  if (expression === undefined || expression.trim() === '') {
    return true
  }
  const ast = parseCel(expression)
  const result = evaluate(ast, event)
  if (typeof result !== 'boolean') {
    throw new Error('when expression must evaluate to a boolean')
  }
  return result
}
