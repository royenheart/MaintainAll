import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse } from 'yaml'

interface PresetRow {
  id?: string
  name?: string
  config?: {
    id?: string
    plugins?: Array<{
      id?: string
      name?: string
      config?: {
        watch?: boolean
        watchMaxProjects?: number
        prefix?: string
        allowParallelInProgress?: boolean
        section?: string
      }
    }>
  }
}

test('ops preset patch declares the ops preset with the watcher disabled', () => {
  const patch = parse(
    readFileSync(new URL('../../preset/ops.patch.yml', import.meta.url), 'utf8'),
  ) as Array<{ insert?: PresetRow[] }>
  const declaration = patch.flatMap((entry) => entry.insert ?? [])
    .find((row) => row.id === 'preset-ops')
  assert.ok(declaration !== undefined, 'ops patch must declare preset-ops')
  assert.equal(declaration.name, '@deepseek-ai/dsh-agent-preset')
  assert.equal(declaration.config?.id, 'ops')
  const plugins = declaration.config?.plugins ?? []
  const watch = plugins.find((row) => row.id === 'skill-filesystem')
  assert.ok(watch !== undefined, 'ops preset must mount skill-filesystem')
  assert.equal(watch.config?.watch, false)
  assert.equal(watch.config?.watchMaxProjects, 8)
  const reminders = plugins.find((row) => row.id === 'tool-schedule')
  assert.equal(reminders?.name, '@deepseek-ai/dsh-tool-schedule')
  const persona = plugins.find((row) => row.id === 'persona')?.config?.prefix
  assert.equal(typeof persona, 'string')
  for (const match of (persona ?? '').matchAll(/\{\{\s*([\w-]+)\s*\}\}/g)) {
    assert.ok(match[1] === 'model' || match[1] === 'provider', `unknown persona variable ${match[1]}`)
  }
  assert.equal(plugins.find((row) => row.id === 'todo')?.config?.allowParallelInProgress, true)
  const planning = plugins.find((row) => row.id === 'planning')
  const planMode = (planning as { config?: Array<{ id?: string; config?: { section?: string } }> } | undefined)
    ?.config?.find((row) => row.id === 'plan-mode')
  assert.equal(typeof planMode?.config?.section, 'string')
})
