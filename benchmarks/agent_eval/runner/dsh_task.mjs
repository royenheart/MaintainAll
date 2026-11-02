import { pathToFileURL } from 'node:url'
const root = process.env.DSH_HARNESS_ROOT
if (!root) throw new Error('DSH_HARNESS_ROOT is required')
const { DeepSeekHarness } = await import(pathToFileURL(`${root}/packages/sdk/client/lib/index.js`).href)
import { readFileSync, existsSync } from 'node:fs'

const prompt = readFileSync('/work/prompt.txt', 'utf8').trim()
import { readFileSync as readMode } from 'node:fs'
const mode = readMode('/runner/mode', 'utf8').trim()
if (mode !== 'with' && mode !== 'without') throw new Error('mode file must be with or without')
const maxTokens = Number(process.env.AB_MAX_TOKENS ?? '32768')
const maxToolCalls = Number(process.env.AB_MAX_TOOL_CALLS ?? '0')
const harness = new DeepSeekHarness({
  dshBin: `${root}/apps/cli/lib/bin.js`,
  profile: 'sdk',
  patches: ['/work/profile.patch.yml', ...(existsSync('/work/extra.patch.yml') ? ['/work/extra.patch.yml'] : [])],
  dshHome: '/work/engine-home',
  processCwd: '/work/repo',
  cwd: '/work/repo',
  provider: 'deepseek-official',
  model: process.env.AB_MODEL ?? 'deepseek-v4.1-flash',
  maxTokens,
  requestTimeoutMs: Number(process.env.AB_TIMEOUT_MS ?? '1200000'),
  env: process.env,
})
try {
  let callsSeen = 0
  const result = await harness.run(prompt, {
    onNotification(notification) {
      if (notification.method !== 'session.event') return
      const event = notification.params?.event
      if (event?.type !== 'tool/call') return
      callsSeen += 1
      if (maxToolCalls > 0 && callsSeen > maxToolCalls) {
        process.stderr.write(`tool-call budget exceeded during run: ${callsSeen} > ${maxToolCalls}\n`)
        process.stdout.write('BENCH_RESULT ' + JSON.stringify({
          sessionId: null, finalResponse: '', events: [],
          budget: { toolCalls: callsSeen, maxToolCalls, exceeded: true },
          error: 'tool-call budget exceeded during run',
        }) + '\n')
        process.exit(2)
      }
    },
  })
  const toolCalls = result.events.filter(event => event.type === 'tool/call').length
  const budget = { toolCalls, maxToolCalls, exceeded: maxToolCalls > 0 && toolCalls > maxToolCalls }
  process.stdout.write('BENCH_RESULT ' + JSON.stringify({
    sessionId: result.sessionId,
    finalResponse: result.finalResponse,
    events: result.events,
    notifications: result.notifications,
    budget,
  }) + '\n')
} catch (error) {
  process.stdout.write('BENCH_RESULT ' + JSON.stringify({ error: String(error?.stack ?? error) }) + '\n')
  process.exitCode = 1
} finally {
  await harness.close().catch(() => {})
}
