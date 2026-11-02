#!/usr/bin/env node
/** Read-only static audit for third-party dsh plugins. Never executes plugin code. */
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, extname, resolve } from 'node:path'

const repo = process.argv[2]
if (!repo) { console.error('usage: plugin-audit.mjs <plugin-dir>'); process.exit(2) }
const findings = []
const add = (severity, id, file, line, evidence, why, verify) => findings.push({ severity, id, file, line, evidence: String(evidence).slice(0, 240), why, verify })
const text = (path) => { try { return readFileSync(path, 'utf8') } catch { return '' } }
const pkgPath = join(repo, 'package.json')
let pkg = {}
try { pkg = JSON.parse(text(pkgPath)) } catch { add('high', 'package-json', 'package.json', 0, 'missing/invalid package.json', 'cannot establish plugin identity or scripts', 'obtain the source') }
const files = []
const notScanned = []
const walk = (dir) => {
  for (const name of readdirSync(dir)) {
    if (['node_modules', '.git', 'dist', 'build', '.next', 'coverage'].includes(name)) { notScanned.push(relative(repo, join(dir, name))); continue }
    const path = join(dir, name)
    const st = statSync(path)
    if (st.isDirectory()) walk(path)
    else if (st.isFile() && st.size < 2_000_000) files.push(path)
    else if (st.isFile()) notScanned.push(relative(repo, path))
  }
}
try { walk(repo) } catch (error) { add('high', 'unreadable', '.', 0, String(error), 'cannot scan the tree', 'inspect permissions') }
// Always include declared entry points even when they live under dist/build or a skipped tree.
for (const rel of [pkg.main, ...Object.values(pkg.exports || {}).filter(v => typeof v === 'string'), pkg.dsh?.client?.entry].filter(Boolean)) {
  const path = join(repo, String(rel).replace(/^\.\//, ''))
  if (existsSync(path) && statSync(path).isFile() && !files.includes(path)) files.push(path)
}
const addShipped = (path) => {
  if (!existsSync(path)) return
  const st = statSync(path)
  if (st.isDirectory()) for (const name of readdirSync(path)) addShipped(join(path, name))
  else if (st.isFile() && !files.includes(path)) files.push(path)
}
for (const entry of (Array.isArray(pkg.files) ? pkg.files : [])) {
  const path = resolve(repo, String(entry))
  if (!path.startsWith(repo + '/')) continue
  addShipped(path)
}
const source = files.filter(file => ['.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx'].includes(extname(file)))
const scripts = pkg.scripts || {}
for (const name of ['preinstall', 'install', 'postinstall', 'prepare']) {
  if (scripts[name]) {
    const body = String(scripts[name])
    add(/(curl|wget|http|process\.env|\.credentials)/.test(body) ? 'critical' : 'high', 'install-script', 'package.json', 0, `scripts.${name} = ${body}`, `${name} runs before the host review`, 'read the script; run only in a throwaway container')
  }
}
for (const [name, spec] of Object.entries({ ...(pkg.dependencies || {}), ...(pkg.devDependencies || {}) })) {
  if (/^(git\+|github:|https?:|file:|link:)/.test(String(spec))) {
    const absolute = /^(file|link):\//.test(String(spec)) || /^(file|link):\.\./.test(String(spec))
    add(absolute ? 'high' : 'review', 'dependency-source', 'package.json', 0, `${name}: ${spec}`, 'non-registry source can execute or leave the expected tree', 'pin and inspect the source')
  }
}
for (const [rel, content] of source.map(file => [relative(repo, file), text(file)])) {
  const lines = content.split('\n')
  const check = (severity, id, re, why, verify) => {
    lines.forEach((line, index) => { if (re.test(line)) add(severity, id, rel, index + 1, line.trim(), why, verify) })
  }
  check('review', 'child-process', /\b(child_process|execSync|spawnSync|execFileSync|execa)\b|\b(spawn|exec)\s*\(/, 'runs external processes with the host user permissions', 'trace argv/env and whether input is untrusted')
  check('high', 'dynamic-code', /\beval\s*\(|new\s+Function\s*\(|vm\.run(In|NewContext)\s*\(|import\s*\(\s*[`'"]https?:/, 'executes dynamically supplied code', 'confirm the source is trusted and not remote')
  check('high', 'html-injection', /\.innerHTML\s*=|dangerouslySetInnerHTML|document\.write\s*\(|insertAdjacentHTML/, 'writes markup without React escaping', 'trace the value to untrusted input; prefer text/React nodes')
  lines.forEach((line, index) => {
    if (!/webServer\.(register|registerUpgrade)\s*\(|\.listen\s*\(|createServer\s*\(/.test(line)) return
    const block = lines.slice(Math.max(0, index - 2), Math.min(lines.length, index + 10)).join('\n')
    const guarded = /(requestRejection|connection\.|ctx\.auth|auth\.)/i.test(block)
    add(guarded ? 'review' : 'high', guarded ? 'route-auth-context' : 'raw-route', rel, index + 1, line.trim(), 'opens a route; host auth is not automatic', 'check the route for connection/token/cookie gate and origin/host checks')
  })
  check('review', 'route-context', /router\.(get|post|put|delete)\s*\(/, 'defines an HTTP route; auth depends on its registration', 'inspect auth and exposure')
  check('review', 'credential-reference', /\.credentials|auth\.json|\.npmrc|id_rsa|\.ssh\b|process\.env(\.[A-Z0-9_]*(KEY|TOKEN|SECRET|PASSWORD)|\s*\[[^\]]*(KEY|TOKEN|SECRET|PASSWORD))|(const|let|var)\s*\{[^}]*\b(KEY|TOKEN|SECRET|PASSWORD)[^}]*\}\s*=\s*process\.env/i, 'references a credential source', 'trace whether the value is logged, sent, or persisted')
  check('high', 'credential-sink', /(credential|api[_-]?key|token|secret).*(fetch|http|send|log|console|write|exec)/i, 'combines a credential-like value with a network/log/write sink', 'confirm the value cannot reach the sink')
  check('review', 'env-read', /process\.env\b/, 'reads host environment; may include secrets', 'list the variables and the sink')
  check('review', 'network', /\bfetch\s*\(|axios|https?\.request|new\s+WebSocket|WebSocket\s*\(/, 'sends or receives data over the network', 'trace destination, payload, and TLS/origin validation')
  check('review', 'filesystem', /\b(readFile|writeFile|appendFile|mkdir|rm|unlink|createWriteStream)(Sync)?\s*\(/, 'filesystem access can leave the workspace or read user data', 'trace the path source and target')
  check('high', 'monkeypatch', /patch-package|patchedDependencies|defineProperty\s*\(\s*(globalThis|global)\b|(globalThis|global)\.[A-Za-z0-9_$]+\s*=|write(File|Stream)?Sync\s*\([^)]*node_modules|node_modules[^\n]*(write|patch)/, 'writes a global or a node_modules/patch entry', 'prefer a bundle/patch; treat as host compromise review')
  check('review', 'postmessage', /postMessage\s*\(/, 'cross-window messaging needs origin validation', 'verify event.origin and targetOrigin')
  const cred = /\.credentials|auth\.json|\.npmrc|id_rsa|\.ssh\b|process\.env(\.[A-Z0-9_]*(KEY|TOKEN|SECRET|PASSWORD)|\s*\[[^\]]*(KEY|TOKEN|SECRET|PASSWORD))|(const|let|var)\s*\{[^}]*\b(KEY|TOKEN|SECRET|PASSWORD)[^}]*\}\s*=\s*process\.env/i.test(content)
  const sink = /(fetch\s*\(|https?\.request|new\s+WebSocket|child_process|execSync|spawnSync|\.exec\s*\(|console\.log|\.write(File|Stream)?Sync\s*\()/i.test(content)
  if (cred && sink) add('critical', 'credential-taint', rel, 0, 'credential-like value and a network/log/write/exec sink in one file', 'combines secret access with a sink', 'confirm the value cannot reach the sink')
}
const manifest = pkg.dsh || {}
if (!manifest.bundle && !manifest.client) add('review', 'not-a-dsh-plugin', 'package.json', 0, 'no dsh.bundle or dsh.client', 'may not be a dsh plugin, or manifest is hidden elsewhere', 'confirm the actual install shape')
const patches = manifest.bundle?.patch
for (const rel of (Array.isArray(patches) ? patches : patches ? [patches] : [])) {
  const file = join(repo, rel)
  const content = text(file)
  if (!content) add('high', 'patch-missing', rel, 0, 'declared bundle patch is missing', 'install cannot compose the plugin', 'fix the package')
  const blocks = content.split(/(?=\n\s*-\s*id:)/)
  for (const block of blocks) {
    const id = (block.match(/-\s*id:\s*(\S+)/) || [])[1]
    if (!id) continue
    const name = (block.match(/\n\s*name:\s*['"]?([^'"\n]+)/) || [])[1]
    if (name && /^[./]/.test(name)) add('high', 'patch-relative-name', rel, 0, `${id}: ${name}`, 'bundle rows should resolve by package name, not a relative path', 'use the package name')
    if (name && name !== pkg.name) add(name.startsWith('@deepseek-ai/') ? 'high' : 'review', name.startsWith('@deepseek-ai/') ? 'patch-host-row' : 'patch-foreign-row', rel, 0, `${id}: ${name}`, 'patch inserts a row other than this package', 'confirm the row is intentional and reviewed')
    if (/^\s+disabled:\s*true/m.test(block)) add('review', 'patch-row-disabled', rel, 0, id, 'composition disables a row; verify it is not a host safety row', 'inspect the row and the reason')
    if (/(auth|token|secret|credential|requestRejection)/i.test(block)) add('review', 'patch-auth-override', rel, 0, id, 'patch touches an auth/credential-looking config', 'inspect the effective composition')
  }
}
const filesList = Array.isArray(pkg.files) ? pkg.files : []
if (pkg.dsh?.client && filesList.length > 0 && !filesList.some(entry => String(entry).includes('client') || String(entry) === 'lib' || String(entry) === 'dist')) add('review', 'client-files', 'package.json', 0, 'dsh.client without a matching files entry', 'packed install may omit the client', 'check npm pack')
const critical = findings.filter(f => f.severity === 'critical')
const high = findings.filter(f => f.severity === 'high')
const review = findings.filter(f => f.severity === 'review')
console.log(JSON.stringify({
  repo,
  verdict: critical.length || high.length ? 'BLOCK-OR-REVIEW' : review.length ? 'REVIEW' : 'CLEAN',
  counts: { critical: critical.length, high: high.length, review: review.length, total: findings.length },
  findings,
  notScanned: notScanned.slice(0, 40),
  notVerified: ['runtime behavior', 'auth middleware reachability', 'network destination trust', 'transitive dependencies'],
}, null, 2))
process.exit(high.length ? 1 : 0)
