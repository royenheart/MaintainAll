#!/usr/bin/env node
/** Read-only dsh host/process/checkout inspector. Never writes. */
import { readFileSync, readlinkSync, statSync, existsSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { createConnection } from 'node:net'
import { resolve } from 'node:path'

const args = process.argv.slice(2)
const arg = (name, fallback) => {
  const i = args.indexOf(name)
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback
}
const pidArg = arg('--pid', null)
if (!pidArg) { console.error('usage: inspect-host.mjs --pid <dsh-host-pid> [--checkout <path>] [--port <port>]'); process.exit(2) }
const pid = Number(pidArg)
const checkout = resolve(arg('--checkout', process.cwd()))
const explicitPort = arg('--port', null)

const read = path => { try { return readFileSync(path, 'utf8') } catch { return '' } }
const cmdline = read(`/proc/${pid}/cmdline`).split('\0').filter(Boolean)
const targetEnv = read(`/proc/${pid}/environ`).split('\0').filter(Boolean).reduce((acc, item) => {
  const at = item.indexOf('=')
  if (at > 0) acc[item.slice(0, at)] = item.slice(at + 1)
  return acc
}, {})
const stat = read(`/proc/${pid}/stat`).trim().split(' ')
const btime = Number((read('/proc/stat').match(/^btime\s+(\d+)$/m) || [])[1] || 0)
const ticks = Number(stat[21] || 0)
const hz = 100
const startEpoch = btime ? Math.round((btime + ticks / hz) * 1000) : null
let commitEpoch = null
try { commitEpoch = Date.parse(execFileSync('git', ['-C', checkout, 'log', '-1', '--format=%cI'], { encoding: 'utf8' }).trim()) } catch {}
const pkg = (() => { try { return JSON.parse(read(`${checkout}/package.json`)) } catch { return {} } })()
const gitStatus = (() => { try { return execFileSync('git', ['-C', checkout, 'status', '--porcelain'], { encoding: 'utf8' }).trim() } catch { return '' } })()
const entryRel = pkg.main || (typeof pkg.exports === 'string' ? pkg.exports : null)
const entryPath = entryRel ? resolve(checkout, String(entryRel).replace(/^\.\//, '')) : null
let entryMtime = null
let entryChangedAfterStart = false
try { entryMtime = statSync(entryPath).mtimeMs } catch {}
let exePath = null
try { exePath = readlinkSync(`/proc/${pid}/exe`) } catch {}
entryChangedAfterStart = entryMtime !== null && startEpoch !== null && entryMtime > startEpoch
const portFromArgv = (() => {
  const i = cmdline.indexOf('--port')
  if (i >= 0) return Number(cmdline[i + 1])
  const eq = cmdline.find(value => value.startsWith('--port='))
  return eq ? Number(eq.slice('--port='.length)) : null
})()
const port = Number(explicitPort || portFromArgv || 3080)
const portOpen = await new Promise(done => {
  const socket = createConnection({ host: '127.0.0.1', port })
  socket.once('connect', () => { socket.destroy(); done(true) })
  socket.once('error', () => done(false))
  setTimeout(() => { socket.destroy(); done(false) }, 400)
})
const ghost = process.platform !== 'linux' ? null : entryChangedAfterStart || (gitStatus === '' && startEpoch !== null && commitEpoch !== null && startEpoch < commitEpoch)
const resolvedHome = targetEnv.DSH_HOME || (targetEnv.HOME ? resolve(targetEnv.HOME, '.dsh') : null)
console.log(JSON.stringify({
  pid,
  argv: cmdline,
  startEpoch,
  checkout,
  checkoutCommitEpoch: commitEpoch,
  ghostHost: ghost,
  dshHome: resolvedHome,
  dshHomeSource: targetEnv.DSH_HOME ? 'target-env' : targetEnv.HOME ? 'target-home/.dsh' : 'unknown',
  gitDirty: gitStatus !== '',
  entryPath,
  exePath,
  entryMtime,
  entryChangedAfterStart,
  profileArg: (() => { const i = cmdline.indexOf('--profile'); if (i >= 0) return cmdline[i + 1]; const eq = cmdline.find(v => v.startsWith('--profile=')); if (eq) return eq.slice('--profile='.length); return cmdline.includes('web') ? 'web (default)' : null })(),
  portFromArgv,
  platform: process.platform,
  packageName: pkg.name || null,
  packageVersion: pkg.version || null,
  port,
  portOpen,
  notes: process.platform !== 'linux' ? ['process start/ghost and /proc inspection are only supported on Linux'] : ghost ? ['process may be running old code (start older than commit or entry changed after start)'] : gitStatus !== '' ? ['working tree is dirty; ghost verdict is conservative/uncertain'] : [],
}, null, 2))
