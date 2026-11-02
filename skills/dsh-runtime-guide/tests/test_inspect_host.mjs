import { execFileSync, spawn } from 'node:child_process'
import { resolve } from 'node:path'
const script = resolve(import.meta.dirname, '../scripts/inspect-host.mjs')
const run = (pid, port = '1') => JSON.parse(execFileSync('node', [script, '--pid', String(pid), '--checkout', process.cwd(), '--port', port], { encoding: 'utf8' }))
const self = run(process.pid)
for (const key of ['pid', 'argv', 'startEpoch', 'checkout', 'ghostHost', 'port', 'portOpen', 'dshHome', 'platform']) {
  if (!(key in self)) throw new Error(`missing ${key}`)
}
if (self.pid !== process.pid) throw new Error('pid mismatch')
if (!Array.isArray(self.argv) || self.argv.length === 0) throw new Error('argv missing')
if (!(typeof self.ghostHost === 'boolean' || self.ghostHost === null)) throw new Error('ghost type')
if (self.port !== 1) throw new Error('explicit port not honored')
const child = spawn(process.execPath, ['-e', 'setTimeout(() => {}, 5000)'], { env: { ...process.env, DSH_HOME: '/tmp/bench-runtime-home' }, stdio: 'ignore' })
try {
  await new Promise(resolve => setTimeout(resolve, 150))
  const target = run(child.pid)
  if (target.dshHome !== '/tmp/bench-runtime-home') throw new Error(`target env dshHome mismatch: ${target.dshHome}`)
  if (target.dshHomeSource !== 'target-env') throw new Error('dshHome source')
} finally {
  child.kill()
}
console.log('dsh-runtime-guide inspect-host test: PASS')
