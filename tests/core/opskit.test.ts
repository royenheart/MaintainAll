import { test } from 'node:test'
import { existsSync } from 'node:fs'
import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { parse as parseYaml } from 'yaml'
import type { TaskManifest, TaskTrigger } from '../../src/core/contract.ts'
import { sha256Hex } from '../../src/core/manifest.ts'
import {
  createZip,
  exportTask,
  importTask,
  readZip,
} from '../../src/core/opskit.ts'
import {
  readTaskAsset,
  writeTaskAsset,
  type TaskAssetInput,
} from '../../src/core/task-writer.ts'

function sampleInput(id = 'restart-nginx'): TaskAssetInput {
  const manifest: TaskManifest = {
    format: 'dsh-opskit/1',
    id,
    name: 'Restart nginx',
    description: 'Restart nginx when the config changes',
    version: '1.2.3',
    requires: { dsh: '>=0.1.0', tools: ['bash'] },
    bindings: { agentPreset: { hint: 'standard' }, permissionPreset: { hint: 'readonly' } },
  }
  const triggers: TaskTrigger[] = [
    { id: 'cron', source: 'schedule', params: { cron: '*/5 * * * *' }, enabled: true },
    {
      id: 'log',
      source: 'filewatch',
      filter: { path: '/var/log/nginx/error.log' },
      when: "event.payload.level == 'error'",
      enabled: true,
    },
  ]
  return {
    manifest,
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
      ],
    },
    triggers,
  }
}

async function tempRoot(t: import('node:test').TestContext): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), 'maintainall-opskit-'))
  t.after(() => rm(root, { recursive: true, force: true }))
  return root
}

test('exportTask creates a stored zip with manifest checksums', async (t) => {
  const root = await tempRoot(t)
  const input = sampleInput()
  await writeTaskAsset(root, input)
  const outDir = join(root, 'dist')

  const zipPath = await exportTask(root, 'restart-nginx', outDir)
  assert.equal(zipPath, join(outDir, 'restart-nginx.opskit.zip'))
  assert.ok((await stat(zipPath)).isFile())

  const entries = readZip(await readFile(zipPath))
  const names = [...entries.keys()]
  assert.deepEqual(names, [
    'manifest.yml',
    'AGENTS.md',
    '.agents/skills/nginx/SKILL.md',
    '.agents/skills/nginx/refs/commands.md',
    'scripts/restart.sh',
    'seed/session.jsonl',
    'triggers.yml',
  ])
  assert.equal(entries.get('AGENTS.md')!.toString('utf8'), input.agensMd)

  const manifest = parseYaml(entries.get('manifest.yml')!.toString('utf8')) as TaskManifest
  assert.equal(manifest.id, 'restart-nginx')
  // Machine-local bindings never ship in an exported asset.
  assert.equal(manifest.bindings, undefined)
  // Checksums cover every other file in the archive.
  const checksums = manifest.checksums!
  assert.deepEqual(Object.keys(checksums).sort(), names.filter((n) => n !== 'manifest.yml').sort())
  assert.equal(checksums['AGENTS.md'], sha256Hex(input.agensMd))
  for (const [path, sum] of Object.entries(checksums)) {
    assert.equal(sha256Hex(entries.get(path)!.toString('utf8')), sum, path)
  }
})

test('importTask reads back the same files and checksums', async (t) => {
  const srcRoot = await tempRoot(t)
  const input = sampleInput()
  await writeTaskAsset(srcRoot, input)
  const zipPath = await exportTask(srcRoot, 'restart-nginx', join(srcRoot, 'dist'))

  const destRoot = await tempRoot(t)
  const result = await importTask(destRoot, zipPath)
  assert.equal(result.taskId, 'restart-nginx')
  assert.equal(result.path, join(destRoot, 'ops', 'restart-nginx'))

  const asset = await readTaskAsset(destRoot, 'restart-nginx')
  assert.equal(asset.agensMd, input.agensMd)
  assert.deepEqual(asset.skills, input.skills)
  assert.deepEqual(asset.scripts, input.scripts)
  assert.deepEqual(asset.seed, input.seed)
  // Checksums live in the zip for verification, not in the installed asset.
  assert.equal(asset.manifest.checksums, undefined)
  assert.equal(asset.manifest.id, input.manifest.id)
  assert.equal(asset.manifest.version, input.manifest.version)
})

test('importTask rejects a bad checksum', async (t) => {
  const srcRoot = await tempRoot(t)
  await writeTaskAsset(srcRoot, sampleInput())
  const zipPath = await exportTask(srcRoot, 'restart-nginx', join(srcRoot, 'dist'))

  // Tamper with AGENTS.md and rebuild the zip (fresh CRCs, stale manifest checksums).
  const entries = readZip(await readFile(zipPath))
  entries.set('AGENTS.md', Buffer.from('# tampered\n', 'utf8'))
  const badZip = join(srcRoot, 'tampered.opskit.zip')
  await writeFile(
    badZip,
    createZip([...entries].map(([name, data]) => ({ name, data }))),
  )

  const destRoot = await tempRoot(t)
  await assert.rejects(() => importTask(destRoot, badZip), /checksum mismatch.*AGENTS\.md/)
})

test('importTask rejects a zip without manifest.yml', async (t) => {
  const root = await tempRoot(t)
  const zipPath = join(root, 'no-manifest.opskit.zip')
  await writeFile(
    zipPath,
    createZip([{ name: 'AGENTS.md', data: Buffer.from('# nothing\n', 'utf8') }]),
  )
  await assert.rejects(() => importTask(root, zipPath), /missing manifest\.yml/)
})

test('importTask disables triggers by default, honors opts.enabled', async (t) => {
  const srcRoot = await tempRoot(t)
  const input = sampleInput() // all triggers enabled: true
  await writeTaskAsset(srcRoot, input)
  const zipPath = await exportTask(srcRoot, 'restart-nginx', join(srcRoot, 'dist'))

  const destRoot = await tempRoot(t)
  await importTask(destRoot, zipPath)
  const asset = await readTaskAsset(destRoot, 'restart-nginx')
  assert.equal(asset.triggers.length, 2)
  for (const trigger of asset.triggers) {
    assert.equal(trigger.enabled, false, trigger.id)
  }
  // Other trigger fields are preserved.
  assert.deepEqual(asset.triggers[0], { ...input.triggers[0], enabled: false })

  // opts.enabled: true enables the imported triggers.
  const destRoot2 = await tempRoot(t)
  await importTask(destRoot2, zipPath, { enabled: true })
  const asset2 = await readTaskAsset(destRoot2, 'restart-nginx')
  for (const trigger of asset2.triggers) {
    assert.equal(trigger.enabled, true, trigger.id)
  }
})

test('importTask rewrites bindings with machine-local presets', async (t) => {
  const srcRoot = await tempRoot(t)
  await writeTaskAsset(srcRoot, sampleInput())
  const zipPath = await exportTask(srcRoot, 'restart-nginx', join(srcRoot, 'dist'))

  const destRoot = await tempRoot(t)
  await importTask(destRoot, zipPath, {
    bindings: { agentPreset: 'ops', permissionPreset: 'readonly' },
  })
  const asset = await readTaskAsset(destRoot, 'restart-nginx')
  assert.deepEqual(asset.manifest.bindings, {
    agentPreset: { hint: 'ops' },
    permissionPreset: { hint: 'readonly' },
  })

  // Without bindings, none are written.
  const destRoot2 = await tempRoot(t)
  await importTask(destRoot2, zipPath)
  const asset2 = await readTaskAsset(destRoot2, 'restart-nginx')
  assert.equal(asset2.manifest.bindings, undefined)
})

test('importTask validates triggers before writing the asset', async (t) => {
  const srcRoot = await tempRoot(t)
  await writeTaskAsset(srcRoot, sampleInput())
  const zipPath = await exportTask(srcRoot, 'restart-nginx', join(srcRoot, 'dist'))
  const destRoot = await tempRoot(t)
  await assert.rejects(
    () => importTask(destRoot, zipPath, {
      validateTriggers: () => { throw new Error('trigger set rejected') },
    }),
    /trigger set rejected/,
  )
  assert.equal(existsSync(join(destRoot, 'ops', 'restart-nginx')), false)
})

test('importTask normalizes legacy trigger params before validation', async (t) => {
  const root = await tempRoot(t)
  const manifest = [
    'format: dsh-opskit/1',
    'id: legacy-log',
    'name: Legacy log',
    'description: Legacy filewatch asset',
    'version: 1.0.0',
  ].join('\n')
  const triggers = [
    'triggers:',
    '  - id: legacy-log-t1',
    '    source: filewatch',
    '    enabled: true',
    '    params:',
    '      path: app.log',
  ].join('\n')
  const zipPath = join(root, 'legacy.opskit.zip')
  await writeFile(zipPath, createZip([
    { name: 'manifest.yml', data: Buffer.from(manifest) },
    { name: 'AGENTS.md', data: Buffer.from('# Legacy\n') },
    { name: 'triggers.yml', data: Buffer.from(triggers) },
  ]))
  let seen: TaskTrigger[] | undefined
  const imported = await importTask(root, zipPath, {
    validateTriggers: (parsed) => { seen = parsed },
  })
  assert.deepEqual(seen?.map((trigger) => trigger.filter), [{ path: 'app.log' }])
  const asset = await readTaskAsset(root, imported.taskId)
  assert.deepEqual(asset.triggers[0]?.filter, { path: 'app.log' })
})

test('readZip: rejects directory entries carrying data', () => {
  const zip = createZip([{ name: 'dir/', data: Buffer.from('not a directory') }])
  assert.throws(() => readZip(zip), /directory entry has data/)
})
