# Agent Note: Art creation skill

Status: implemented — a creative entrypoint routes progressive exploration to adapted construction methods and executable resources.

## Problem

The repository's reusable skills focus on engineering. A non-expert needs to learn
how visual references work and refine an imprecise artistic idea through visible
alternatives without first mastering professional terminology.

## Decision

- [Art Creation](../../../../skills/art-creation/SKILL.md) is one discoverable
  entrypoint with two selectively loaded capabilities:
  [style analysis](../../../../skills/art-creation/references/style-analysis.md)
  and [iterative creation](../../../../skills/art-creation/references/iterative-creation.md).
- The analysis instructions preserve the requested two-chapter teaching report,
  twelve one-sentence overview items, seven detailed sections, and direct annotation
  of the actual input. Instructions are maintained in English; reports use accessible
  Chinese unless the user requests otherwise.
- Exploration uses language and inspectable programs first, visible contrasting
  directions, user feedback, and controlled refinement. Preference hypotheses stay
  separate from observations and user-confirmed choices. Multimodal assistance is
  scoped to a concrete gap rather than used by default.
- The iterative workflow indexes seven nested method skills: algorithmic art,
  canvas design, animation, visual variants, procedural 3D, browser 3D, and video.
  Their focused references and starters are loaded only for the active question.
  Nested SKILL.md files are linked resources; the layout does not rely on the host
  automatically discovering every child. The shared
  [method contract](../../../../skills/art-creation/references/method-contract.md)
  carries constraints, tested hypotheses, visible results, exact recipes,
  limitations, and decision status between the workflow and each method.
- Five methods adapt inspected upstream instructions. Anthropic and Impeccable
  copies retain Apache 2.0 licenses and applicable notices; the video adapter uses
  the explicitly MIT-licensed official Remotion Codex plugin. The
  [source inventory](../../../../skills/art-creation/references/upstream-sources.md)
  explains modifications, new resources, and omitted runtime assumptions. The
  [source lock](../../../../skills/art-creation/upstream-lock.json) preserves exact
  revisions and original/current hashes. Original resources retain the repository's
  [MPL 2.0 license](../../../../skills/art-creation/LICENSE), included for standalone
  packaging. Scene and browser 3D methods are original.
- The adapted procedural viewer supplies a working seeded example, fixed steps,
  deep reset, and recipe export. Original resources include an editable SVG,
  playable native-browser motion, comparison/selection UI, a frame-derived video
  composition, and an actual Three.js scene. Impeccable helper executables and
  proprietary event/application protocols are not required by the portable viewer.
- The standard-library
  [scene generator](../../../../skills/art-creation/methods/scene-3d/scripts/scene.py)
  exports a closed OBJ mesh, recipe, and SVG from the same geometry. It separates
  model parameters from viewpoint and refuses to replace existing iteration
  artifacts. Its projection/shading limitations are explicit. The browser example
  uses an open lathed surface, so the two starters do not imply identical geometry.
- [Visual methods](../../../../skills/art-creation/references/visual-methods.md)
  describe inspection/display options. The
  [practice review](../../../../skills/art-creation/references/practice-review.md)
  compares primary sources and distinguishes research evidence from adaptations.
- This domain skill is independent of the engineering
  [model policy](../../../../skills/model-policy/SKILL.md). Engineering task tiers
  do not establish artistic or multimodal capability; no artistic tier is invented.

## Alternatives considered

- **Separate top-level skills for each creative capability:** independent discovery
  is possible, but a shared entrypoint better matches the requested extensible index
  and keeps evidence, feedback, and tool-selection rules in one place.
- **One large prompt loaded for every creative request:** would mix strict report
  formatting with short feedback rounds and load unrelated detail; references keep
  those contracts distinct.
- **Adopt external skills unchanged:** required branding, helper protocols, fixed
  aesthetics, and self-refinement would conflict with preference-driven exploration.
  Adapters retain useful construction mechanisms and explicitly record changes.
- **Only name possible representations:** gives a non-expert no concrete path from
  feedback to an improved artifact. Focused method guides and executable starters
  make that path inspectable without requiring every renderer.
- **Bundle full applications or install runtime packages globally:** project versions
  and actual media needs differ. Resources declare dependencies and offer scoped
  fallbacks; loading this skill does not install a video application or modeler.

## Consequences

The complete [skill directory](../../../../skills/art-creation/) must be distributed
with its methods, references, templates, scripts, licenses, notices, and source lock;
copying only the entrypoint loses construction instructions and resources.
The [repository index](../../../../README.md) links the skill and research. No plugin
runtime, external installation, or user model configuration is changed.

Validation covers all eight skill entrypoints, relative links/anchors, source/license
hashes, JavaScript syntax, and manual analysis-contract review. The
[scene tests](../../../../tests/test_art_creation.py) pass three cases covering
closed/oriented topology, repeatable exports and camera independence, and invalid
input/baseline preservation. Static SVG and actual mesh previews render successfully.
Headless Chrome with p5.js 1.7.0 and Three.js 0.180.0 verifies procedural replay,
parameter changes/reset/export, actual motion playback and reduced motion,
explicit selection with live child recipe capture, and browser-3D edits/reset/resize.
Browser checks use locally served matching runtime files; they do not establish
that a target user's CDN connection or graphics driver works. Screenshots were
inspected and no browser page errors occurred.

The Remotion starter passes JavaScript syntax validation, but no Remotion project
or Blender runtime is installed or rendered by this change. Automated selection
checks do not represent user aesthetic approval. Model performance and creative
satisfaction require actual inputs and feedback in the target environment.
