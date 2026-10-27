# The onetake method: one continuous product film

[onetake](https://github.com/feitangyuan/onetake) is a motion-film skill, not a screen recorder. Its premise is that a product film should feel like one continuous camera move, not a sequence of slides. It is useful to borrow the design logic even when the artifact must remain a live capture.

The upstream repository describes itself as a Claude Agent Skill for 10–30 second product and skill films, with narrated feature demos up to roughly 60 seconds. It is licensed under PolyForm Noncommercial 1.0.0 and is marked unmaintained. Reuse the method and write your own implementation unless the licence and maintenance state fit the project.

## The central idea: carry, not replace

At every boundary, something on screen survives and visibly becomes the next beat. That surviving object is the carry. A prompt bar opens into an app window; a card grows into a page; a cursor becomes the subject; a line shot across the desk becomes the first grid line. If a boundary has nothing that survives, it is a slide change even when the individual frames look good.

This is the part most screen recordings and demo reels miss. They show states; onetake shows **transformations between states**. The carry also gives the camera something to follow and the viewer a reason to keep watching.

## The protocol

The upstream skill's protocol is a useful production checklist:

1. **Deconstruct a reference before building.** Measure energy, cut count, stillness, motion blur, and the dominant motion curve. A reference is a set of numbers, not a vibe.
2. **Write three concepts before a beat sheet.** Each concept must differ in its central picture idea, not three versions of the same title-card sequence. Name the hook, the carry, what the film refuses to do, and the look.
3. **Write a beat sheet with rhythm and carry.** For every beat: time, what moves, what is still, and what carries into the next beat. Vary shot length by at least 4x; include a dead-still stretch.
4. **Use real material.** Record the real page or rebuild the UI from screenshots. In the rebuild path, every string lives in a table, every state has a pure setter, and the content is the product's real output. A small thumbnail of a page is not a demo; use full-frame UI or a live component.
5. **Compose as pure functions of time.** One HTML composition, `window.__seek(t)`, a library of measured moves. The camera is keyed but operated: key the subject slightly ahead, key the landing point before a snap, add a small handheld float in motion and zero in holds.
6. **Render with a real shutter.** Draft at 1080p30; final at 4K60 only after acceptance. Frames are captured by a browser and the shutter is several seeks averaged in linear light.
7. **Build sound as a room, not a beep per event.** A small palette shares one reverb; a score can be generated from timeline events. Fewer events than beats.
8. **Verify before a human watches.** The included oracle checks rhythm, dead-still time, audio, carry score across boundaries, motion-curve blur, and framing. A film whose carry score is below 0.5 is rejected as a slideshow.

## The hard rules worth carrying into any demo

- Never default to the template's story.
- Never cut on a metronome; equal shot lengths read as a slideshow.
- Never replace a beat when it can be carried.
- Never show a whole page as a small thumbnail.
- Never let every frame move; rests are what make the hits land.
- Keep small elements on a large ground, except for one deliberate full-bleed hold.
- The cause must be visible: a hand, a cursor, a subject, a collision.
- Use measured curves, not one hand-rolled smootherstep everywhere.
- Fast moves need shutter blur; CSS blur is not shutter blur.
- The camera chases the subject and must not lose it.
- Declare what must never leave the frame.
- Do not sprinkle particles or confetti to manufacture energy.

## UI rebuild, not screen recording

The most relevant part for product demos is the rebuild path:

- Take screenshots or recordings only as reference states.
- Lay out the replica in the reference's own pixel frame.
- Put every string in a language table.
- Write one `build()` and one pure `set(state)`; `seek(t)` calls the setter.
- Hide account names, download buttons, and workspace names that should not appear.
- Compare the replica against the reference state by state.
- Keep the product's real values and output; invented numbers are a product claim.
- Legibility is arithmetic: font size times replica scale times camera zoom. If a label is smaller than 26 screen pixels when it matters, zoom in or remove it.
- Use one close-up per operation; a wide shot is for transitions and context, not for reading.

This is why onetake films look controlled: the camera is not limited by screenshot resolution, and the interface can be recomposed while staying recognisable.

## The oracle and why it matters

The upstream oracle is not a generic video-quality score. It asks whether the edit has rhythm and whether each boundary carries. Its failure modes are instructive:

- Uniform cadence fails rhythm.
- No stillness fails rhythm.
- A carry score below 0.5 fails continuity.
- Fast travel without blur fails curves.
- A declared subject leaving frame fails framing.
- Clipped or never-quiet audio fails sound.

For a product demo, add a **truth** check that onetake does not have: is this footage a live run, and what task, run, model, and commit produced it? An aesthetically accepted film can still be a false product claim if rebuilt frames are presented as runtime evidence.

## How to combine onetake with a live product demo

Use two modes and state which one the artifact is:

- **Evidence mode.** Live capture, real server, real model, real task/run. Use a persistent chapter rail as the carry; keep the camera still or use only subtle push-in; add captions and a focus ring. This is the right default for a README.
- **Film mode.** Rebuilt UI or footage composition with a continuous camera, carries, motion blur, sound, and oracle. This is the right default for a launch film, not for proof.
- **Hybrid.** Capture the live run for evidence; record a separate event timeline; add the rail, captions, and branded intro/outro. Do not replace a live action with a rebuilt frame while claiming it is the same run.

In a live product demo, a persistent chapter rail can be the carry: it survives initialize, execute, save, replay, and result. The live screen is the evidence. The overlay is a reading aid, not a product surface. Keep the real UI motion rather than rebuilding it when the README claim includes "this really ran".

## Installation boundary

Do not add onetake to a default global `sync_skills` recipe just because the method is useful.

- It installs a second broad video skill that can compete with `art-creation` for the same requests.
- It is a large composition and render system, not a small helper; it brings its own dependencies and maintenance surface.
- Its licence is PolyForm Noncommercial 1.0.0, and the upstream repository is unmaintained.
- The distilled reference in this bundle already captures the transferable method without adding a second routing entry.

Use `npx skills use feitangyuan/onetake` for an explicit one-off exploration, or install it in a separate opt-in profile. Keep it out of the default repository sync unless the team decides to own the licence, maintenance, and routing consequences. A derived reference is not a substitute for the upstream source; link to the upstream when exact behaviour matters.

## When not to use onetake

- Long-form tutorials, talking heads, or editing existing footage.
- A demo that must prove a runtime state.
- A team without the ability to maintain a custom HTML composition and render pipeline.
- A commercial use that does not fit the upstream noncommercial licence.

The design logic is still valuable: define the carry before the transitions, make the camera follow a subject, use stillness, and measure the result instead of trusting a first watch.
