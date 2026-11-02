# Personal homepage

The VPC homepage is an Astro static site with React islands, TypeScript, Tailwind CSS, Motion, and React Three Fiber. It preserves the sidebar/navigation, central artwork, bottom music/registration bar, blue cube cloud, and golden event horizon. OpenResty serves the build output or proxies to an internal static server. It never reads application data or renders templates.

The latest Orbit refinement is documented in [quiet cards and layered audio
contours](../docs/proxy-audio-contours.md), including card order, contour-aware
identity layout, actual audio analysis and visual-review evidence.

The selected Orbit soundtrack is **Clair de Lune** for cubes and **Sanctuary**
for horizon, both using public NetEase outer links in the unified native player.
When samples cannot be read, the artwork ring uses a gentle default animation;
readable sources still drive it with actual audio. See the
[external soundtrack notes](../docs/proxy-external-soundtrack.md).
Optional [same-origin recording delivery](../docs/proxy-local-soundtrack.md)
remains available for local files. No artist recording is bundled.

The selected full-screen website is available at `/` in the static production
build, including arrivals, music, the drum deck, live B and F7. `/preview/` is
retained as a review alias, and the previous compact homepage remains at
`/original/`. None of these routes load Storybook. For LAN review, run
`REVIEW_HOST=<your LAN address> npm exec -w @royenheart/home -- astro preview --host "$REVIEW_HOST" --port 4321` and open
`http://$REVIEW_HOST:4321/`. Set `REVIEW_HOST` locally; do not commit a machine address.
The preview enters a randomly chosen scene automatically and keeps its four-card
deck visible. The cube scene is named `axolotl`; its music remains Clair de Lune.
Browser-blocked sound can be enabled from the final information card without
blocking entry. Its previous / play-pause / next controls keep music pause
independent of background motion. Registration links sit below the dock.
The user selected IBM Plex Sans and a random cover treatment on each scene
change. `/preview-covers/` compares the three retained artwork treatments;
`cover` and `identity` query parameters allow isolated review. Optional
`?details=etch`, `?details=flow` and `?details=orbit` compare restrained icon
feedback using the same material and typography. These detail studies await
selection. See the [continuous presentation notes](../docs/proxy-continuous-presentation.md)
and [dock refinement measurements](../docs/proxy-dock-refinement.md).

Use `?scene=cubes` or `?scene=horizon` to choose the initial scene;
`?diagnostics=1` opens the runtime HUD. `Shift+D` toggles the same local HUD at
any time: renderer, frame cadence, drawing buffer, scene/optics/audio services,
network and a live frame chart. On coarse-pointer phones and tablets, a 44px
`>_` control at the top-right opens the same HUD; it hides while the HUD is open,
and the panel's × control closes it. Degraded or unavailable rendering uses a
continuously moving, scene-specific damage layer rather than a blur or a static
poster; the visible fallback sentence lives only in the HUD. `?graphics=poster` selects the lightweight still view. The previous
compact homepage remains available at `/original/` for comparison. See the
[performance audit](../docs/proxy-preview-performance.md) for measured results
and the distinction between hardware rendering, software rendering and transfer
cost. The current tree's startup readiness, audio intent and concurrency review
is in [the performance and concurrency review](../docs/proxy-performance-concurrency-review.md).

## Development

Use Node 24 LTS and run commands from the repository root:

```bash
npm ci
npm run proxy:dev
```

Astro prints the local URL (normally `http://localhost:4321`). `npm run proxy:storybook` opens the component development server at `http://localhost:6006`. Run `npm run proxy:build && npm run proxy:preview` to inspect the production output. Preview is for local verification only.

The Jekyll blog remains independent. One root `package-lock.json` locks the npm workspace. Do not create another lockfile inside `proxy`.

## Content

Edit the following files, commit, build, and publish the new artifact:

- `src/content/site.json`: title, profile links, and official registration links.
- `src/content/playlist.json`: track IDs, labels, and the default selection.
- `src/content/scenes.json`: default scene, deterministic seed, particle budget, and palettes.

`src/lib/content/schema.ts` validates these files during the build. Invalid links, arbitrary HTML, duplicate track IDs, missing defaults, or invalid graphics settings fail the build. React escapes labels; raw iframe markup is not accepted.

A playlist entry uses this structure:

```json
{
  "id": "first-light",
  "kind": "netease-embed",
  "songId": "30953026",
  "label": "A little music for the journey"
}
```

The existing NetEase song is preserved. Multiple entries expose a native track selector. An empty playlist uses `{"defaultTrackId": null, "tracks": []}`. The player loads only after Listen is pressed, with autoplay disabled. Small screens use the external song link. Cross-origin playback remains under NetEase's control; a loaded iframe does not establish that audio is playing. The advisory timeout and external link remain available when the provider fails.

## Architecture

`src/pages/index.astro` validates data and emits the static `HomeFrame`. Music and scene controls hydrate independently. `SceneExperience` owns scene selection, loading, reduced motion, pause, and fallback. `SceneCanvas` loads separately and delegates the render loop, resizing, instancing, and resource disposal to R3F/Three.js. Motion handles DOM transitions; Drei's performance monitor lowers quality when needed. There is no custom cross-device renderer or second Canvas2D engine.

The existing artistic shaders remain in `src/scenes/materials`. The scene posters are fallback captures of the original artwork; live rendering uses actual geometry and shaders. The optimized avatar derives from the original `avatar.svg`, retained as source material.

Useful diagnostic URLs:

- `/?capture=1`: deterministic scene time for screenshots; no continuous loop.
- `/?graphics=poster`: static scene artwork for layout/failure isolation.

Neither diagnostic mode is evidence of normal animation performance. Test `/` as well.

See [design constraints](DESIGN.md), [architecture decisions](../docs/proxy-refactor-plan.md), [verification record](../docs/proxy-verification.md), [deployment](deploy/README.md), and [agent skills](../.agents/skills/README.md).

## Verification

```bash
npm run skills:check
npm test
npx playwright install chromium firefox webkit
npm run proxy:storybook:test
npm run proxy:build
npm run proxy:bundle
npm run proxy:deploy:test # Requires Docker
npm run proxy:storybook:build
npm run proxy:e2e
```

On supported Linux CI, use `npx playwright install --with-deps chromium firefox webkit`. Local operating systems may need additional browser libraries. The Playwright config starts the production preview and a static Storybook server. In local development it can reuse servers on ports 4321 and 6006; stop stale servers after rebuilding when necessary. CI requires clean ports.

`npm test` runs type checking, lint, formatting, content-contract tests, and temporary-directory deployment tests. `proxy:storybook:test` runs component interactions and accessibility checks in Chromium. `proxy:e2e` runs the actual production page and built Storybook iframe in Chromium, Firefox, and WebKit. The GPU/performance smoke is explicitly Chromium-only; other engines verify layout, input, and failure behavior. `npm run proxy:perf` runs only the rendering lifetime/frame-sampling scenario.

The 13-size matrix covers phone, tablet, desktop, portrait/landscape, short height, and both sides of the 720px breakpoint. Geometry assertions calculate containment, intersection, edge alignment, overflow, and canvas size. A deliberate broken-layout test verifies that the oracle detects defects. Race tests cover repeated scene changes, resize during interaction, deferred graphics loading/unmount, pending music embeds, stale timeouts, and close/reopen. Text enlargement, keyboard access, reduced motion, no JavaScript, unavailable graphics, and context loss have dedicated checks.

Browser evidence is written to `proxy/test-results/` and `proxy/playwright-report/`. Frame intervals describe the browser scheduler, not GPU completion. Software-rendered CI results do not establish real iOS/Android device performance. Screenshots are review artifacts; this migration does not claim cross-platform pixel-identical image baselines.

The compressed budget covers **all emitted JavaScript**, including the dynamically imported graphics chunk, and all CSS. It does not hide the graphics download under a shell-only budget. The graphics import starts after hydration, so it is still part of the first normal visit. `proxy:bundle` records individual and total gzip sizes and fails above 500 KiB JavaScript or 30 KiB CSS.

## Design exploration

The latest [falling arrival and accretion studies](../docs/proxy-accretion-studies.md)
compare `split-accretion`, `orbital-accretion` and `cascade-accretion`, with a
full-sized falling `cube-arrival`. The user selected live B (`orbital-accretion`);
A/C remain comparisons. The accepted F7 reverse remains selected.
The [continuous journey](../docs/proxy-scene-continuity.md) runs arrival, both
backgrounds and both transitions on one canvas with advancing material time.

The selected [F7 glitch transition](../docs/proxy-glitch-transition.md) expands a
local color anomaly through the actual horizon, disk and nebula, progressively
warps and blurs that source, then separates scene-bearing mirror panes.
`glitch-and-fracture`, `glitch-surface`, `glitch-field` and `glitch-sharp` expose
the complete sequence, source-only view, growing field and no-blur comparison.
Radiation strands are absent from the selected path. F3–F6 remain historical
comparisons, including the orbitable `Explorations/Spatial radiation` study.

Four interactive directions live under `Explorations/Design directions` in Storybook. They share the original two scenes and the new `UnifiedPlayer`; the production `HomeFrame` remains the previous design until a direction is selected. See [the research and capability report](../docs/proxy-design-exploration.md) for current playback support and remaining integration work.

With Storybook running on port 6006, capture both scenes on desktop, phone and tablet:

```bash
node proxy/scripts/capture-concepts.mjs /tmp/proxy-style-previews
```

Run this command from the repository root. It refuses an output directory inside the repository. Screenshots, comparison pages and rendering evidence are local review artifacts, not committed design assets.

`Explorations/Orbit study` develops the subsequent full-screen direction: compact artwork controls, a rounded capsule deck with cylindrical card travel, and a reversible cube-to-horizon sequence. Its optical renderer uses precomputed Schwarzschild light paths and procedural disk emission. See [the current implementation notes](../docs/proxy-relativistic-horizon.md) for model limits, source attribution, controls and verification. Generate the comparison page and motion recordings with:

```bash
node proxy/scripts/capture-optical-study.mjs /tmp/proxy-optical-study/final
```

The user selected **B / Velvet drum** in `Explorations/Rotary directions`. The Orbit component and `Selected Cubes` / `Selected Horizon` stories now use it. A/C and the classic trapezoid stories remain comparisons; older capture scripts explicitly select the classic baseline. [The rotary decision record](../docs/proxy-rotary-directions.md) documents contour-aware text placement, scene textures, motion and responsive verification. Generate the out-of-repository review with `node proxy/scripts/capture-rotary.mjs /tmp/proxy-rotary-study/final`.

The latest [limb-glow refinement](../docs/proxy-limb-refinement.md) removes card arrow buttons, reveals playback inside the artwork and restores a foreground disk reaching the bottom. The selected stories use the `limb` treatment; `optical` retains the previous disk image. Capture the current state with `node proxy/scripts/capture-limb.mjs /tmp/proxy-limb-study/final`.

The [continuous ribbon refinement](../docs/proxy-continuous-ribbon.md) replaces the
rejected independent tip veil with shared disk/arc material coordinates.
`Horizon Flow Coordinates` displays connected material groups, and
`Horizon Unbloomed Emission` disables Bloom for junction inspection. Both are
diagnostic Storybook views; the selected scene still uses the normal gold material.

The [depth and wave refinement](../docs/proxy-perspective-waves.md) expands ring
intervals toward the foreground and displaces the shared surface with travelling
swells. Orbit Storybook URLs accept `&capture=1&sceneTime=12` (or `16`, `20`) for
reproducible wave phases. `sceneTime` is ignored outside capture mode; omit
`capture=1` to inspect normal animation.

The [nebula and luminous-mantle study](../docs/proxy-nebula-corona.md) adds seeded
clouds, dust, supporting colors and rounded outer-glow protrusions. The inner
rim and black shadow stay fixed; the raised mantle is filled with light. The
[reference analysis](../docs/proxy-nebula-reference-analysis.md) records the
user's corrected sketches and excludes the building-associated streak in the
sixth reference. The existing limb capture command includes the current material.

The optical browser tests run in Chromium, Firefox and WebKit. The Orbit geometry matrix checks 17 viewport sizes, including short screens. These are separate from the original homepage's matrix and do not establish real-device GPU performance.

## Release

The independent `Proxy checks and static artifact` workflow uploads `proxy-static-<commit>` after verification. Deploy only its contents (`proxy/dist`), using the [atomic publication helper and OpenResty examples](deploy/README.md). Node is a build/deployment-helper dependency; the public server needs no Node, Python, Lua template engine, playlist API, or database.

The legacy TOML/template/Python preview path and source-regex tests have been removed. Previous Git revisions and deployed release directories remain the rollback source. No production deployment is performed by the verification workflow.

The selected nameplate now defaults to drifting inlay and graphic Elsewhere marks. Bound-card extraction studies are available via `cardMotion=slide|lift|fan` and `cardSurface=drift|light|layers` on `/preview/?card=elsewhere&skipIntro=1`. See [the slot/card refinement](../docs/proxy-slot-cards.md) for semantics, motion references, lifecycle checks and review artifacts.

The user-selected card behavior is now single-card straight rise/return with drifting inlay; other cards remain stored. `cardArt=engraving|foil|relief` compares scene-specific lower-right SVG prints. See [the single-card/artwork refinement](../docs/proxy-card-art.md) for pending artwork choices, reproduction and validation.

The selected scene printing is relief for horizon and foil for cubes. Elsewhere defaults to horizontal printing (`editorial`); `marks=emblem|intaglio|editorial` retains the comparisons. See [semantic marks and recessed storage](../docs/proxy-slot-mark-refinement.md) for the current defaults, license attribution and visual measurements.
