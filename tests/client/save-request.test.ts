import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildAutoCreateSaveRequest,
  buildEditLlmRequest,
  buildEditMaterializeRequest,
  buildManualCreateSaveRequest,
  effectiveCreateTaskMode,
} from '../../src/client/save-request.ts'

const trigger = {
  id: 'task-t1',
  source: 'schedule',
  enabled: true,
  params: { everySeconds: 1800 },
}

test('effectiveCreateTaskMode: continuation always forces fresh', () => {
  assert.equal(effectiveCreateTaskMode(true, 'safe-copy'), 'fresh')
  assert.equal(effectiveCreateTaskMode(true, 'auto'), 'fresh')
  assert.equal(effectiveCreateTaskMode(false, 'safe-copy'), 'safe-copy')
  assert.equal(effectiveCreateTaskMode(false, 'compact'), 'compact')
})

test('buildAutoCreateSaveRequest: continuation sends fresh and the flag', () => {
  const request = buildAutoCreateSaveRequest({
    sessionId: 'session-1',
    mode: 'safe-copy',
    continueSession: true,
    icon: '📁',
    color: '',
    naturalPrompt: 'watch issues',
    description: 'watch issues',
  })
  assert.equal(request.sessionId, 'session-1')
  assert.equal(request.boundarySeq, 0)
  assert.equal(request.meta['taskMode'], 'fresh')
  assert.equal(request.meta['continueSession'], true)
  assert.equal(request.meta['auto'], true)
})

test('buildManualCreateSaveRequest: continuation sends fresh and the trigger', () => {
  const request = buildManualCreateSaveRequest({
    sessionId: 'session-1',
    mode: 'compact',
    continueSession: true,
    icon: '📁',
    color: '#fff',
    naturalPrompt: 'watch issues',
    taskId: 'watch-issues',
    name: 'Watch issues',
    description: 'watch issues',
    trigger,
  })
  assert.equal(request.meta['taskMode'], 'fresh')
  assert.equal(request.meta['continueSession'], true)
  assert.equal(request.meta['materialize'], true)
  assert.deepEqual(request.meta['triggers'], [trigger])
})

test('creation requests without continuation keep the selected mode', () => {
  const auto = buildAutoCreateSaveRequest({
    sessionId: 'session-1',
    mode: 'compact',
    continueSession: false,
    icon: '📁',
    color: '',
    naturalPrompt: '',
    description: 'watch',
  })
  assert.equal(auto.meta['taskMode'], 'compact')
  assert.equal(auto.meta['continueSession'], false)
  const manual = buildManualCreateSaveRequest({
    sessionId: 'session-1',
    mode: 'safe-copy',
    continueSession: false,
    icon: '📁',
    color: '',
    naturalPrompt: '',
    taskId: 'watch',
    name: 'Watch',
    description: 'watch',
    trigger,
  })
  assert.equal(manual.meta['taskMode'], 'safe-copy')
  assert.equal(manual.meta['continueSession'], false)
})

test('both edit request builders never change the replay target', () => {
  const llm = buildEditLlmRequest({ description: 'more checks', icon: '📁', color: '', naturalPrompt: 'more checks' })
  assert.equal('continueSession' in llm, false)
  assert.equal('replayMode' in llm, false)
  const materialize = buildEditMaterializeRequest({
    name: 'Watch',
    description: 'more checks',
    triggers: [trigger],
    icon: '📁',
    color: '',
    naturalPrompt: '',
  })
  const meta = materialize['meta'] as Record<string, unknown>
  assert.equal('continueSession' in meta, false)
  assert.equal('replayMode' in meta, false)
  assert.equal('taskMode' in meta, false)
})
