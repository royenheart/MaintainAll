#!/usr/bin/env node
// Enumerate host entrypoints and any visible guard. Read-only; does not execute the plugin.
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const root = process.argv[2]
if (!root) { console.error('usage: node route-matrix.mjs <plugin-dir>'); process.exit(2) }
const files = []
function walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name)
    const stat = statSync(path)
    if (stat.isDirectory()) walk(path)
    else if (/\.(?:[cm]?[jt]sx?)$/.test(name)) files.push(path)
  }
}
walk(root)
const routes = []
for (const path of files) {
  const text = readFileSync(path, 'utf8')
  const lines = text.split('\n')
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]
    const match = line.match(/(?:webServer\.register|registerUpgrade|ctx\.on\(\s*['"]upgrade)\(\s*['"]([^'"]+)/)
    if (!match) continue
    const guarded = /requestRejection|withHostGate|withGate|\bgate\s*\(/.test(line)
    routes.push({
      route: match[1],
      file: relative(root, path).replaceAll('\\', '/'),
      line: i + 1,
      observed_guard: guarded ? 'host-gate-in-registration' : 'none-in-registration',
      note: 'verify the handler and middleware; a guard on a different route is not this route\'s guard.',
    })
  }
}
console.log(JSON.stringify({ root, routes }, null, 2))
