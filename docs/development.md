# Development

## Prerequisites

- Node `^22.19 || >=24`
- A local `deepseek-harness` checkout for dsh integration testing

## Commands

```sh
npm install
npm run build
npm test
npm run typecheck
npm run lint
```

## Develop loop

1. Edit `src/`.
2. Run `npm run build`, `npm test`, `npm run typecheck`, `npm run lint`.
3. Install into a dsh profile:

```sh
dsh plugin --profile <profile> add link:<checkout>
```

4. Run `npm run build`, then restart dsh and refresh the page. `dev:web` only discovers packages inside the harness checkout; a plugin linked from a separate checkout is not rebuilt by that watcher, so both host and client changes need this manual build/restart loop.

## Adding a trigger source

1. Add the normalized event fields to `src/core/triggers/event.ts`.
2. Implement the source in `src/core/triggers/<source>.ts`.
3. Register it in the host trigger engine.
4. Add tests under `tests/triggers/`.
5. Update [architecture.md](architecture.md) and the relevant project skill or decision record for the trigger design.

## Documentation

Follow [AGENTS.md](../AGENTS.md) and the [project skill](../.agents/skills/maintainall/SKILL.md). Routine knowledge belongs in the project skill; substantial decisions belong in its `decisions/` directory.
