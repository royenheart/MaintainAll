# Progressive Game Creation

Start with the player's intended experience, a rough description, sketch, or reference. Develop the game in its chosen engine from the first playable experiment and retain that project through refinement. Establish the [feedback path](feedback-setup.md) using native playback, compatible Web export, or streamed native execution. Use [Game engine construction](../methods/game-engine/SKILL.md) for Godot execution and [Iterative creation](iterative-creation.md) for the shared feedback loop.

## Discover through play

1. Identify the player, intended feeling, main action, immediate consequence, and likely play session. Record platform and input assumptions. Show a small sketch, scene, or state diagram to clarify the unresolved idea.
2. Turn the next uncertainty into a testable hypothesis. Build contrasting native scenes or parameter profiles at the fidelity needed to test it. A movement question needs controls; an atmosphere question needs enough art and sound to convey the intended context.
3. Deliver a working play link or native build with a short action to try. Present the same goal, camera, and level when comparing movement profiles; vary those conditions when they are the question under investigation.
4. Ask a few atomic questions tied to that build and state. Offer A/B choices or Yes / No / Not sure answers; let the user describe an unexpected result in ordinary language. Present the relevant image or playable moment alongside the question.
5. Preserve accepted decisions, record rejected interpretations, and change the smallest useful set of dependent properties. Once the central experience works, build one representative playable slice with the necessary art, sound, interface, progression, and recovery flow before expanding content.

Adapt the number and order of experiments to the unresolved decisions. Carry the selected genre, control scheme, and visual direction forward as accepted inputs.

## Atomic game dimensions

Use only the rows that matter to the current experiment. Follow [Intent and evidence](intent-and-evidence.md) for observation, hypothesis, preference, and dependency records.

| Dimension | Useful atoms and evidence |
|---|---|
| Player experience and core loop | Player action, observable state change, feedback, meaningful choice, reward, and what motivates another attempt; compare actual play reactions |
| Controls, movement, and camera | Input-to-response timing, acceleration, stopping distance, turn behavior, framing, tracking lag, and motion comfort in a named movement state |
| Rules, interaction, and level space | Collision relationship, reachability, information needed for a decision, interaction range, goal conditions, failure consequences, checkpoint and restart behavior |
| Progression and economy | A resource's source, storage, conversion, cost, and sink; decision frequency, alternative strategies, and feedback loops under stated scenarios |
| Characters, world, and narrative | Role readability, player motivation, spatial landmarks, reveal order, and continuity between narrative and allowed actions; use [Fashion and avatar design](fashion-design.md) when relevant |
| Visuals, animation, and effects | Silhouette, palette relationships, state readability, anticipation, impact and recovery timing, foreground/background separation; use [Style analysis](style-analysis.md) for references |
| Audio | Which event triggers a cue, its attack and decay, relative loudness, spatial location, repetition, and whether the required message remains available without sound |
| Interface, teaching, and accessibility | What the player can perceive, understand, and operate in a concrete state; readable labels, input alternatives, focus order, feedback and recovery |
| Runtime and delivery | Target device/browser, input and viewport, loading, measured frame time, save persistence, build identity and export compatibility under the actual tested conditions |

Stop splitting when one observation or short play experiment can settle the next decision. Numeric, categorical, relational, temporal and preference answers are all useful. Evaluate each property against its intended player experience, recording measured behavior and player preferences separately.

An atom can record `id`, `parent_intent`, `object/state`, `question`, `response_type`, `observation_or_target`, `dependencies`, `accepted_baseline`, `evidence`, and `status`. Store only fields needed by the decision. Attach human responses to the build/profile and question version that produced them.

For example, “responsive movement” may become “after releasing a direction at full speed, does the stopping distance feel right?” Compare observable stopping distances in the same level, then ask which distance is preferred.

## Keep iteration resumable

Keep a compact project brief, a current set of atoms, accepted decisions, editable engine source, and build-linked feedback. A decision record can carry `build_id`, `source_revision`, `profile`, `question_id`, `answer`, and `evidence_ref`. Revisit a decision when its dependencies change.

The skill guides the collaboration. A future enforced workflow can consume these records, validate stage transitions, wait for user input, and schedule construction or verification. Read [Workflow orchestration](../methods/game-engine/references/workflow-orchestration.md) when designing that runtime.
