import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  extractSeedEvents,
  filterRegeneratedContext,
  filterSeedTools,
  rewriteSeedCwd,
  validateSeedCwd,
} from '../../src/core/seed.ts'
import type { SeedEvent, TaskSeed } from '../../src/core/contract.ts'

function event(seq: number, type: string, data?: unknown): SeedEvent {
  return data === undefined ? { seq, type } : { seq, type, data }
}

test('extractSeedEvents: boundary cut keeps only seq <= boundary', () => {
  const events = [
    event(1, 'turn/start'),
    event(2, 'user/message', { text: 'a' }),
    event(3, 'turn/end'),
    event(4, 'turn/start'),
    event(5, 'user/message', { text: 'b' }),
  ]
  const seed = extractSeedEvents(events, 3)
  assert.deepEqual(
    seed.map((e) => e.seq),
    [1, 2, 3],
  )
})

test('extractSeedEvents: a cut inside an open turn yields no dangling seed', () => {
  const events = [
    event(1, 'turn/start'),
    event(2, 'user/message', { text: 'a' }),
    event(3, 'assistant/message', { message: { content: [{ type: 'tool-call', id: 'c1' }] } }),
    event(4, 'tool/call', { callId: 'c1' }),
  ]
  assert.deepEqual(extractSeedEvents(events, 4), [])
})

test('extractSeedEvents: keeps only durable event types, preserving order', () => {
  const events = [
    event(1, 'turn/start'),
    event(2, 'session/meta', { noisy: true }),
    event(3, 'assistant/message', { content: [] }),
    event(4, 'model/thinking', { noisy: true }),
    event(5, 'turn/end'),
  ]
  const seed = extractSeedEvents(events, 5)
  assert.deepEqual(
    seed.map((e) => e.type),
    ['turn/start', 'assistant/message', 'turn/end'],
  )
})

test('extractSeedEvents: throws on non-contiguous seq', () => {
  const events = [event(1, 'turn/start'), event(3, 'turn/end')]
  assert.throws(() => extractSeedEvents(events, 3), /contiguous/)
})

test('rewriteSeedCwd: remaps executable tool-call arguments only', () => {
  const seed: TaskSeed = {
    cwd: '/old/host/project',
    events: [
      event(1, 'user/message', { message: { content: [{ type: 'text', text: 'check /old/host/project/logs' }] } }),
      event(2, 'tool/call', {
        callId: 'c1',
        name: 'bash',
        arguments: JSON.stringify({
          command: 'ls /old/host/project',
          workdir: '/old/host/project',
          paths: ['/old/host/project/a', '/etc'],
          content: '/old/host/project is literal file content',
          data: { command: 'cat /old/host/project/secret', path: '/old/host/project/literal' },
        }),
      }),
      event(3, 'tool/result', { callId: 'c1', output: 'done in /old/host/project', meta: { path: '/old/host/project' } }),
    ],
  }
  const rewritten = rewriteSeedCwd(seed, '/old/host/project', '/new/host/project')
  assert.equal(rewritten.cwd, '/new/host/project')
  const call = rewritten.events[1].data as { arguments: string }
  const args = JSON.parse(call.arguments) as { command: string; workdir: string; paths: string[]; content: string; data: unknown }
  assert.equal(args.command, 'ls /new/host/project')
  assert.equal(args.workdir, '/new/host/project')
  assert.deepEqual(args.paths, ['/new/host/project/a', '/etc'])
  assert.equal(args.content, '/old/host/project is literal file content')
  assert.deepEqual(args.data, { command: 'cat /old/host/project/secret', path: '/old/host/project/literal' })
  assert.equal((rewritten.events[0].data as { message: { content: [{ text: string }] } }).message.content[0].text, 'check /old/host/project/logs')
  assert.equal((rewritten.events[2].data as { output: string }).output, 'done in /old/host/project')
  assert.deepEqual((rewritten.events[2].data as { meta: unknown }).meta, { path: '/old/host/project' })
  assert.equal(seed.cwd, '/old/host/project')
})

test('rewriteSeedCwd: refuses shell remapping into a metacharacter cwd', () => {
  const seed: TaskSeed = {
    cwd: '/old/project',
    events: [
      event(0, 'tool/call', {
        callId: 'c1',
        name: 'bash',
        arguments: JSON.stringify({ command: 'cd /old/project && ls' }),
      }),
    ],
  }
  assert.throws(
    () => rewriteSeedCwd(seed, '/old/project', '/run/My Data'),
    /shell metacharacters/,
  )
  const windows: TaskSeed = {
    cwd: 'C:\\Ops\\App',
    events: [event(0, 'tool/call', { arguments: JSON.stringify({ command: 'cd c:/ops/app && ls' }) })],
  }
  assert.throws(
    () => rewriteSeedCwd(windows, 'C:\\Ops\\App', 'C:\\run\\My Data'),
    /shell metacharacters/,
  )
  const uri: TaskSeed = {
    cwd: '/srv/app',
    events: [event(0, 'tool/call', { arguments: JSON.stringify({ command: 'curl file:///srv/app/x' }) })],
  }
  assert.throws(
    () => rewriteSeedCwd(uri, '/srv/app', "/run/a'b"),
    /shell metacharacters/,
  )
})

test('rewriteSeedCwd: handles raw JSON escaping and path fields', () => {
  const seed: TaskSeed = {
    cwd: 'C:\\ops\\app',
    events: [event(1, 'tool/call', {
      callId: 'c1',
      name: 'filesystem',
      arguments: JSON.stringify({
        file_path: 'c:\\ops\\app\\x.txt',
        command: 'Get-Content c:\\ops\\app\\x.txt',
        content: 'C:\\ops\\app is literal content',
      }),
    })],
  }
  const rewritten = rewriteSeedCwd(seed, 'C:\\ops\\app', 'D:\\run\\app')
  const args = JSON.parse((rewritten.events[0].data as { arguments: string }).arguments) as {
    file_path: string
    command: string
    content: string
  }
  assert.equal(args.file_path, 'D:\\run\\app\\x.txt')
  assert.equal(args.command, 'Get-Content D:\\run\\app\\x.txt')
  assert.equal(args.content, 'C:\\ops\\app is literal content')
  const escaped = rewriteSeedCwd({
    cwd: '/srv/app',
    events: [event(1, 'tool/call', { callId: 'c2', arguments: '{"command":"cat \\u002fsrv/app/x"}' })],
  }, '/srv/app', '/run/app')
  assert.equal(JSON.parse((escaped.events[0].data as { arguments: string }).arguments).command, 'cat /run/app/x')
  const uri = rewriteSeedCwd({
    cwd: '/srv/app space',
    events: [event(1, 'tool/call', { callId: 'c3', arguments: JSON.stringify({ uri: 'file:///srv/app%20space/x' }) })],
  }, '/srv/app space', '/run/app')
  assert.equal(JSON.parse((uri.events[0].data as { arguments: string }).arguments).uri, 'file:///run/app/x')
  const encodedCommand = rewriteSeedCwd({
    cwd: '/srv/app space',
    events: [event(1, 'tool/call', { arguments: JSON.stringify({ command: 'curl file:///srv/app%20space/x' }) })],
  }, '/srv/app space', '/run/app')
  assert.equal(JSON.parse((encodedCommand.events[0].data as { arguments: string }).arguments).command, 'curl file:///run/app/x')
  const literalPercent = rewriteSeedCwd({
    cwd: '/srv/app space',
    events: [event(1, 'tool/call', { arguments: JSON.stringify({ command: 'rm -rf /srv/app%20space/cache' }) })],
  }, '/srv/app space', '/run/app')
  assert.equal(JSON.parse((literalPercent.events[0].data as { arguments: string }).arguments).command, 'rm -rf /srv/app%20space/cache')
  const reservedTarget = rewriteSeedCwd({
    cwd: '/srv/app space',
    events: [event(1, 'tool/call', { arguments: JSON.stringify({ command: 'curl file:///srv/app%20space/cache' }) })],
  }, '/srv/app space', '/run/a#b')
  assert.equal(JSON.parse((reservedTarget.events[0].data as { arguments: string }).arguments).command, 'curl file:///run/a%23b/cache')
  const colonPath = rewriteSeedCwd({
    cwd: '/srv/app:space',
    events: [event(1, 'tool/call', { arguments: JSON.stringify({ command: 'curl file:///srv/app%3Aspace/x' }) })],
  }, '/srv/app:space', '/run/app')
  assert.equal(JSON.parse((colonPath.events[0].data as { arguments: string }).arguments).command, 'curl file:///run/app/x')
  const colonSpacePath = rewriteSeedCwd({
    cwd: '/srv/app:space dir',
    events: [event(1, 'tool/call', { arguments: JSON.stringify({ command: 'curl file:///srv/app:space%20dir/x' }) })],
  }, '/srv/app:space dir', '/run/app')
  assert.equal(JSON.parse((colonSpacePath.events[0].data as { arguments: string }).arguments).command, 'curl file:///run/app/x')
  const siblingColon = rewriteSeedCwd({
    cwd: '/srv/app:space dir',
    events: [event(1, 'tool/call', { arguments: JSON.stringify({ command: 'curl file:///srv/app:space%20dir:backup/x' }) })],
  }, '/srv/app:space dir', '/run/app')
  assert.equal(JSON.parse((siblingColon.events[0].data as { arguments: string }).arguments).command, 'curl file:///srv/app:space%20dir:backup/x')
  const unicodeSibling = rewriteSeedCwd({
    cwd: '/srv/app',
    events: [event(1, 'tool/call', { arguments: JSON.stringify({ command: 'curl file:///srv/appé/x' }) })],
  }, '/srv/app', '/run/app')
  assert.equal(JSON.parse((unicodeSibling.events[0].data as { arguments: string }).arguments).command, 'curl file:///srv/appé/x')
  const quotedSibling = rewriteSeedCwd({
    cwd: '/srv/app',
    events: [event(1, 'tool/call', { arguments: JSON.stringify({ command: "curl 'file:///srv/app)backup/x'" }) })],
  }, '/srv/app', '/run/app')
  assert.equal(JSON.parse((quotedSibling.events[0].data as { arguments: string }).arguments).command, "curl 'file:///srv/app)backup/x'")
  const quotedUri = rewriteSeedCwd({
    cwd: '/srv/app',
    events: [event(1, 'tool/call', { arguments: JSON.stringify({ command: "curl 'file:///srv/app'" }) })],
  }, '/srv/app', '/run/app')
  assert.equal(JSON.parse((quotedUri.events[0].data as { arguments: string }).arguments).command, "curl 'file:///run/app'")
  const substitutionUri = rewriteSeedCwd({
    cwd: '/srv/app',
    events: [event(1, 'tool/call', { arguments: JSON.stringify({ command: 'x=$(curl file:///srv/app)' }) })],
  }, '/srv/app', '/run/app')
  assert.equal(JSON.parse((substitutionUri.events[0].data as { arguments: string }).arguments).command, 'x=$(curl file:///run/app)')
  const quotedParam = rewriteSeedCwd({
    cwd: '/srv/app',
    events: [event(1, 'tool/call', { arguments: JSON.stringify({ command: 'curl "${URI:-file:///srv/app}"' }) })],
  }, '/srv/app', '/run/app')
  assert.equal(JSON.parse((quotedParam.events[0].data as { arguments: string }).arguments).command, 'curl "${URI:-file:///run/app}"')
  const quotedBrace = rewriteSeedCwd({
    cwd: '/srv/app',
    events: [event(1, 'tool/call', { arguments: JSON.stringify({ command: 'curl -g ${X:-"file:///srv/app}backup"}' }) })],
  }, '/srv/app', '/run/app')
  assert.equal(JSON.parse((quotedBrace.events[0].data as { arguments: string }).arguments).command, 'curl -g ${X:-"file:///srv/app}backup"}')
  const separatorUri = rewriteSeedCwd({
    cwd: '/srv/app',
    events: [event(1, 'tool/call', { arguments: JSON.stringify({ command: 'curl file:///srv/app; echo ok' }) })],
  }, '/srv/app', '/run/app')
  assert.equal(JSON.parse((separatorUri.events[0].data as { arguments: string }).arguments).command, 'curl file:///run/app; echo ok')
  const windowsEncoded = rewriteSeedCwd({
    cwd: 'C:\\ops\\app space',
    events: [event(1, 'tool/call', { arguments: JSON.stringify({ command: 'Get-Content file:///C:/ops/app%20space/x' }) })],
  }, 'C:\\ops\\app space', 'D:\\run\\app')
  assert.equal(JSON.parse((windowsEncoded.events[0].data as { arguments: string }).arguments).command, 'Get-Content file:///D:/run/app/x')
})

test('rewriteSeedCwd: leaves arguments with unsafe JSON numbers untouched', () => {
  const raw = '{"command":"ls /srv/app","n":9007199254740993}'
  const seed: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { callId: 'c1', arguments: raw })] }
  const rewritten = rewriteSeedCwd(seed, '/srv/app', '/run/app')
  assert.equal((rewritten.events[0].data as { arguments: string }).arguments, raw)
  const underflow = '{"command":"ls /srv/app","n":1e-400}'
  assert.equal((rewriteSeedCwd({ cwd: '/srv/app', events: [event(1, 'tool/call', { arguments: underflow })] }, '/srv/app', '/run/app').events[0].data as { arguments: string }).arguments, underflow)
  const uuid = JSON.stringify({ file_path: '/srv/app/x', content: 'token 550e8400-e29b' })
  const uuidOut = rewriteSeedCwd({ cwd: '/srv/app', events: [event(1, 'tool/call', { arguments: uuid })] }, '/srv/app', '/run/app')
  assert.equal(JSON.parse((uuidOut.events[0].data as { arguments: string }).arguments).file_path, '/run/app/x')
  const exponent = '{"file_path":"/srv/app/x","n":1e5}'
  const exponentOut = rewriteSeedCwd({ cwd: '/srv/app', events: [event(1, 'tool/call', { arguments: exponent })] }, '/srv/app', '/run/app')
  assert.deepEqual(JSON.parse((exponentOut.events[0].data as { arguments: string }).arguments), { file_path: '/run/app/x', n: 100000 })
  const exactInteger = '{"file_path":"/srv/app/x","n":9007199254740992}'
  const exactOut = rewriteSeedCwd({ cwd: '/srv/app', events: [event(1, 'tool/call', { arguments: exactInteger })] }, '/srv/app', '/run/app')
  assert.equal(JSON.parse((exactOut.events[0].data as { arguments: string }).arguments).file_path, '/run/app/x')
})

test('rewriteSeedCwd: keeps assistant tool-call arguments equal and clears changed streams', () => {
  const argumentsText = JSON.stringify({ command: 'cat /srv/app/x' })
  const seed: TaskSeed = {
    cwd: '/srv/app',
    events: [
      event(1, 'assistant/message', {
        message: { content: [{ type: 'tool-call', id: 'c1', name: 'bash', arguments: argumentsText }] },
        stream: [{ delta: 'cat /srv/app/x' }],
      }),
      event(2, 'tool/call', { callId: 'c1', name: 'bash', arguments: argumentsText }),
    ],
  }
  const rewritten = rewriteSeedCwd(seed, '/srv/app', '/run/app')
  const block = (rewritten.events[0].data as { message: { content: [{ arguments: string }] } }).message.content[0]
  const call = rewritten.events[1].data as { arguments: string }
  assert.equal(block.arguments, call.arguments)
  assert.equal(JSON.parse(call.arguments).command, 'cat /run/app/x')
  assert.deepEqual((rewritten.events[0].data as { stream: unknown[] }).stream, [])
})

test('validateSeedCwd: rejects relative, control, and oversized cwd values', () => {
  assert.equal(validateSeedCwd('/srv/app'), '/srv/app')
  assert.equal(validateSeedCwd('C:\\ops\\app'), 'C:\\ops\\app')
  assert.throws(() => validateSeedCwd('relative/path'), /absolute/)
  assert.throws(() => validateSeedCwd('/srv/app\nnext'), /control/)
  assert.throws(() => validateSeedCwd('/' + 'a'.repeat(4096)), /too long/)
  assert.throws(() => validateSeedCwd('/'), /filesystem root/)
  assert.throws(() => validateSeedCwd('C:\\'), /filesystem root/)
  assert.throws(() => validateSeedCwd('//'), /filesystem root/)
  assert.throws(() => validateSeedCwd('/srv/..'), /filesystem root/)
  assert.throws(() => validateSeedCwd('C:\\\\'), /filesystem root/)
  assert.throws(() => validateSeedCwd('\\\\server\\share'), /filesystem root/)
  assert.throws(() => validateSeedCwd('\\\\?\\C:\\'), /filesystem root/)
})

test('filterRegeneratedContext: drops capture environment context only', () => {
  const events = [
    event(1, 'user/message', { message: { source: { form: 'snapshot' }, content: [] } }),
    event(2, 'user/message', { message: { source: { form: 'catalog' }, content: [] } }),
    event(3, 'user/message', { message: { source: { kind: 'agent-instructions' }, content: [] } }),
    event(4, 'user/message', { message: { source: { kind: 'runtime-context' }, content: [] } }),
    event(5, 'user/message', { message: { source: { kind: 'user' }, content: [] } }),
    event(6, 'user/message', { message: { content: [] } }),
  ]
  assert.deepEqual(filterRegeneratedContext(events).map((e) => e.seq), [5, 6])
})

test('rewriteSeedCwd: does not rewrite sibling prefixes', () => {
  const seed: TaskSeed = {
    cwd: '/srv/app',
    events: [event(1, 'tool/call', { command: 'ls /srv/app-backup /srv/app/logs' })],
  }
  const rewritten = rewriteSeedCwd(seed, '/srv/app', '/run/app')
  assert.equal((rewritten.events[0].data as { command: string }).command, 'ls /srv/app-backup /run/app/logs')
  const nested: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'cat /backup/srv/app/config' })] }
  assert.equal((rewriteSeedCwd(nested, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'cat /backup/srv/app/config')
  const shell: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'cd /srv/app&&./run.sh' })] }
  assert.equal((rewriteSeedCwd(shell, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'cd /run/app&&./run.sh')
  const parameter: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'X=${X:-/srv/app}' })] }
  assert.equal((rewriteSeedCwd(parameter, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'X=${X:-/run/app}')
  const fileUri: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'curl file:///srv/app/data' })] }
  assert.equal((rewriteSeedCwd(fileUri, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'curl file:///run/app/data')
  const nestedFileUri: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'curl file:/srv/app/data' })] }
  assert.equal((rewriteSeedCwd(nestedFileUri, '/srv/app', '/srv/app/.dsh/run').events[0].data as { command: string }).command, 'curl file:/srv/app/.dsh/run/data')
  const posixBackslash: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'cat /srv/app\\backup/x /srv\\app/y /srv/app/z' })] }
  assert.equal((rewriteSeedCwd(posixBackslash, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'cat /srv/app\\backup/x /srv\\app/y /run/app/z')
  const notCwd: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'cat ~/srv/app/logs /backup-/srv/app/logs' })] }
  assert.equal((rewriteSeedCwd(notCwd, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'cat ~/srv/app/logs /backup-/srv/app/logs')
  const list: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'arr=[/srv/app,/srv/app/x]' })] }
  assert.equal((rewriteSeedCwd(list, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'arr=[/run/app,/run/app/x]')
  const variablePrefix: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'cat ${BACKUP_ROOT}/srv/app/logs' })] }
  assert.equal((rewriteSeedCwd(variablePrefix, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'cat ${BACKUP_ROOT}/srv/app/logs')
  const parameterSibling: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'X=${X:-/backup-/srv/app/logs}' })] }
  assert.equal((rewriteSeedCwd(parameterSibling, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'X=${X:-/backup-/srv/app/logs}')
  const parameterAlternate: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'X=${X:+/srv/app}' })] }
  assert.equal((rewriteSeedCwd(parameterAlternate, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'X=${X:+/run/app}')
  const mixedQuotes: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: `printf '%s\n' "it's fine"; cat '/srv/app/config'` })] }
  assert.equal((rewriteSeedCwd(mixedQuotes, '/srv/app', '/run/app').events[0].data as { command: string }).command, `printf '%s\n' "it's fine"; cat '/run/app/config'`)
  const substitution: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'x="$(cat \'/srv/app/config\')"; y=`cat \'/srv/app/config\'`; bash -c "cd \'/srv/app\' && cat \'/srv/app/x\'"; z=$(printf \')\'); cat \'/srv/app/z\'' })] }
  assert.equal((rewriteSeedCwd(substitution, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'x="$(cat \'/run/app/config\')"; y=`cat \'/run/app/config\'`; bash -c "cd \'/run/app\' && cat \'/run/app/x\'"; z=$(printf \')\'); cat \'/run/app/z\'')
  const backtick: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: '`/srv/app/bin/check`' })] }
  assert.equal((rewriteSeedCwd(backtick, '/srv/app', '/run/app').events[0].data as { command: string }).command, '`/run/app/bin/check`')
  const backtickSuffix: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'cp `printf /backup`\'/srv/app/logs\' .' })] }
  assert.equal((rewriteSeedCwd(backtickSuffix, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'cp `printf /backup`\'/srv/app/logs\' .')
  const dollarQuote: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'echo $\'/srv/app\' foo$\'/srv/app\'' })] }
  assert.equal((rewriteSeedCwd(dollarQuote, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'echo $\'/run/app\' foo$\'/srv/app\'')
  const ansiQuote: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'x=$(printf $\'it\\\'s\'); cat \'/srv/app/config\'' })] }
  assert.equal((rewriteSeedCwd(ansiQuote, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'x=$(printf $\'it\\\'s\'); cat \'/run/app/config\'')
  const backtickDollar: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'x=`$\'/srv/app/bin/check\'`' })] }
  assert.equal((rewriteSeedCwd(backtickDollar, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'x=`$\'/run/app/bin/check\'`')
  const escapedDollar: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'echo \\$\'abc\\\' \'/srv/app/config\'' })] }
  assert.equal((rewriteSeedCwd(escapedDollar, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'echo \\$\'abc\\\' \'/run/app/config\'')
  const tripleDollar: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'echo $$$\'it\\\'s\'; cat \'/srv/app/config\'' })] }
  assert.equal((rewriteSeedCwd(tripleDollar, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'echo $$$\'it\\\'s\'; cat \'/run/app/config\'')
  const escapedDollarWord: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'echo \\$$\'aa\\\' \'/srv/app/config\'' })] }
  assert.equal((rewriteSeedCwd(escapedDollarWord, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'echo \\$$\'aa\\\' \'/srv/app/config\'')
  const concatenatedQuote: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'foo"/srv/app"' })] }
  assert.equal((rewriteSeedCwd(concatenatedQuote, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'foo"/srv/app"')
  const unicodeSpace: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: '\u00a0/srv/app/x' })] }
  assert.equal((rewriteSeedCwd(unicodeSpace, '/srv/app', '/run/app').events[0].data as { command: string }).command, '\u00a0/run/app/x')
  const arraySubscript: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'X=${X[-1]:-/srv/app}' })] }
  assert.equal((rewriteSeedCwd(arraySubscript, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'X=${X[-1]:-/run/app}')
  const positional: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'cat ${1:-/srv/app} ${!REF:-/srv/app} ${X[0]:-/srv/app}' })] }
  assert.equal((rewriteSeedCwd(positional, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'cat ${1:-/run/app} ${!REF:-/run/app} ${X[0]:-/run/app}')
  const quotedVariable: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'cp "${BACKUP_ROOT}"/srv/app/logs .' })] }
  assert.equal((rewriteSeedCwd(quotedVariable, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'cp "${BACKUP_ROOT}"/srv/app/logs .')
  const fileAuthority: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'curl file://srv/app/config' })] }
  assert.equal((rewriteSeedCwd(fileAuthority, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'curl file://srv/app/config')
  const colonNoGuess: TaskSeed = { cwd: '/srv/app', events: [event(1, 'tool/call', { command: 'PATH=x:"/srv/app/bin" PATH=/opt/file:/srv/app profile:/srv/app' })] }
  assert.equal((rewriteSeedCwd(colonNoGuess, '/srv/app', '/run/app').events[0].data as { command: string }).command, 'PATH=x:"/srv/app/bin" PATH=/opt/file:/srv/app profile:/srv/app')
  const windows: TaskSeed = { cwd: 'C:\\ops\\app', events: [event(1, 'tool/call', { command: 'Get-Content C:\\ops\\app\\scripts\\check.ps1' })] }
  assert.equal((rewriteSeedCwd(windows, 'C:\\ops\\app', 'D:\\run\\app').events[0].data as { command: string }).command, 'Get-Content D:\\run\\app\\scripts\\check.ps1')
  const windowsSlash: TaskSeed = { cwd: 'C:\\ops\\app', events: [event(1, 'tool/call', { command: 'Get-Content C:/ops/app/scripts/check.ps1 file:///C:/ops/app/data' })] }
  assert.equal((rewriteSeedCwd(windowsSlash, 'C:\\ops\\app', 'D:/run/app').events[0].data as { command: string }).command, 'Get-Content D:/run/app/scripts/check.ps1 file:///D:/run/app/data')
  const windowsSingleSlash: TaskSeed = { cwd: 'C:\\ops\\app', events: [event(1, 'tool/call', { command: 'Get-Content file:/C:/ops/app/data file:/C:\\ops\\app\\data file://C:/ops/app/data' })] }
  assert.equal((rewriteSeedCwd(windowsSingleSlash, 'C:\\ops\\app', 'D:/run/app').events[0].data as { command: string }).command, 'Get-Content file:/D:/run/app/data file:/D:/run/app\\data file://D:/run/app/data')
})

test('filterSeedTools: drops unavailable calls, their results, and message blocks', () => {
  const events = [
    event(1, 'assistant/message', {
      message: {
        content: [
          { type: 'text', text: 'running two tools' },
          { type: 'tool-call', id: 'keep-1', name: 'bash' },
          { type: 'tool-call', id: 'drop-1', name: 'legacy.probe' },
        ],
      },
    }),
    event(2, 'tool/call', { id: 'keep-1', name: 'bash', args: {} }),
    event(3, 'tool/call', { id: 'drop-1', name: 'legacy.probe', args: {} }),
    event(4, 'tool/result', { message: { id: 'result-1', toolCallId: 'keep-1', content: [] } }),
    event(5, 'tool/result', { message: { id: 'result-2', toolCallId: 'drop-1', content: [] } }),
    event(7, 'tool/result', { message: { id: 'result-3', source: { kind: 'tool', callId: 'drop-1' }, content: [] } }),
    event(6, 'user/message', { text: 'next' }),
  ]
  const filtered = filterSeedTools(events, new Set(['bash']))
  assert.deepEqual(
    filtered.map((e) => e.type),
    ['assistant/message', 'tool/call', 'tool/result', 'user/message'],
  )
  assert.equal((filtered[1].data as { id: string }).id, 'keep-1')
  assert.equal(((filtered[2].data as { message: { toolCallId: string } }).message.toolCallId), 'keep-1')
  const message = (filtered[0].data as { message: { content: Array<{ type: string; id?: string }> } }).message
  assert.deepEqual(
    message.content.map((b) => b.type),
    ['text', 'tool-call'],
  )
  assert.equal(message.content[1].id, 'keep-1')
})

test('filterSeedTools: no-op when every tool is available', () => {
  const events = [
    event(1, 'tool/call', { id: 'c1', name: 'bash' }),
    event(2, 'tool/result', { callId: 'c1' }),
  ]
  const filtered = filterSeedTools(events, new Set(['bash']))
  assert.deepEqual(filtered, events)
})
