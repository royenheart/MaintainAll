import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
const root = resolve(import.meta.dirname, '..')
const repo = resolve(root, '../../benchmarks/agent_eval/cases/supply-chain-audit/repo')
const out = JSON.parse(execFileSync('node', [resolve(root, 'scripts/supply-chain-audit.mjs'), repo], { encoding: 'utf8' }))
const ids = new Set(out.vulnerabilities.map(v => v.id))
if (!ids.has('GHSA-xvch-5gv4-984h')) throw new Error('missing minimist advisory')
if (!ids.has('GHSA-29mw-wpgm-hmr9') || !ids.has('GHSA-35jh-r3h4-6jhm')) throw new Error('missing lodash advisories')
if (!out.issues.some(issue => issue.number === 42)) throw new Error('missing issue 42')
if (out.vulnerabilities.some(v => v.package === 'left-pad')) throw new Error('false left-pad finding')
console.log('dsh-plugin-validation supply-chain test: PASS')
