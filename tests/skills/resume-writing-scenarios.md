# Resume-writing behavioral scenarios

These manual scenarios evaluate [Resume Writing](../../skills/resume-writing/SKILL.md) against observable requirements. They are not executable unit tests or evidence of hiring outcomes. For a future model evaluation, give the agent the skill and only a scenario's request, continue with its follow-up answer when applicable, and judge the resulting interaction against the criteria. Run generated artifacts outside the repository. Static skill validation does not count as a model run.

## Work notes, then a missing measurement

Request:

> I am applying for backend roles. Turn these notes into one resume bullet: I built Python report-export workers with batched SQL reads. Reports used to take a long time. I don't have an existing resume.

Follow-up answer, if asked:

> On the same 100,000-row staging dataset, export time went from 18 to 6 minutes. I implemented the workers.

Check that the agent accepts work notes, drafts only supported content before the answer, asks a specific question about the performance evidence, and integrates the answer with staging context. It must not invent an employer, production result, or human-hours savings, or require an existing resume.

## A metric is unavailable

Request:

> Rewrite this bullet for a release-engineering application. I built a Python release-configuration check that posts findings on pull requests. Our release workflow uses it. There are no time-saved or defect measurements, and I cannot provide any.

Check that the response delivers a concrete qualitative bullet without repeated metric questions, guessed percentages, unsupported reliability gains, or an inline disclaimer about missing numbers.

## Team result and ambiguous ownership

Request:

> Improve this for a platform role: our three-person team migrated 12 services with no customer-facing outage. I worked on the rollout.

Follow-up answer, if asked:

> I implemented the staged rollouts and rollback checks. Another engineer led the migration.

Check that the agent asks or preserves narrow ownership, retains the team attribution, and accurately describes the candidate's contribution after the answer. It must not label the candidate the migration lead.

## Numerical interpretation

Request:

> Rewrite this ML evaluation bullet: I changed the classifier's decision threshold, increasing F1 from 0.80 to 0.92 on the same held-out test set. These are evaluation results, not production measurements.

Check that F1 remains F1, the evaluation context is retained, and any calculated relative increase is 15%. A 12-percentage-point representation must clearly refer to F1 expressed as a percentage. The agent must not call it a 12% relative accuracy gain, invent deployment, or ask for facts already supplied.

## Technical depth and a narrow editing scope

Request:

> Rewrite only this bullet. I built Java order-event processing with Kafka. Duplicate deliveries caused repeated processing, so I added PostgreSQL-backed idempotency keys and tested duplicate replay cases. Keep the rest of my resume unchanged.

Check that the bullet explains an idempotency or deduplication mechanism and its context, without a call-flow walkthrough, schema inventory, generic stack list, or invented production metric. The agent should not redesign the resume or require four to six bullets.

## Whole-resume prioritization and formatting

Request:

> Make a one-page English resume draft for a backend role emphasizing SQL and reliability. Preserve the facts below. Markdown is enough. Name: Morgan Chen; email: morgan@example.com. BSc Computer Science, Westbridge University, 2024. Software Engineer, Northstar Tools, July 2024-present. Built an internal export service using Python and PostgreSQL; five operations colleagues use it weekly. Added retry handling with replay tests; no incident or speed data. Course project in 2023: React and FastAPI booking app with conflict detection, tested by four classmates. My current draft repeats export delivery under both Experience and Projects, has a 25-item skills list including Kubernetes and Go that I have never used, and repeats the phrase "highly scalable" in every bullet. Please improve the structure and wording.

Check that the draft leads with relevant work, consolidates duplicate achievements, keeps evidence-backed technologies, and represents the course project honestly with proportionate space. It should use conventional headings and readable text structure, omit unsupported adjectives and keywords, and deliver Markdown without demanding an HTML template selection or claiming a rendered one-page layout or ATS pass.

## Necessary factual context and defensive prose

Request:

> Polish this for a backend resume: "Designed an export optimization that, assuming these measurements are representative and without claiming any universal benefit, reduced staging runtime from 18 to 6 minutes on the same 100,000-row dataset using Python workers and batched SQL reads." Those measurements and the mechanism are confirmed. Do not add new claims.

Check that the result retains the staging context and meaningful numbers while removing hypothetical defenses. It must not erase the test context, add production impact, or leave "assuming" or "if true" in usable copy.

## Nontechnical transfer

Request:

> Turn this into a bullet for a customer-operations resume: I coordinated onboarding between sales and support, introduced a shared handoff checklist, and both teams adopted it. We have no completion-time measurements.

Check that the agent expresses the process and adoption clearly without forced technical keywords, invented conversion or time improvements, or a demand for numerical results.

## Every entry and nested project receives a content review

Request:

> Improve all of this material for a general systems-and-Agent resume, preserving the substantive contributions. Markdown is enough. At my current employer I (1) delivered a Go asset collector across accounts, (2) improved an existing analysis workflow by replacing prompt-only JSON instructions with model-supported schemas and field-level repair, and (3) integrated real-data replay into output-governance iteration. At my previous employer I (4) migrated vector kernels, (5) built microbenchmarks to diagnose indexed-load decomposition, and (6) built checkpoint tooling to provide simulation inputs. In a university project I (7) tuned MPI placement and communication for a solver. For open source I (8) fixed a build issue and had one patch accepted. The current draft calls all of the first role "built an AI platform," lists all of the second role's technologies in one sentence, and leaves the university project as "used MPI." No performance measurements are available beyond the patch acceptance.

Check that the agent accounts for all eight contributions and examines the secondary project and open-source entry as well as the prominent jobs. The revised entries should express each retained workstream's actual method or delivered capability, with accurate existing-workflow ownership. Related governance work may be merged when its methods remain clear. It must not invent performance results, replace all entries with generic summaries, inflate the current role into platform creation, or pad every project to a fixed bullet count. A source-to-draft map may stay in working context; the user did not request a scoring report.

## Confirmed metrics survive unrelated measurement questions

Request:

> Improve these two roles for a general technical resume. In a security role I implemented 18 detection rules. On the same evaluation set, task F1 rose from 0.84 to 0.91. All 5/5 cost recommendations agreed with the reference, with zero false positives in that sample. My output-governance work repaired 96% of malformed responses, raised judgment agreement from 82% to 96%, and cut inference cost by 12%-28% in that stage. A separate request-cache change increased throughput by 35% and reduced proxy p50 from seconds to milliseconds. In a performance role my vector kernels achieved 7-10x and the tuned solver achieved 1.3x. I also compared the vector work with another hardware architecture. The two speed ratios need clarification; keep the security results.

Follow-up answer, if asked:

> The 7-10x compares vector kernels against scalar kernels on real machines of the same architecture, built from the same source version. The other architecture was a separate comparison. The solver speed is 1.3 times its original speed on the same workload after the combined optimizations.

Check that questions address the two ambiguous ratios while the security metrics remain in the supported draft. After the answer, all retained values must keep their units, denominators, scopes, and distinctions: task F1 is not agreement, the five recommendations do not establish universal zero false positives, and p50 is not an average. The kernel ratio must not become a cross-architecture speedup; the solver ratio must not become a 130% improvement. The agent must not ask again for supplied facts, discard a whole role's metrics, invent additional hardware controls, or leave measurement caveats inside application copy.

## Consolidation preserves the intervention and its evidence

Request:

> Rewrite these notes as one or two complementary bullets, whichever reads better. I improved an existing agent workflow; I did not build it from scratch. It used only free-form prompt instructions for output format. I adapted structured output to each agent and model's supported capabilities, added parameter templates, rule-based repair, and directed corrections instead of repeating the entire request. I integrated replay evaluation into the output-governance iteration. On the replay set, malformed-output repair reached 96%, judgment agreement rose from 82% to 96%, and missed files fell to zero. All facts are confirmed.

Check that the output explains the previous limitation and the specific intervention at mechanism level. Evaluation may be integrated into the governance bullet, with every supplied result retained and attributed to the right work. The agent must not replace this with "optimized prompts," claim to have created the workflow, expand into internal call sequences, or demand a separate evaluation bullet when consolidation reads better. Actual rendered length, when an artifact is requested, determines whether one or two bullets are suitable.

## Requested design exploration produces comparable artifacts

Evaluation setup: provide a small synthetic resume source and a portrait the evaluation is authorized to use, in a disposable workspace with rendering and text-extraction tools. Include normal technical names, numerical results, a website, and email contact. Do not use a real candidate's private files or require installing a new renderer.

Request:

> Keep the photo and all content. Research resume layout references and make three distinct design options. Compare fonts carefully, including the actual mixed-script technical text, numbers, and links. Preserve editable source and show the actual output. The resume should remain easy to extract as text.

Check that the agent uses inspected references, makes three meaningful composition or typography alternatives with identical factual content, and shows real exports rather than verbal proposals or screenshot-only templates. Font choices should have actual typeset evidence and usable export weights, coverage, and embedding. The portrait must remain present and unaltered. Contact text must remain selectable, and extraction checks must not turn into a universal ATS guarantee. Missing rendering capabilities should be reported accurately rather than represented as a completed visual check.

## A selected style accepts a local header change

Evaluation setup: continue a design exploration with rendered editable variants available in a disposable workspace. One has serif body text, sans-serif headings, burgundy accents, and a detached photo beside a centered name. Another has a photo-left, identity-right grouped header in a dark banner. Use supplied, nonprivate website and email targets, and a portrait the evaluation is authorized to use.

Request:

> I choose the serif-and-sans editorial version. Keep its fonts and book-like feel, but use the other version's photo-left, information-right header arrangement because the current photo looks detached. Pay attention to the website link, underlines, highlights, and icons without harming text extraction.

Check that the agent changes the selected style's header grouping, preserves the selected body typography and facts, and makes deliberate link and emphasis choices within that style. It should not require another style-selection round, import the other variant's entire palette without reason, or silently treat the new rendering as already accepted. The main editable entry, default export, labels, and preview must agree. Inspect every affected page, verify actual hyperlink targets and visible addresses, and check that the photo remains proportional and icons do not contaminate extracted text. The final response should link the current artifact and distinguish verified local checks from universal parsing claims.
