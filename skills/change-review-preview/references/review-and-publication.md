# Review and publication

## Explain the complete change

Start with the trigger, actual behavior and expectation. A PR explains mechanism and resulting behavior; an Issue describes the observed problem. Follow current repository templates. An efficiency enhancement does not become a missing-data bug because the form accepts only bugs: use the appropriate PR/discussion route or the real performance symptom.

Analyze dimensions the patch changes: correctness, performance, resources/lifecycle, snapshots/cache/timeouts/retries, UX/accessibility, refactoring, interfaces, wire/persistence, security and tests. This is analysis, not a requirement to list every category. Supporting refactoring need not be the main delivery type.

State actual changes: shared pending work shares a snapshot/deadline; removing a request can remove incidental cache population; virtualization changes DOM and keyboard/scroll ownership. Distinguish a narrower internal call contract from a public protocol break.

Explain historical constraints when material. Separate documented intent from inferred omission. Remove speculative warnings, unrelated unobserved failures, review diaries and repeated disclaimers. Retain conditions needed to interpret the evidence.

## Make evidence usable

Keep one authoritative draft per item and an explicit evidence list. Include revisions, scripts/helper dependencies, setup, commands/results, raw samples and cleanup needed for the claims. Reuse repository suites. A focused result does not imply every suite/platform passed.

Use original screenshots/recordings for relevant UI states and assertions for properties an image cannot show. Exercise keyboard/focus or nearby flows when affected. State tested platforms and meaningful gaps once where they belong.

Use [Performance Investigation](../../performance-investigation/SKILL.md) for measured claims. Keep controls/raw data and component/E2E scopes distinct. Functional revisions need affected evidence rather than relabeled older measurements.

Public prose follows the requested language and stands alone from private hosts, accounts, credentials and the conversation. Reproduction paths are configurable. Review the complete intended bundle, including scripts, raw captures, screenshots/metadata and archive entries, for credentials, personal identifiers and machine-specific configuration. Whitelisting a file is not a content privacy review. Redact strings without changing measured numbers, ordering or necessary source.

## Present faithfully

Render text without rewriting it in the browser. Preserve complete raw Markdown, code fences and tables. Map listed local images/attachments for preview while leaving copied public source portable. Display raw dataset text without JavaScript parse/stringify.

Show each independent item with issue/PR copy, patch, evidence/source and optional scope-labeled metrics. The helper's path/hash validation and allowlist do not establish the experiment or classify its change.

## Authorized publication

Refresh upstream duplicates, including merge state and actual changes. Verify the whole intended branch diff and untracked files. Commit/push only the selected patch with required hooks/checks. Keep reports and captures outside source commits when requested.

Choose hosting for the environment and permission scope: existing forge attachments, an approved evidence store or evidence release assets can work. Do not turn evidence hosting into a product release. Use returned upload URLs and verify anonymous download/image rendering.

Journal source commit, branch, hashes, returned IDs/URLs and completed steps. After uncertain failure, query/reconcile recorded objects or a unique head/title/content match before retrying writes. Serialize mutations and respect rate-limit responses. Do not overwrite unrelated branches/assets or automatically reopen maintainer-closed PRs.

Substitute real URLs and linked issues before final submission. Check host limits after substitution. Preserve ordinary complete source/data files with sizes/hashes in ZIPs; split at file boundaries when needed. An encoded inline archive is an optional response to a host/user constraint, not the default format for every review.

Verify remote bodies/data, heads/file sets, issue relationships, draft state, hashes and rendered images. Honor ready/draft choices. Update preview status and report upstream closures or pending checks as observed outcomes.
