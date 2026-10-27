import { test } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, lstatSync, mkdtempSync, mkdirSync, readdirSync, readFileSync, symlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createRunCwd, runTimestamp } from '../../src/dispatch/run-cwd.ts'

function tmpRoot(): string {
  return mkdtempSync(join(tmpdir(), 'maintainall-dispatch-run-cwd-'))
}

/** Walk every entry under `dir`, asserting none is a symlink. */
function assertNoSymlinks(dir: string): void {
  const stack = [dir]
  while (stack.length > 0) {
    const current = stack.pop() as string
    for (const entry of readdirSync(current).map((name) => join(current, name))) {
      assert.equal(lstatSync(entry).isSymbolicLink(), false, `symlink found: ${entry}`)
      if (lstatSync(entry).isDirectory()) stack.push(entry)
    }
  }
}

test('runTimestamp: formats local time as YYYYMMDD-HHMMSS', () => {
  assert.equal(runTimestamp(new Date(2026, 7, 24, 10, 30, 5)), '20260824-103005')
  assert.equal(runTimestamp(new Date(2026, 0, 2, 3, 4, 5)), '20260102-030405')
})

test('createRunCwd: creates run dir under ops/<taskId>/runs and copies task files', async () => {
  const root = tmpRoot()
  const taskDir = join(root, 'ops', 'demo-task')
  mkdirSync(join(taskDir, '.agents', 'skills', 'demo'), { recursive: true })
  mkdirSync(join(taskDir, 'scripts'), { recursive: true })
  writeFileSync(join(taskDir, 'AGENTS.md'), '# Demo task runbook\n')
  writeFileSync(join(taskDir, '.agents', 'skills', 'demo', 'SKILL.md'), '# demo skill\n')
  writeFileSync(join(taskDir, 'scripts', 'run.sh'), '#!/bin/sh\necho ok\n')

  const runCwd = await createRunCwd(root, 'demo-task', new Date(2026, 7, 24, 10, 30, 0))

  assert.ok(runCwd.startsWith(join(taskDir, 'runs')), runCwd)
  assert.match(runCwd, /20260824-103000-[0-9a-f]{8}$/, runCwd)
  assert.ok(existsSync(runCwd))
  assert.equal(readFileSync(join(runCwd, 'AGENTS.md'), 'utf8'), '# Demo task runbook\n')
  assert.equal(
    readFileSync(join(runCwd, '.agents', 'skills', 'demo', 'SKILL.md'), 'utf8'),
    '# demo skill\n',
  )
  assert.equal(readFileSync(join(runCwd, 'scripts', 'run.sh'), 'utf8'), '#!/bin/sh\necho ok\n')
})

test('createRunCwd: copies through symlinks, producing plain files', async () => {
  const root = tmpRoot()
  const taskDir = join(root, 'ops', 'demo-task')
  mkdirSync(join(taskDir, 'scripts'), { recursive: true })
  writeFileSync(join(taskDir, 'AGENTS.md'), '# runbook\n')
  writeFileSync(join(taskDir, 'scripts', 'run.sh'), 'echo real\n')
  symlinkSync(join(taskDir, 'scripts', 'run.sh'), join(taskDir, 'scripts', 'link.sh'))

  const runCwd = await createRunCwd(root, 'demo-task', new Date(2026, 7, 24, 10, 31, 0))

  assert.equal(readFileSync(join(runCwd, 'scripts', 'link.sh'), 'utf8'), 'echo real\n')
  assertNoSymlinks(runCwd)
})

test('createRunCwd: an empty skills directory is not copied', async () => {
  const root = tmpRoot()
  const taskDir = join(root, 'ops', 'empty-skills')
  mkdirSync(join(taskDir, '.agents', 'skills'), { recursive: true })
  writeFileSync(join(taskDir, 'AGENTS.md'), '# empty skills\n')

  const runCwd = await createRunCwd(root, 'empty-skills', new Date(2026, 7, 24, 10, 34, 0))

  assert.equal(existsSync(join(runCwd, '.agents', 'skills')), false)
  assert.equal(existsSync(join(runCwd, 'AGENTS.md')), true)
})

test('createRunCwd: a non-empty skills directory is copied', async () => {
  const root = tmpRoot()
  const taskDir = join(root, 'ops', 'with-skills')
  mkdirSync(join(taskDir, '.agents', 'skills', 'demo'), { recursive: true })
  writeFileSync(join(taskDir, 'AGENTS.md'), '# with skills\n')
  writeFileSync(join(taskDir, '.agents', 'skills', 'demo', 'SKILL.md'), '# demo\n')

  const runCwd = await createRunCwd(root, 'with-skills', new Date(2026, 7, 24, 10, 35, 0))

  assert.equal(
    readFileSync(join(runCwd, '.agents', 'skills', 'demo', 'SKILL.md'), 'utf8'),
    '# demo\n',
  )
})

test('createRunCwd: missing optional entries are skipped', async () => {
  const root = tmpRoot()
  const taskDir = join(root, 'ops', 'bare-task')
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, 'AGENTS.md'), '# bare\n')

  const runCwd = await createRunCwd(root, 'bare-task', new Date(2026, 7, 24, 10, 32, 0))

  assert.ok(existsSync(join(runCwd, 'AGENTS.md')))
  assert.ok(!existsSync(join(runCwd, 'scripts')))
  assert.ok(!existsSync(join(runCwd, '.agents')))
})

test('createRunCwd: repeated calls in the same second produce distinct run dirs', async () => {
  const root = tmpRoot()
  const taskDir = join(root, 'ops', 'demo-task')
  mkdirSync(taskDir, { recursive: true })

  const now = new Date(2026, 7, 24, 10, 33, 0)
  const a = await createRunCwd(root, 'demo-task', now)
  const b = await createRunCwd(root, 'demo-task', now)
  assert.notEqual(a, b)
  assert.ok(existsSync(a))
  assert.ok(existsSync(b))
})
