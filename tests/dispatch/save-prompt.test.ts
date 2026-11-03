import test from 'node:test'
import assert from 'node:assert/strict'

import { buildEditPrompt, buildSavePrompt } from '../../src/dispatch/save-prompt.ts'
import type { TaskManifest } from '../../src/core/contract.ts'

const seed = {
  boundarySeq: 8014,
  safeCopyBytes: 15_000_000,
  compactBytes: 5_988_465,
  safeCopyEventCount: 5111,
  compactEventCount: 5099,
  maxBytes: 16 * 1024 * 1024,
  maxEvents: 100_000,
}

test('save prompt: a concrete mode carries the trigger contract and the measured seed budget', () => {
  const prompt = buildSavePrompt('watch PRs', 8014, 'safe-copy', {}, seed)
  assert.match(prompt, /everySeconds/)
  assert.match(prompt, /is the trigger kind/)
  assert.match(prompt, /exactly one rule in `params`/)
  assert.match(prompt, /filter\.path/)
  assert.match(prompt, /15000000/)
  assert.match(prompt, /5111 events/)
  assert.match(prompt, /16777216/)
  assert.match(prompt, /100000 event cap/)
  assert.match(prompt, /frozen snapshot/)
})

test('save prompt: metadata, mode, and boundary requirements stay exact', () => {
  const prompt = buildSavePrompt(
    'watch PRs',
    8014,
    'compact',
    { icon: '📁', color: '', naturalPrompt: 'watch PRs' },
    seed,
  )
  assert.match(prompt, /`taskMode` must be "compact"/)
  assert.match(prompt, /`icon` must be "📁"/)
  assert.match(prompt, /`color` must be ""/)
  assert.match(prompt, /`naturalPrompt` must be "watch PRs"/)
  assert.match(prompt, /Use `boundarySeq` 8014/)
  assert.match(prompt, /compact stores 5988465 bytes across 5099 events/)
})

test('save prompt: auto mode reports both byte and event budgets with eligibility', () => {
  const prompt = buildSavePrompt('watch PRs', 8014, 'auto', {}, seed)
  assert.match(prompt, /safe-copy 15000000 bytes \/ 5111 events \(fits/)
  assert.match(prompt, /compact 5988465 bytes \/ 5099 events \(fits/)
  assert.match(prompt, /16777216 byte \/ 100000 event cap/)
  assert.match(prompt, /Choose a mode marked "fits"/)
  assert.match(prompt, /fresh/)
})

test('save prompt: auto mode marks a byte-overflow mode as exceeding', () => {
  const overBytes = { ...seed, safeCopyBytes: 20_214_014 }
  const prompt = buildSavePrompt('watch PRs', 8014, 'auto', {}, overBytes)
  assert.match(prompt, /safe-copy 20214014 bytes \/ 5111 events \(exceeds/)
  assert.match(prompt, /compact 5988465 bytes \/ 5099 events \(fits/)
})

test('save prompt: auto mode marks a byte-fit but event-count-overflow mode as exceeding', () => {
  const overEvents = {
    ...seed,
    safeCopyBytes: 1_000,
    safeCopyEventCount: 100_001,
    compactBytes: 900,
    compactEventCount: 99_999,
  }
  const prompt = buildSavePrompt('watch PRs', 8014, 'auto', {}, overEvents)
  assert.match(prompt, /safe-copy 1000 bytes \/ 100001 events \(exceeds/)
  assert.match(prompt, /compact 900 bytes \/ 99999 events \(fits/)
})

test('save prompt: auto mode can fall back to fresh when capture is unavailable', () => {
  const prompt = buildSavePrompt('watch PRs', 8014, 'auto', {}, undefined, 'invalid seed: cwd must be non-empty')
  assert.match(prompt, /Replay seed cannot be captured/)
  assert.match(prompt, /Choose `taskMode` "fresh"/)
  assert.doesNotMatch(prompt, /frozen snapshot/)
})

test('save prompt: fresh mode does not claim a replay seed exists', () => {
  const prompt = buildSavePrompt('watch PRs', 8014, 'fresh', {}, seed)
  assert.match(prompt, /`taskMode` must be "fresh"/)
  assert.match(prompt, /no replay seed is stored/)
  assert.match(prompt, /unused for `fresh`/)
  assert.doesNotMatch(prompt, /that trace and earlier become the replay seed/)
  assert.doesNotMatch(prompt, /frozen snapshot/)
})

test('edit prompt: keeps the captured mode and seed and does not ask for a new seed', () => {
  const manifest: TaskManifest = {
    format: 'dsh-opskit/1',
    id: 'watch-prs',
    name: 'Watch PRs',
    description: 'Watch PR status',
    version: '0.1.0',
    taskMode: 'safe-copy',
  }
  const prompt = buildEditPrompt(
    { manifest, triggers: [], agensMd: '# Watch PRs' },
    'also watch issue 42',
    { icon: '📁' },
  )
  assert.match(prompt, /taskMode/)
  assert.match(prompt, /safe-copy/)
  assert.match(prompt, /preserves the existing replay seed/)
  assert.match(prompt, /also watch issue 42/)
})

test('save prompt: auto with neither capture mode fitting promises no seed and prescribes fresh', () => {
  const over = { ...seed, safeCopyBytes: 20_000_000, compactBytes: 18_000_000 }
  const prompt = buildSavePrompt('watch PRs', 8014, 'auto', {}, over)
  assert.match(prompt, /Neither safe-copy nor compact fits/)
  assert.match(prompt, /choose `fresh`/)
  assert.doesNotMatch(prompt, /frozen snapshot/)
  assert.doesNotMatch(prompt, /become the replay seed/)
})

test('save prompt: auto with a fitting capture mode explains that fresh stores no seed', () => {
  const prompt = buildSavePrompt('watch PRs', 8014, 'auto', {}, seed)
  assert.match(prompt, /Choose `safe-copy` or `compact` to store that seed/)
  assert.match(prompt, /`fresh` stores no seed/)
})

test('save prompt: continuation mode instructs replayMode, no seed, and no preset bindings', () => {
  const prompt = buildSavePrompt('watch PRs', 8014, 'fresh', {}, undefined, undefined, true)
  assert.match(prompt, /replayMode/)
  assert.match(prompt, /"continue-session"/)
  assert.match(prompt, /`taskMode` must be "fresh"/)
  assert.match(prompt, /do not capture a replay seed/)
  assert.match(prompt, /Do not bind `agentPreset` or `permissionPreset`/)
  assert.match(prompt, /self-contained runbook/)
  assert.doesNotMatch(prompt, /frozen snapshot/)
})

test('edit prompt: reports a continuation binding and asks to preserve it', () => {
  const prompt = buildEditPrompt(
    {
      manifest: {
        format: 'dsh-opskit/1',
        id: 'continue-task',
        name: 'Continue task',
        description: 'x',
        version: '0.1.0',
        taskMode: 'fresh',
        bindings: { continueSession: { sessionId: 'session-1' } },
      },
      triggers: [],
      agensMd: '# Continue',
    },
    'more checks',
  )
  assert.match(prompt, /Preserve the existing `bindings` and replay target/)
  assert.match(prompt, /continues its source session/)
  assert.match(prompt, /"continue-session"/)
})

test('save prompt: continuation mode does not ask for a successful trace', () => {
  const prompt = buildSavePrompt('watch PRs', 8014, 'fresh', {}, undefined, undefined, true)
  assert.match(prompt, /continues this source session/)
  assert.doesNotMatch(prompt, /with the successful trace before boundarySeq/)
  const seeded = buildSavePrompt('watch PRs', 8014, 'fresh', {})
  assert.match(seeded, /with the successful trace before boundarySeq/)
})
