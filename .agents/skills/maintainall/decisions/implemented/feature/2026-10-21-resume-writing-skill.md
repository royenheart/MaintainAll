# Decision: Evidence-led resume writing

Status: implemented — a standalone resume skill combines selective follow-ups, factual accomplishment writing, and readable presentation guidance.

## Problem

Resume guidance often specifies action verbs, numerical results, and a template without deciding what to do when the candidate's materials lack evidence. Generic rewriting can invent impact, inflate personal ownership, overload technical details, or produce a polished technology inventory without a coherent case for a role.

## Decision

[Resume Writing](../../../../../../skills/resume-writing/SKILL.md) accepts existing resumes and raw work notes and reads the supplied context before asking questions. A full review accounts for each contribution across every supplied entry, including secondary projects and separate workstreams within a job, before condensing the story for the target role. A lightweight source-to-draft map preserves traceability through rewriting, merging, movement, and deliberate omission; it stays in working context unless requested as a deliverable. Questions address the exact missing ownership, outcome, measurement context, or conflicting fact. Supported edits continue while a dependent claim awaits an answer. An ambiguous comparison does not remove unrelated supplied metrics; unavailable evidence leads to a narrower result or concrete qualitative wording.

The entrypoint owns the reusable writing rules. [Entry review and evidence examples](../../../../../../skills/resume-writing/references/interviewing-and-evidence.md) explain contribution-level review, targeted interviewing, measurement preservation, numerical interpretation, and the appropriate depth of technical explanation. [Layout and delivery](../../../../../../skills/resume-writing/references/layout-and-delivery.md) covers readable defaults, conditional visual exploration, header composition, real font specimens, hyperlinks and icons, and checks against the actual requested artifact. [The research review](../../../../../../skills/resume-writing/references/research.md) compares three source-pinned industry skills with recruiter, career-center, ATS-provider, and user-supplied sources, distinguishing guidance and practical workflow rationale from measured outcomes.

XYZ supplies outcome, measurement, and method; STAR supplies context during evidence gathering. Neither forces a sentence order or a metric for every bullet. A project overview explains purpose and defining technologies; four to six bullets are a starting point for a substantial featured project, with fewer for secondary work. Mechanism-level detail establishes technical substance without narrating internal implementation. Necessary factual context stays in resume wording; speculative caveats and unresolved questions stay outside application copy.

Requested design variants share reviewed factual content and have actual rendered previews. A selected direction persists through local changes, such as combining its typography with another option's photo-and-identity grouping. The main editable entry and export reflect the latest selected direction; the record distinguishes that choice from details introduced by the latest rendering. User-required portraits, original image proportions, meaningful visible link text, and selectable contact details are preserved. Font and extraction checks verify the actual export rather than promising universal parsing compatibility.

The bundle is independent of the engineering model policy and contains no document-rendering runtime, upstream code, candidate-specific profile, or external-service dependency. Instructions and examples are maintained in English under the repository's standing convention; generated resumes follow the requested language and destination.

## Alternatives considered

- **Adopt a public resume skill unchanged:** the inspected skills include useful tailoring and truthfulness rules, but also fixed reports, candidate-input prerequisites, format defaults, or confirmation flows that do not fit this request. Original instructions retain only the applicable mechanisms.
- **Require quantified outcomes before drafting:** blocks useful work and encourages numerical decoration. A targeted question is appropriate when a meaningful claim depends on it; otherwise a concrete capability or observed outcome is sufficient.
- **Use one strict project template:** equal bullet quotas, full-stack lists, and full STAR narratives compete with evidence selection and readability. The skill provides adjustable defaults and distinguishes featured from secondary work.
- **Bundle an HTML or Word generator:** the requested reusable asset concerns writing and presentation rules. Available host tools can produce requested formats without imposing a renderer or template selection on content edits.
- **Put the research in every invocation:** source comparisons and access limitations matter for maintenance, while routine work needs a short entrypoint and selectively loaded references.
- **Polish the overall story before examining each project:** efficient for a superficial pass, but can hide distinctive mechanisms in secondary entries and collapse unrelated work into generic labels. Source coverage precedes compression, with proportional detail in the resulting resume.
- **Remove all numerical results until complete measurement records are available:** loses useful user-supplied evidence and couples independent claims. The skill clarifies material ambiguities individually, retains supported results, and keeps measurement notes outside application copy.
- **Use the same photo, font, and visual workflow for every application:** turns one editing session's preferences into universal requirements. Rich visual exploration is conditional on the request; accepted choices guide subsequent local refinements.

## Consequences

Distribute the complete [skill directory](../../../../../../skills/resume-writing/) to retain referenced guidance and UI metadata. No plugin runtime or installed host configuration changes. The existing English-resource tests cover the bundle; [manual behavioral scenarios](../../../../../../tests/skills/resume-writing-scenarios.md) cover missing metrics, source evidence, team ownership, arithmetic, technical depth, global prioritization, factual qualifiers, nontechnical work, complete entry coverage, selective measurement questions, evidence-preserving consolidation, rendered design comparisons, and local refinement of a selected style. They define future model evaluations rather than claiming a measured model or hiring improvement.
