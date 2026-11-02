#!/usr/bin/env node
/** Read-only dependency/advisory/issue audit. Offline fixtures by default; opt-in OSV. */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const repo = process.argv[2]
if (!repo) { console.error('usage: supply-chain-audit.mjs <plugin-dir> [--online] [--fixtures <dir>]'); process.exit(2) }
const online = process.argv.includes('--online')
const fixtureArg = process.argv.indexOf('--fixtures')
const fixtures = fixtureArg >= 0 ? process.argv[fixtureArg + 1] : join(repo, 'fixtures')
const read = path => { try { return readFileSync(path, 'utf8') } catch { return '' } }
const json = path => { try { return JSON.parse(read(path)) } catch { return null } }
const cmp = (a, b) => {
  const pa = String(a).replace(/^v/, '').split('-')[0].split('.').map(Number)
  const pb = String(b).replace(/^v/, '').split('-')[0].split('.').map(Number)
  for (let i = 0; i < Math.max(pa.length, pb.length); i += 1) {
    const d = (pa[i] || 0) - (pb[i] || 0)
    if (d) return d
  }
  return 0
}
const packages = []
const lock = json(join(repo, 'package-lock.json'))
if (lock?.packages) {
  for (const [key, value] of Object.entries(lock.packages)) {
    if (!key || !value?.version) continue
    const name = key.split('node_modules/').pop()
    if (!name) continue
    packages.push({ name, version: value.version, direct: key === `node_modules/${name}` })
  }
}
const advisories = []
const addJson = dir => {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name)
    const st = statSync(path)
    if (st.isDirectory()) addJson(path)
    else if (st.isFile() && name.endsWith('.json')) {
      const value = json(path)
      if (value) advisories.push({ ...value, _file: relative(repo, path) })
    }
  }
}
try { addJson(join(fixtures, 'advisories')) } catch {}
const issues = []
try {
  for (const name of readdirSync(join(fixtures, 'issues'))) {
    if (!name.endsWith('.json')) continue
    const value = json(join(fixtures, 'issues', name))
    if (value) issues.push(value)
  }
} catch {}
const affected = (advisory, pkg) => {
  for (const entry of advisory.affected || []) {
    if (entry.package?.name !== pkg.name || (entry.package?.ecosystem && entry.package.ecosystem !== 'npm')) continue
    if (Array.isArray(entry.versions) && entry.versions.includes(pkg.version)) return true
    for (const range of entry.ranges || []) {
      let introduced = null
      for (const event of range.events || []) {
        if (event.introduced) introduced = event.introduced
        if (event.fixed && introduced !== null && cmp(pkg.version, introduced) >= 0 && cmp(pkg.version, event.fixed) < 0) return true
        if (event.fixed && introduced === null && cmp(pkg.version, event.fixed) < 0) return true
      }
    }
    if (entry.database_specific?.vulnerable_versions?.includes(pkg.version)) return true
  }
  return false
}
const findings = []
for (const pkg of packages) {
  for (const advisory of advisories) {
    if (affected(advisory, pkg)) {
      findings.push({
        package: pkg.name, version: pkg.version, id: advisory.id,
        aliases: advisory.aliases || [], summary: advisory.summary || '',
        fixed: (advisory.affected || []).flatMap(a => (a.ranges || []).flatMap(r => (r.events || []).filter(e => e.fixed).map(e => e.fixed))).join(', '),
        source: advisory._file,
      })
    }
  }
}
let onlineFindings = []
let onlineError = null
if (online) {
  try {
    const queries = packages.slice(0, 100).map(pkg => ({ package: { name: pkg.name, ecosystem: 'npm' }, version: pkg.version }))
    const response = await fetch('https://api.osv.dev/v1/querybatch', {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ queries }),
    })
    if (!response.ok) throw new Error(`OSV HTTP ${response.status}`)
    const batch = await response.json()
    const ids = new Set()
    for (const result of batch.results || []) for (const vuln of result.vulns || []) ids.add(vuln.id)
    for (const id of [...ids].slice(0, 30)) {
      const detail = await fetch(`https://api.osv.dev/v1/vulns/${encodeURIComponent(id)}`)
      if (!detail.ok) continue
      const advisory = await detail.json()
      for (const pkg of packages) {
        if (!affected(advisory, pkg)) continue
        onlineFindings.push({
          package: pkg.name, version: pkg.version, id: advisory.id,
          aliases: advisory.aliases || [], summary: advisory.summary || '',
          fixed: (advisory.affected || []).flatMap(a => (a.ranges || []).flatMap(r => (r.events || []).filter(e => e.fixed).map(e => e.fixed))).join(', '),
          source: 'osv.dev',
        })
      }
    }
  } catch (error) {
    onlineError = String(error)
  }
}
const seen = new Set()
const allFindings = [...findings, ...onlineFindings].filter(finding => {
  const key = `${finding.id}:${finding.package}:${finding.version}`
  if (seen.has(key)) return false
  seen.add(key)
  return true
})
const result = {
  repo,
  mode: online ? 'online+fixtures' : 'fixtures',
  packages: packages.length,
  vulnerabilities: allFindings,
  issues,
  onlineError,
  notes: [
    'Offline fixtures are not a complete advisory database; absence is not safety.',
    online ? 'Online OSV lookup used the public API; record advisory modified timestamps and fetch time.' : 'Run with --online for the public OSV feed; fixture mode is a snapshot.',
  ],
}
console.log(JSON.stringify(result, null, 2))
process.exit(0)
