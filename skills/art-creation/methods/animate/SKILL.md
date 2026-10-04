---
name: animate
description: Use within art-creation when an interaction or visual sequence needs motion studies, timing, easing, continuity, or playable alternatives; not static styling or frame-rendered video export.
license: Apache-2.0; see LICENSE and NOTICE.md
---

# Motion Studies

Adapted from Impeccable's animate; see [upstream sources](../../references/upstream-sources.md). Read the [method contract](../../references/method-contract.md) and, for concrete motion construction, [motion recipes](references/motion-recipes.md).

## Specify the motion

Determine what movement should express: feedback, a relationship, spatial continuity, attention, or artistic character. Describe object, trigger/start, initial/final states, path, duration, easing, coordination, interruption behavior, and reduced-motion behavior when relevant. The brief determines whether a focal sequence or quiet feedback is appropriate.

## Build comparable playable studies

1. Choose distinctly different motion vocabularies for an open brief: spatial travel, reveal/occlusion, scale/depth, or shape change when appropriate.
2. Use CSS for simple interaction states; Web Animations API or an existing library for scrubbing, interruption, or sequences. Do not add a library for an effect the available runtime already expresses.
3. [The motion starter](templates/motion-study.html) demonstrates three real keyframe mechanisms, playback, scrubbing, duration control, reset, and recipe export without an external library. Replace its example subject and states.
4. Hold content, canvas size, and comparison duration fixed unless one is the experimental variable. Actually play the results; stills cannot demonstrate timing or easing. Display timestamped stills only as a disclosed fallback.

## Improve by mechanism

If feedback says abrupt, compare the initial speed, easing, or state discontinuity. If it says sluggish, inspect delay, travel distance, and when useful feedback occurs. If it says chaotic, inspect overlapping actions and attention shifts. Do not simply make every animation slower or apply the same curve everywhere.

Keep content visible if the script fails. For interface motion, check keyboard use, repeat/interruption, target-device performance, and reduced movement while retaining meaningful state feedback. Expressive character or film animation may need a different timing vocabulary from UI feedback.

For frame-accurate video, route to [Remotion video](../remotion-video/SKILL.md): wall-clock CSS/WAAPI playback is not a deterministic video export mechanism. Return playable source, a timing recipe, inspected states, limitations, and the user decision to the parent workflow.
