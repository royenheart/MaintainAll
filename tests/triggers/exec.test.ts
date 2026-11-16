import { test } from 'node:test'
import assert from 'node:assert/strict'
import { ExecEdgeDetector } from '../../src/core/triggers/exec.ts'

const T0 = new Date('2026-08-23T00:00:00.000Z')
const T1 = new Date('2026-08-23T00:01:00.000Z')
const T2 = new Date('2026-08-23T00:02:00.000Z')

test('update: first observation is an edge', () => {
  const detector = new ExecEdgeDetector()
  assert.equal(detector.update('ok\n', '', 0, T0), true)
})

test('update: steady state is not an edge', () => {
  const detector = new ExecEdgeDetector()
  detector.update('ok\n', '', 0, T0)
  assert.equal(detector.update('ok\n', '', 0, T1), false)
})

test('update: stdout change is an edge', () => {
  const detector = new ExecEdgeDetector()
  detector.update('used: 10%\n', '', 0, T0)
  assert.equal(detector.update('used: 97%\n', '', 0, T1), true)
  assert.equal(detector.update('used: 97%\n', '', 0, T2), false)
})

test('update: exit code change is an edge', () => {
  const detector = new ExecEdgeDetector()
  detector.update('ok\n', '', 0, T0)
  assert.equal(detector.update('ok\n', '', 1, T1), true)
})

test('update: stderr change alone is not an edge but is recorded', () => {
  const detector = new ExecEdgeDetector()
  detector.update('ok\n', '', 0, T0)
  assert.equal(detector.update('ok\n', 'warning\n', 0, T1), false)
  assert.equal(detector.snapshot()?.stderr, 'warning\n')
})

test('constructor: restored state suppresses the first-observation edge', () => {
  const restored = new ExecEdgeDetector({ stdout: 'ok\n', stderr: '', exitCode: 0 })
  assert.equal(restored.update('ok\n', '', 0, T0), false)
  assert.equal(restored.update('changed\n', '', 0, T1), true)

  const empty = new ExecEdgeDetector({ stdout: undefined })
  assert.equal(empty.update('ok\n', '', 0, T0), true)
})

test('snapshot: reflects the latest observation with its timestamp', () => {
  const detector = new ExecEdgeDetector()
  assert.equal(detector.snapshot(), undefined)
  detector.update('a\n', '', 0, T0)
  detector.update('a\n', '', 1, T1)
  assert.deepEqual(detector.snapshot(), {
    stdout: 'a\n',
    stderr: '',
    exitCode: 1,
    observedAt: T1.toISOString(),
  })
  // The snapshot is a copy.
  const snap = detector.snapshot()!
  snap.stdout = 'mutated'
  assert.equal(detector.snapshot()?.stdout, 'a\n')
})
