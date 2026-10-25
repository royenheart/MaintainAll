---
name: animate
description: Use within art-creation when an interaction or visual sequence needs motion studies, timing, easing, continuity, or playable alternatives.
license: Apache-2.0; see LICENSE and NOTICE.md
---

# Motion Studies

Adapted from Impeccable's animate; see [upstream sources](../../references/upstream-sources.md). Read the [method contract](../../references/method-contract.md) and, for concrete motion construction, [motion recipes](references/motion-recipes.md).

## Specify the motion

Determine what movement should express: feedback, a relationship, spatial continuity, attention, or artistic character. Describe object, trigger/start, initial/final states, path, duration, easing, coordination, interruption behavior, and reduced-motion behavior when relevant. The brief determines whether a focal sequence or quiet feedback is appropriate.

## Build comparable playable studies

1. Choose distinctly different motion vocabularies for an open brief: spatial travel, reveal/occlusion, scale/depth, or shape change when appropriate.
2. Use CSS for simple interaction states, or Web Animations API and suitable libraries for scrubbing, interruption, and sequences.
3. [The motion starter](templates/motion-study.html) demonstrates three real keyframe mechanisms, playback, scrubbing, duration control, reset, and recipe export without an external library. Replace its example subject and states.
4. Hold content, canvas size, and comparison duration fixed unless one is the experimental variable. Play the studies to compare timing and easing; use timestamped stills for key states.

## Improve by mechanism

If feedback says abrupt, compare the initial speed, easing, or state discontinuity. If it says sluggish, inspect delay, travel distance, and when useful feedback occurs. If it says chaotic, inspect overlapping actions and attention shifts.

For interface motion, check keyboard use, repeat/interruption, target-device performance, and reduced movement while retaining meaningful state feedback. Develop character or film timing from the expressive brief.

For frame-accurate video, use [Remotion video](../remotion-video/SKILL.md). Return playable source, a timing recipe, key states, and user feedback.
