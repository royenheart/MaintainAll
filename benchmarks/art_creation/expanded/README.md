# Expanded art creation tasks

The [frozen suite](suite.json) adds 16 demanding three-turn tasks, with 12 development cases and four holdouts. It contains 48 prompts, 194 exact prompt-linked requirements, and 141 ordinal rating atoms. The existing [core suite](../suite.json) and [trajectory suite](../trajectory/suite.json) remain separate frozen datasets. These additions create task coverage; they are not model results, proof of improvement, or a validated estimate of real-world task difficulty.

The [coverage matrix](matrix.json) records case hashes, splits, capabilities, challenge axes, and rating dimensions. Every corrective turn changes a limited aspect while preserving accepted relationships and the unchosen alternative. Requirements only activate after the relevant wording is delivered. Cross-turn comparisons use actual retained artifacts rather than the solver's claim that something was preserved.

## 1. Coverage matrix

| Case | Split | Backend | Main relational challenge |
| --- | --- | --- | --- |
| expanded-reference-evidence-transfer | Development | SVG | Exact-photo annotation, nonliteral reference transfer, hierarchy under added copy, local pattern density |
| expanded-editorial-density | Development | SVG | Open space and grouped details, fixed title/column, small-view hierarchy |
| expanded-palette-evidence | Development | SVG | Palette provenance, item-price association, measured-versus-claimed contrast, row-local edit |
| expanded-reference-medium-conflict | Holdout | SVG | Conflicting reference relationships transferred to a new medium |
| expanded-avatar-silhouette-ownership | Development | SVG | Wearer-side attachment across views, face-first thumbnail, material versus volume |
| expanded-avatar-layer-boundaries | Development | SVG | Semantic garment layers, selective counterfactual edit, drawing versus Live2D export |
| expanded-costume-function-detail | Development | SVG | Functional attachment, bent-arm clearance, pattern versus pocket boundary |
| expanded-avatar-accessory-conflict | Holdout | SVG | Competing accessories, body-side ownership, a correction limited to one view |
| expanded-flow-field-corridor | Development | SVG and Python | Seeded coherence, protected title corridor, global direction versus local variation |
| expanded-pattern-grammar-seam | Development | SVG and Python | Periodic edge continuity with local irregularity, fixed centers, color-only repair |
| expanded-responsive-state-ownership | Development | Browser | Shared content ownership through responsive rearrangement and interrupted selection |
| expanded-attached-motion-retarget | Development | Browser | Boundary attachment through motion, interrupted reversal, reduced-motion equivalence |
| expanded-browser-overlay-priority | Holdout | Browser | Actual reference image, local panel ownership, focus/scroll retention, close/reopen continuity |
| expanded-native-courtyard-grammar | Development | Blender | Bay/entrance grammar, connected threshold, controlled camera/envelope, native parameter probe |
| expanded-native-garment-clearance | Development | Blender | Shoulder anchoring, front/side clearance, material versus silhouette, native shell-offset probe |
| expanded-native-room-sightlines | Holdout | Blender | Privacy versus occlusion, floor contact, partition/table boundary, fixed-camera height probe |

The ten static tasks include reference analysis, editorial work, costume planning, and two executable rule systems. Three tasks require actual browser interaction and motion. Three require actual native Blender scenes. These tasks emphasize observable relationships and counterfactual edits, not element, ornament, frame, or polygon counts as aesthetic proxies. Artifact counts and image dimensions specify delivery and inspection conditions only.

## 2. Inputs, licenses, and provenance

The [asset manifest](assets/manifest.json) includes four Met Open Access object photographs copied byte-for-byte from the existing asset collection, with unchanged SHA-256 values, source pages, API metadata, public-domain flags, and CC0 provenance. The copies keep the new suite self-contained because the case contract permits shared relative assets only inside the suite boundary. Publication can deduplicate equal image hashes across suites. Existing Met metadata JSON files are copied unchanged as provenance snapshots.

| Input | Dimensions | Provenance |
| --- | --- | --- |
| met-125959.jpg | 308 × 624 | Met Open Access photograph, Kimono |
| met-81718.jpg | 500 × 625 | Met Open Access photograph, Mantua |
| met-45406.jpg | 192 × 625 | Met Open Access photograph, Piece of Cloth for Kimono with Pattern of Stylized Rosettes |
| met-436535.jpg | 599 × 477 | Met Open Access photograph, Wheat Field with Cypresses |
| selection-rail.png | 960 × 600 | Original authored relationship schematic, CC0 |
| attached-reveal.png | 960 × 600 | Original authored relationship schematic, CC0 |
| overlay-priority.png | 960 × 600 | Original authored relationship schematic, CC0 |
| courtyard-bays.png | 960 × 600 | Original authored relationship schematic, CC0 |
| garment-section.png | 960 × 600 | Original authored relationship schematic, CC0 |
| room-sightline.png | 960 × 600 | Original authored relationship schematic, CC0 |

The six new schematic references are authored SVG drawings with actual CairoSVG PNG renders, not generated photographs or original-session screenshots. Each visibly labels itself an authored schematic; its editable source and source hash are recorded. MaintainAll dedicates these original schematic SVG/PNG assets to the public domain under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). They convey spatial or ownership relationships without prescribing a finished style. They do not establish structural feasibility, a physical simulation, or a faithful replay of the user's private application state.

All task wording and later corrections are self-authored synthetic briefs. The public cases do not expose private messages or attachments. The existing trajectory cases retain their own separate session-derived provenance; these expanded tasks must not be relabeled as actual user feedback or acceptance.

## 3. Execution and evidence contracts

Every task requires `real_images` and `exact_resume`. Static tasks additionally require `svg`. Browser tasks additionally require `browser_capture` and `playable_motion`. Native tasks additionally require `blender` and `native_scene_reopen`. Capability availability is resolved by the execution backend. A missing native backend is unavailable, rather than an invitation to substitute a static drawing.

SVG tasks retain named editable sources and real PNG renders. General sheets use 960 × 720; small avatar/social previews use 160 × 160, and the direct kimono annotation uses the original 308 × 624 proportions. Source output declarations record each size individually.

Browser tasks deliver self-contained `index.html`, 1280 × 800 desktop and early/middle/late captures, a 390 × 844 mobile capture, `evidence.json`, and notes. Native tasks deliver one `scene.blend` containing labeled alternatives, `source.py`, comparison and side renders, a parameter-probe render, `evidence.json`, and notes. Native PNGs use 640 × 480 to bound rendering cost. All tasks allow at most 8 MiB per file, 32 MiB per workspace, and 600 seconds per turn.

Solver-produced `evidence.json`, notes, and screenshots are declared deliverables, not trusted proof or ratings. A verifier must independently inspect the saved HTML or reopen the native scene where supported; an independent reviewer evaluates each atom using its declared evidence. A generic native reopen or bounded scene edit does not establish that every `source.py` parameter works. Generator reproducibility, local edit scope, continuity through interruption, and target-ready Live2D/VRM claims remain separate checks. Missing evidence yields an unverifiable atom; it must not become a successful quality rating based on the solver's explanation.

The fixed ordinal scale is 0 for contradicted/absent relationships, 1 for partial or ambiguous relationships, and 2 for observable consistent relationships, with task-specific anchors where needed. Unverifiable remains separate. Ratings across different dimensions, task releases, reference variants, runtime versions, or review cohorts must not be collapsed into one aesthetic score.

## 4. Splits and release policy

Development tasks can guide implementation and skill iteration. Four holdouts span reference interpretation, costume/avatar planning, browser interaction, and native 3D. Their prompts and rubrics are evaluator-side task data; skill authors should not load them before freezing the tested skill snapshot. A holdout can only support a claim about an unseen task if it has not already informed the compared skill versions. Record exposure if it is inspected, and do not silently reuse it as an unseen future test.

A task release fixes prompt wording, asset bytes, requirements, activation turns, artifact contracts, and anchors. Any semantic change requires a new release/version and new hashes. Do not rewrite a historical suite or pool its ratings with a later task release. Changes only to this README do not alter the dataset identity.

At one repeat, all 16 cases require 48 generation calls per arm; 12 development cases require 36 calls per arm. A three-arm comparison requires 144 calls for the full suite or 108 for development only. Three repeats increase these counts threefold. These are planning counts, not recorded runs. Local execution is manual and must use the framework's frozen plan and explicit call budget. The current per-experiment ceiling is 54 calls; larger comparisons must be partitioned into separately frozen, traceable batches rather than submitted as one oversized plan. Offline contract tests and CI packaging do not consume model calls or establish completion of a formal evaluation.

## 5. Offline verification

Run from the repository root, using the configured framework environment:

```sh
PYTHONPATH=benchmarks/skill_bench/src python -m skill_bench.cli validate --suite benchmarks/art_creation/expanded/suite.json
PYTHONPATH=benchmarks/skill_bench/src:benchmarks/skill_bench/tests python -m unittest test_expanded_dataset -v
```

The 12 dataset regression tests cover frozen suite/case/asset hashes, 12/4 split and domain coverage, exact requirement quotes, non-retroactive activation, declared evidence artifacts, licensed exact-byte Met reuse, authored-schematic dimensions/provenance, backend capability separation, real motion/native delivery requirements, and bounded stable artifact paths. These checks validate contracts and coverage metadata. They do not run the tasks, determine aesthetic quality, validate a general visual judge, or prove that all runtime behaviors are supported.
