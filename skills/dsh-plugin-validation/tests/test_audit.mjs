import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
const root = resolve(import.meta.dirname, '..')
const run = (fixture) => {
  try {
    return JSON.parse(execFileSync('node', [resolve(root, 'scripts/plugin-audit.mjs'), resolve(root, 'tests/fixtures', fixture)], { encoding: 'utf8' }))
  } catch (error) {
    return JSON.parse(error.stdout)
  }
}
const benign = run('benign')
if (benign.counts.high !== 0) throw new Error(`benign high findings: ${JSON.stringify(benign.findings)}`)
const malicious = run('malicious')
for (const id of ['install-script', 'dependency-source', 'child-process', 'raw-route', 'dynamic-code', 'html-injection', 'credential-reference']) {
  if (!malicious.findings.some(f => f.id === id)) throw new Error(`missing ${id}`)
}
console.log('dsh-plugin-validation audit test: PASS')

const guarded = run('guarded')
if (guarded.counts.high !== 0) throw new Error(`guarded high findings: ${JSON.stringify(guarded.findings)}`)
if (!guarded.findings.some(f => f.id === 'route-auth-context')) throw new Error('missing guarded route context')
if (!guarded.findings.some(f => f.id === 'credential-reference')) throw new Error('missing destructured credential')
if (guarded.findings.some(f => f.id === 'client-files')) throw new Error('false client-files without files list')
const hidden = run('hidden')
if (!hidden.findings.some(f => f.id === 'dynamic-code' && f.severity === 'high')) throw new Error('hidden dist entry not scanned')
console.log('dsh-plugin-validation false-positive/negative test: PASS')
