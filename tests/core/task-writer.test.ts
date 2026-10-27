import { test } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import { mkdtemp, readdir, readFile, rm, stat } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import type { TaskManifest, TaskTrigger } from '../../src/core/contract.ts'
import {
  listTaskAssets,
  readTaskAsset,
  writeTaskAsset,
  writeTaskMeta,
  type TaskAssetInput,
} from '../../src/core/task-writer.ts'

function sampleManifest(id: string): TaskManifest {
  return {
    format: 'dsh-opskit/1',
    id,
    name: 'Restart nginx',
    description: 'Restart nginx when the config changes',
    version: '1.2.3',
    requires: { dsh: '>=0.1.0', tools: ['bash'] },
    bindings: { agentPreset: { hint: 'standard' } },
  }
}

function sampleTriggers(): TaskTrigger[] {
  return [
    {
      id: 'cron',
      source: 'schedule',
      params: { cron: '*/5 * * * *' },
      enabled: true,
    },
    {
      id: 'log',
      source: 'filewatch',
      filter: { path: '/var/log/nginx/error.log' },
      when: "event.payload.level == 'error'",
      rate: { minIntervalSeconds: 60, maxPerHour: 5 },
      enabled: false,
    },
  ]
}

function sampleInput(id = 'restart-nginx'): TaskAssetInput {
  return {
    manifest: sampleManifest(id),
    agensMd: '# Restart nginx\n\n1. Check config\n2. Restart\n',
    skills: new Map([
      ['.agents/skills/nginx/SKILL.md', '# nginx skill\n'],
      ['.agents/skills/nginx/refs/commands.md', 'systemctl restart nginx\n'],
    ]),
    scripts: new Map([['scripts/restart.sh', '#!/bin/sh\nsystemctl restart nginx\n']]),
    seed: {
      cwd: '/work/ops',
      events: [
        { type: 'turn/start', seq: 1, data: { at: '2026-08-23T00:00:00Z' } },
        { type: 'user/message', seq: 2, data: { content: 'restart nginx' } },
        { type: 'turn/end', seq: 3 },
      ],
    },
    triggers: sampleTriggers(),
  }
}

async function tempRoot(t: import('node:test').TestContext): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), 'maintainall-task-writer-'))
  t.after(() => rm(root, { recursive: true, force: true }))
  return root
}

async function walkFiles(dir: string): Promise<string[]> {
  const out: string[] = []
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const abs = join(dir, entry.name)
    if (entry.isDirectory()) out.push(...(await walkFiles(abs)))
    else out.push(abs)
  }
  return out
}

test('writeTaskAsset/readTaskAsset round-trip', async (t) => {
  const root = await tempRoot(t)
  const input = sampleInput()
  const taskDir = await writeTaskAsset(root, input)
  assert.equal(taskDir, join(root, 'ops', 'restart-nginx'))

  const asset = await readTaskAsset(root, 'restart-nginx')
  assert.deepEqual(asset.manifest, input.manifest)
  assert.equal(asset.agensMd, input.agensMd)
  assert.deepEqual(asset.skills, input.skills)
  assert.deepEqual(asset.scripts, input.scripts)
  assert.deepEqual(asset.seed, input.seed)
  assert.deepEqual(asset.triggers, input.triggers)

  // Layout directories exist even for populated assets.
  assert.ok((await stat(join(taskDir, 'runs'))).isDirectory())
  assert.ok((await stat(join(taskDir, '.agents', 'skills'))).isDirectory())
  assert.ok((await stat(join(taskDir, 'scripts'))).isDirectory())
})

test('writeTaskAsset accepts empty skills/scripts maps', async (t) => {
  const root = await tempRoot(t)
  const input = { ...sampleInput('empty-assets'), skills: new Map(), scripts: new Map() }
  const taskDir = await writeTaskAsset(root, input)
  assert.ok((await stat(join(taskDir, '.agents', 'skills'))).isDirectory())
  assert.ok((await stat(join(taskDir, 'scripts'))).isDirectory())

  const asset = await readTaskAsset(root, 'empty-assets')
  assert.deepEqual(asset.skills, new Map())
  assert.deepEqual(asset.scripts, new Map())
})

test('seed file format: session header line, then one JSON event per line', async (t) => {
  const root = await tempRoot(t)
  const input = sampleInput()
  await writeTaskAsset(root, input)
  const seed = input.seed
  assert.ok(seed !== undefined && seed !== null)

  const text = await readFile(join(root, 'ops', 'restart-nginx', 'seed', 'session.jsonl'), 'utf8')
  const lines = text.split('\n')
  assert.equal(lines[0], '{"type":"session","cwd":"/work/ops"}')
  assert.equal(lines.length, 1 + seed.events.length + 1) // trailing newline
  assert.equal(lines.at(-1), '')
  for (const [i, event] of seed.events.entries()) {
    assert.deepEqual(JSON.parse(lines[i + 1]), event)
  }
})

test('writeTaskMeta updates metadata files only and keeps seed/skills/scripts/runs', async (t) => {
  const root = await tempRoot(t)
  const input = sampleInput()
  const taskDir = await writeTaskAsset(root, input)

  await writeTaskMeta(taskDir, {
    manifest: { ...input.manifest, name: 'Restart nginx v2', icon: '⚡' },
    agensMd: '# Updated runbook',
    triggers: [{ id: 't1', source: 'exec', params: { command: 'systemctl restart nginx' }, enabled: false }],
  })

  const asset = await readTaskAsset(root, 'restart-nginx')
  assert.equal(asset.manifest.name, 'Restart nginx v2')
  assert.equal(asset.manifest.icon, '⚡')
  assert.equal(asset.agensMd, '# Updated runbook')
  assert.deepEqual(asset.triggers, [
    { id: 't1', source: 'exec', enabled: false, filter: { command: 'systemctl restart nginx' } },
  ])
  assert.deepEqual(asset.seed, input.seed)
  assert.deepEqual(asset.skills, input.skills)
  assert.deepEqual(asset.scripts, input.scripts)
  assert.ok((await stat(join(taskDir, 'seed', 'session.jsonl'))).isFile())
  assert.ok((await stat(join(taskDir, 'runs'))).isDirectory())
  assert.ok((await stat(join(taskDir, '.agents', 'skills'))).isDirectory())
  assert.ok((await stat(join(taskDir, 'scripts'))).isDirectory())
})

test('writes are atomic: no tmp files remain under the task directory', async (t) => {
  const root = await tempRoot(t)
  await writeTaskAsset(root, sampleInput())
  const files = await walkFiles(root)
  assert.ok(files.length > 0)
  for (const file of files) {
    assert.ok(!file.includes('.tmp-'), `leftover tmp file: ${file}`)
  }
})

test('listTaskAssets returns sorted task ids', async (t) => {
  const root = await tempRoot(t)
  await writeTaskAsset(root, sampleInput('zeta-task'))
  await writeTaskAsset(root, sampleInput('alpha-task'))
  await writeTaskAsset(root, sampleInput('mid-task'))
  assert.deepEqual(await listTaskAssets(root), ['alpha-task', 'mid-task', 'zeta-task'])
})

test('listTaskAssets returns [] when ops/ does not exist', async (t) => {
  const root = await tempRoot(t)
  assert.deepEqual(await listTaskAssets(root), [])
})

test('writeTaskAsset: rejects reserved/escaping asset paths without a partial task', async (t) => {
  const root = await tempRoot(t)
  const input = sampleInput('unsafe-asset')
  input.scripts = new Map([['manifest.yml', 'format: EVIL\n']])
  await assert.rejects(writeTaskAsset(root, input), /unsafe task asset path/)
  assert.equal(existsSync(join(root, 'ops', 'unsafe-asset')), false)
})

test('writeTaskAsset: concurrent same-id writes have one winner', async (t) => {
  const root = await tempRoot(t)
  const a = sampleInput('race-task')
  const b = sampleInput('race-task')
  a.agensMd = '# A\n'
  b.agensMd = '# B\n'
  const results = await Promise.allSettled([writeTaskAsset(root, a), writeTaskAsset(root, b)])
  assert.equal(results.filter((result) => result.status === 'fulfilled').length, 1)
  assert.equal(results.filter((result) => result.status === 'rejected').length, 1)
})
