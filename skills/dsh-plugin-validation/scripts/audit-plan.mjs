#!/usr/bin/env node
/** Read-only: enumerate audit surfaces and produce subagent briefs. */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, extname } from 'node:path'

const repo = process.argv[2]
if (!repo) { console.error('usage: audit-plan.mjs <plugin-dir>'); process.exit(2) }
const files = []
const walk = (dir) => {
  for (const name of readdirSync(dir)) {
    if (['node_modules', '.git', 'dist', 'build'].includes(name)) continue
    const path = join(dir, name)
    const st = statSync(path)
    if (st.isDirectory()) walk(path)
    else if (st.isFile() && ['.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx'].includes(extname(path))) files.push(relative(repo, path))
  }
}
try { walk(repo) } catch (error) { console.error(String(error)); process.exit(1) }
const by = (re) => files.filter(file => re.test(readFileSync(join(repo, file), 'utf8')))
const surfaces = {
  install: { files: ['package.json', 'package-lock.json', 'pnpm-lock.yaml', 'yarn.lock', 'bun.lock'].filter(file => { try { return statSync(join(repo, file)).isFile() } catch { return false } }) },
  host: by(/webServer|registerUpgrade|child_process|spawn|exec\(|readFile|writeFile|process\.env|credentials/),
  client: by(/innerHTML|dangerouslySetInnerHTML|eval\(|new Function|postMessage|WebSocket|fetch\(|dsh\.client|inject/),
  composition: ['cordis.patch.yml', 'package.json'].filter(file => { try { return statSync(join(repo, file)).isFile() } catch { return false } }),
}
const briefs = Object.entries(surfaces).filter(([, value]) => (Array.isArray(value) ? value.length : value.files.length)).map(([surface, value]) => ({
  surface,
  files: (Array.isArray(value) ? value : value.files).slice(0, 40),
  brief: `Repository: ${repo}\nSurface: ${surface}\nRead-only. Do not edit/install/execute lifecycle scripts. Inspect only the listed files. Return JSON findings with file:line, evidence, why, verify, notVerified.`,
}))
console.log(JSON.stringify({ repo, files: files.length, briefs, note: 'Spawn at most four read-only children; parent merges reports.' }, null, 2))
