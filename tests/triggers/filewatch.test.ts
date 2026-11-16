import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  FileWatchPoller,
  type FileStatResult,
} from '../../src/core/triggers/filewatch.ts'

/** Fake file: an in-memory byte string with controllable size/inode. */
function fakeFile(initial: string, inode = 1) {
  let content = initial
  const statResult: FileStatResult = {
    size: Buffer.byteLength(content, 'utf8'),
    mtimeMs: Date.parse('2026-08-23T00:00:00Z'),
    inode,
  }
  const io = {
    async stat(_path: string): Promise<FileStatResult> {
      return { ...statResult }
    },
    reads: 0,
    async read(_path: string, start: number) {
      io.reads += 1
      const chunk = content.slice(start)
      const cut = chunk.lastIndexOf('\n') + 1
      const text = chunk.slice(0, cut)
      return { text, bytes: Buffer.byteLength(text, 'utf8') }
    },
  }
  return {
    io,
    statResult,
    append(text: string) {
      content += text
      statResult.size = Buffer.byteLength(content, 'utf8')
      statResult.mtimeMs += 1000
    },
    replace(text: string, newInode?: number) {
      content = text
      statResult.size = Buffer.byteLength(content, 'utf8')
      statResult.mtimeMs += 1000
      if (newInode !== undefined) statResult.inode = newInode
    },
    setInode(inode: number) {
      statResult.inode = inode
    },
  }
}

const PATH = '/var/log/fake.log'

test('poll: emits only new complete lines and advances the offset', async () => {
  const file = fakeFile('first\nsecond\n')
  const poller = new FileWatchPoller(file.io)

  const initial = await poller.poll(PATH)
  assert.deepEqual(initial.lines, ['first', 'second'])
  assert.equal(initial.offset, Buffer.byteLength('first\nsecond\n', 'utf8'))
  assert.equal(initial.inode, 1)

  file.append('third\n')
  const delta = await poller.poll(PATH)
  assert.deepEqual(delta.lines, ['third'])
  assert.equal(delta.offset, Buffer.byteLength('first\nsecond\nthird\n', 'utf8'))
})

test('poll: no change returns no lines and keeps the offset', async () => {
  const file = fakeFile('line\n')
  const poller = new FileWatchPoller(file.io)
  await poller.poll(PATH)

  const again = await poller.poll(PATH)
  assert.deepEqual(again.lines, [])
  assert.equal(again.offset, Buffer.byteLength('line\n', 'utf8'))
})

test('poll: trailing partial line is held back until it completes', async () => {
  const file = fakeFile('done\npar')
  const poller = new FileWatchPoller(file.io)

  const first = await poller.poll(PATH)
  assert.deepEqual(first.lines, ['done'])
  assert.equal(first.offset, Buffer.byteLength('done\n', 'utf8'))

  file.append('tial\nnext\n')
  const second = await poller.poll(PATH)
  assert.deepEqual(second.lines, ['partial', 'next'])
})

test('poll: size shrink is treated as rotation and rereads from 0', async () => {
  const file = fakeFile('aaaaaaaa\nbbbbbbbb\n')
  const poller = new FileWatchPoller(file.io)
  await poller.poll(PATH)

  file.replace('cc\n') // smaller file, same inode
  const after = await poller.poll(PATH)
  assert.deepEqual(after.lines, ['cc'])
  assert.equal(after.offset, Buffer.byteLength('cc\n', 'utf8'))
})

test('poll: inode change is treated as rotation even when size grows', async () => {
  const file = fakeFile('old\n')
  const poller = new FileWatchPoller(file.io)
  await poller.poll(PATH)

  file.replace('new-content-longer\n', 2)
  const after = await poller.poll(PATH)
  assert.deepEqual(after.lines, ['new-content-longer'])
  assert.equal(after.inode, 2)
  assert.equal(after.offset, 0 + Buffer.byteLength('new-content-longer\n', 'utf8'))
})

test('poll: regex filter selects lines but still advances the offset', async () => {
  const file = fakeFile('INFO ok\nERROR boom\nDEBUG noise\nERROR crash\n')
  const poller = new FileWatchPoller(file.io, { regex: '^ERROR' })

  const result = await poller.poll(PATH)
  assert.deepEqual(result.lines, ['ERROR boom', 'ERROR crash'])
  assert.equal(result.offset, file.statResult.size)
})

test('poll: resumes from persisted offset and inode without rotation', async () => {
  const file = fakeFile('one\ntwo\n')
  const offset = Buffer.byteLength('one\n', 'utf8')
  const poller = new FileWatchPoller(file.io, { initialOffset: offset, initialInode: 1 })

  const result = await poller.poll(PATH)
  assert.deepEqual(result.lines, ['two'])
})

test('prime: adopts the current EOF without reading historical content', async () => {
  const file = fakeFile('old line\n')
  const poller = new FileWatchPoller(file.io)
  const primed = await poller.prime(PATH)
  assert.deepEqual(primed.lines, [])
  assert.equal(primed.offset, file.statResult.size)
  assert.equal(file.io.reads, 0)
  file.append('new line\n')
  const delta = await poller.poll(PATH)
  assert.deepEqual(delta.lines, ['new line'])
})

test('reset: forgets the tracked position', async () => {
  const file = fakeFile('a\n')
  const poller = new FileWatchPoller(file.io)
  await poller.poll(PATH)
  poller.reset()
  assert.equal(poller.currentOffset, 0)
  const result = await poller.poll(PATH)
  assert.deepEqual(result.lines, ['a'])
})
