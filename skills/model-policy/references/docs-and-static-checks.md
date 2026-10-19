# Documentation ownership and static checks

Use this reference when updating documentation or adding a repeatable repository check. Adapt the mechanisms to the repository; directory names, document templates, translation policies, and numeric budgets are local choices.

## Documentation ownership

Keep one authoritative owner per fact and link to it:

| Information | Typical owner |
| --- | --- |
| Standing agent instructions | Root or subtree `AGENTS.md` |
| Public package behavior | Package README and source API comments |
| Cross-component contracts | Architecture or subsystem documentation |
| Task procedures | Contributor guides or cookbooks |
| Decisions and tradeoffs | Existing decision records, if maintained |
| Exhaustive API/configuration inventories | Source-derived generated references |
| Temporary plans and validation results | Conversation or host plan; repository files only when requested or required |

Read the local owners first. Update existing documentation with the changed contract; create a page only when the requested deliverable or repository policy calls for it. Do not create a plan/spec/report directory merely because a skill was loaded.

Write current behavior, prerequisites, observable success, failures, and recovery. Keep durable rationale with its decision owner and temporary progress outside standing instructions. Use relative Markdown links with valid anchors. Keep prose paragraphs on natural lines without fixed-width wrapping. Update translations or website projections only when the repository maintains them. Prefer generating catalogs to copying them; source-equivalence checks can protect declarations that must be pasted verbatim.

## Static check design

1. Inspect package scripts and CI. Reuse existing commands and make local and CI entry points call the same checks. Keep command inventories in executable configuration, with prose linking to that owner.
2. Define the invariant, authoritative input corpus, exclusions, and actionable failure output before implementation. Use a parser for syntax-dependent rules; a deliberately limited text check must state its detection boundary.
3. Discover files from maintained ownership or manifests; normalize repository-relative paths. Reject unexpectedly empty or narrowed discovery where it could falsely pass. Test admitted, rejected, and excluded forms, including missing inputs. A rule that requires judgment stays in review.
4. Keep verification read-only where practical. Separate generation/fix commands from freshness checks; generate comparisons in external temporary storage or configured output directories without silently rewriting tracked files. Run artifact-producing builds/tests only as needed, using existing output conventions; clean task-owned scratch and report any intentional generated deliverables. Declare generated-contract and artifact prerequisites explicitly.
5. Start with plain scripts. Add dependency scheduling only when needed: validate unique IDs, known dependencies, and acyclicity; bound concurrency; serialize writers sharing an output. Skip consumers of failed prerequisites, continue independent checks, and fail the aggregate for required failures or skips. Keep optional failures visible.
6. Report command, scope, file/line diagnostics, exit status, and relevant logs. Tests own their temporary files, ports, and processes. Cover discovery boundaries and dependency/failure behavior when introducing those mechanisms.

Useful checks include broken links/anchors, generated-reference freshness, documented/source type agreement, compilable examples, manifest coverage, and forbidden cross-layer imports. Use budgets only where locally justified; relocate or condense duplicated prose before raising a ceiling.

Run focused checks after edits and required aggregate checks before delivery. A quick documentation check may omit builds; say what remains unverified. Do not treat static success as proof of runtime behavior, usability, or model quality.
