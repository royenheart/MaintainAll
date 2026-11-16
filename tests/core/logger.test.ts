import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, readdir, stat } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { PluginLogger } from '../../src/core/logger.ts'

test('PluginLogger appends JSONL and reads newest first', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'maintainall-logger-'))
  const logger = new PluginLogger(dir)
  logger.info('one')
  logger.warn('two')
  logger.error('three')

  const page = logger.read(2, 0)
  assert.equal(page.hasMore, true)
  assert.deepEqual(page.entries.map((entry) => entry.msg), ['three', 'two'])

  const older = logger.read(2, 2)
  assert.equal(older.hasMore, false)
  assert.deepEqual(older.entries.map((entry) => entry.msg), ['one'])
})

test('PluginLogger rotates and prunes old archives', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'maintainall-logger-rotate-'))
  const logger = new PluginLogger(dir, 64, 2)
  for (let index = 0; index < 20; index += 1) logger.info(`line-${index}`)
  const names = (await readdir(dir)).filter((name) => name.startsWith('maintainall-') && name.endsWith('.log'))
  assert.ok(names.length <= 2)
  const page = logger.read(5, 0)
  assert.ok(page.entries.some((entry) => entry.msg === 'line-19'))
})

test('PluginLogger read returns empty page for missing log file', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'maintainall-logger-empty-'))
  const logger = new PluginLogger(dir)
  assert.deepEqual(logger.read(), { entries: [], hasMore: false })
  assert.equal((await stat(join(dir, 'maintainall.log')).catch(() => null)), null)
})
