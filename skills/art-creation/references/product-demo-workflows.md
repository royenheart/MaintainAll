# Product demo workflows: README, banner, GIF, and film

A product demo is a small system, not one export. For a README-only project, the scope can be deliberately narrow: **one demo GIF**, with no banner or launch film. The broader landscape is still recorded below so the branch does not overfit one repository.

A README needs a fast visual claim; a banner needs a durable identity; a launch film can create desire. They are different jobs.

## Product-demo-specific decisions

Scope: the entry skill selects this branch; this file adds only product-demo-specific decisions and does not replace the generic intent and feedback loop.

These are the decisions that belong to a product demo rather than to the generic creative loop.

### Atomic product-demo attributes

| Atom | Question | Typical choices | Why it changes the artifact |
|---|---|---|---|
| Audience | Who must understand this in one viewing? | New user, evaluator, existing user | Sets vocabulary and how much UI can be omitted |
| Belief | What should the viewer believe after 20 seconds? | "It runs real checks", "It saves a reusable task", "It replays reliably" | Selects the one operation to prove |
| Surface | Where will this be watched? | README, chat, social post, landing page | Sets aspect ratio, size, autoplay, and caption rules |
| Evidence mode | Must this prove a real run? | Live capture, rebuilt film, hybrid | Live capture for proof; rebuilt only for narrative |
| Operation | Which single workflow is the spine? | Create, save, replay, inspect | Prevents a feature catalogue |
| Length | How long can the viewer stay? | 10 s, 20 s, 30 s | Forces cuts and pacing decisions |
| Motion | How much movement is needed? | Static hold, guided UI, one-take film | Determines capture vs composition |
| Visual system | Light or dark, and what accent? | Product theme, brand theme | Affects rail contrast and overlay legibility |
| Language | Which locale is on screen? | English, Chinese, bilingual captions | Changes label widths and rail geometry |
| Accessibility | What if motion is reduced or sound is off? | Poster, captions, alt text | The demo must still explain itself |
| Constraints | What cannot appear or cannot be changed? | No names, no secrets, fixed commit, no banner | Narrows the production path immediately |

### One question at a time

A useful sequence for a new product demo:

1. "After watching this, what should someone believe?" (belief)
2. "Which single operation proves it?" (operation)
3. "Does it need to prove a real run, or is a designed explanation enough?" (evidence mode)
4. "Where will they see it, and how wide is the content column?" (surface)
5. "What is the shortest version that still teaches the operation?" (length)
6. "Which language and theme should be on screen?" (visual system)

Each answer eliminates a branch. Show a preview when the answer is visual; do not ask about palette, easing, or camera until the operation and evidence mode are settled.

### Product-demo brief

Keep a small decision record beside the work:

```text
surface: README
belief: this operation really ran and produced a reusable task
operation: run checks -> save task -> replay
evidence: live capture
length: 20-25 s
language: English
theme: light
constraints: no names, no secrets, no banner, no launch film
accepted: chapter-index rail; no decorative cursor; enter the dispatched session immediately
open: none
```

The brief is not a form for the user to fill. It is the agent's record of what was learned and what remains open.

## Artifact ladder

| Artifact | Job | Default format | Constraints |
|---|---|---|---|
| Banner / hero (optional) | Establish identity and the promise | SVG, with a PNG fallback | 2:1 or 16:9; safe text; light and dark variants; under ~300 KB |
| README demo | Explain the core workflow in one viewing | Animated GIF; optional MP4/WebM | 10–25 s; 12–15 fps; target under 5 MB; captions and alt text |
| Launch film (optional) | Create desire, not proof | MP4/WebM, 15–40 s | 1080p draft, 4K only after acceptance; sound optional; label concept films |
| Interactive landing demo | Let a visitor drive the product | HTML/JS; Three.js or GSAP only when motion needs 3D or scroll | Not a README substitute; test reduced motion and mobile |
| Terminal demo | Show a CLI workflow deterministically | GIF/MP4 from a tape or session | VHS or asciinema; exact commands; no live credentials |

GitHub renders images inline in Markdown; GIF remains the most portable animated README asset. Uploaded video attachments can work where the host renders them, but a GIF or static poster must remain as the fallback. Use the target renderer as the test, not the Markdown renderer alone. See GitHub's [README guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes), [image syntax](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax#images), [social preview guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview), and [file attachment guidance](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/attaching-files).

## What high-attention repositories do

The recurring pattern is not a single tool. It is a short, legible promise followed by a motion artifact with a clear causal path.

| Workflow | Representative tools | Strength | Cost / failure mode |
|---|---|---|---|
| Live screen capture | [Screen Studio](https://screen.studio/), Playwright, FFmpeg, [Gifski](https://github.com/sindresorhus/gifski) | Proves the real product; fast to produce | Capture jank, accidental secrets, unreadable speed |
| Scripted terminal capture | [VHS](https://github.com/charmbracelet/vhs), [asciinema](https://github.com/asciinema/asciinema) | Deterministic, rerunnable, small | Only proves the terminal surface |
| Programmatic video | [Remotion](https://github.com/remotion-dev/remotion), [Motion Canvas](https://github.com/motion-canvas/motion-canvas) | Reusable code, captions, exact timing, brand system | Build complexity; not evidence of runtime behavior |
| Rebuilt-UI film | [onetake](https://github.com/feitangyuan/onetake) | Camera freedom, continuity, polished motion | Design-heavy; not a recording; licence and maintenance matter |
| Web motion / 3D | [Three.js](https://github.com/mrdoob/three.js), [GSAP](https://github.com/greensock/GSAP) | Interactive, scroll-driven, spatial storytelling | Landing-page scope; not a README artifact |
| Vector micro-motion | [Lottie](https://github.com/airbnb/lottie-web), Rive | Small loops, crisp scaling | Cannot prove a workflow; limited runtime support |
| NLE finishing | DaVinci Resolve, After Effects, CapCut | Highest polish, sound, grading | Manual, hard to regenerate, review drift |

Star counts observed through the GitHub API in October 2026 illustrate attention, not fit: Remotion ~68k, Lottie ~32k, Three.js ~117k, GSAP ~30k, VHS ~21k, Motion Canvas ~19.5k, asciinema ~18k, Gifski ~8.6k. Choose by the job, not by the count.

## A README that earns the click

1. One sentence: what changes for the user.
2. One visual: banner or short demo, not both competing for the same first screen.
3. One proof: a real command, a short GIF, or a trustworthy run result.
4. One next step: install, quickstart, or docs.

Keep the first visual readable at GitHub's content width. A hero banner should survive at 640–900 px wide; a demo GIF should keep its smallest label at 10–12 px in the exported frame. If the UI cannot be read at that size, redesign the frame instead of shrinking it.

### Banner rules

- Design at 2x and export a crisp 1280×640 or 1200×630 social preview.
- Keep the product name, one-line promise, and one visual idea; do not put the whole workflow into the banner.
- Provide light and dark variants when the README or social card can switch.
- Prefer SVG for the repository asset; rasterize only where the host requires it.
- Use real product tone, not generic gradients; the banner is the visual promise the demo must keep.

### Demo GIF rules

- Open on the first meaningful action; no idle homepage hold.
- Show one job in 10–25 seconds. A five-stage flow can fit, but only if each stage is legible.
- Use 12–15 fps for UI GIFs, a fixed palette, and a final hold on the result.
- Prefer a persistent progress device over a decorative cursor. If the pointer is shown, its path must be causal; no orbiting dots.
- Type forms at a readable pace; never fill a whole form and submit in one frame.
- When a run dispatches a new session, enter that session immediately. Do not freeze on the management panel and later jump to the result.
- Caption what the viewer cannot infer. Keep a static poster or alt text for reduced-motion readers.

### Video rules

- 1080p at 30 fps for review; 4K/60 only after the cut is accepted.
- Use real motion blur for fast camera or UI moves; a clean frame is not a substitute.
- Keep captions in the safe area; test muted autoplay and a poster frame.
- Publish a GIF or PNG fallback with any README video.

## Motion workflow families

### Live evidence capture

Use a real server, real credentials path, and a real model round. Drive the browser with Playwright or an equivalent; assert DOM/API states before advancing. Record the whole interaction, then trim only at clean state boundaries. Add a stage rail, focus ring, or spotlight as a recording overlay, but keep the underlying pixels and interaction real.

Best for: README proof, changelog demos, bug reports, release evidence.

### Rebuilt-UI film

Rebuild only the states the film needs in HTML, put every string in a table, and drive the composition from a pure `seek(t)`. Use real output values, not invented numbers. This is the onetake family; see [Onetake method](onetake-method.md).

Best for: launch films, feature stories, localized cuts, camera moves that a screen recording cannot make.

### Programmatic video

Remotion or Motion Canvas gives code review and repeatability; it still needs a source of truth for UI and values. Use it when the artifact must be regenerated from data or reused across many products.

### Hybrid

Capture live evidence, then add a designed stage rail, captions, and a branded intro/outro. The overlay explains; the capture proves. Do not replace a captured action with a rebuilt frame while claiming it is the same run.

## Decision tree

- Need proof that the product really ran? **Live capture.**
- Need a 15–30 s launch story with camera movement? **Rebuilt film or onetake.**
- Need a repeatable monthly release asset? **Programmatic video.**
- Need a terminal workflow? **VHS or asciinema.**
- Need a static first impression? **SVG banner.**
- Need all of them? Keep one source visual language and one evidence log; do not let four artifacts tell four different stories.
