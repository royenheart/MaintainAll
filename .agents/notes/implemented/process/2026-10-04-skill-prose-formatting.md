# Agent Note: Skill prose formatting

Status: implemented — repository skill prose uses natural paragraphs without per-line length limits or fixed-width wrapping.

## Problem

Skill instructions and supporting references contain manual fixed-width prose wrapping, which introduces many source newlines without reflecting meaningful structure. The user requests the same natural-paragraph convention across repository-owned skills.

## Decision

The standing rule in [AGENTS.md](../../../../AGENTS.md) and the authoring guidance in [Writing Skills](../../../../skills/writing-skills/SKILL.md) specify no per-line word, character, or column limit. Paragraphs and list-item text stay together; headings, paragraph boundaries, list items, tables, and code/template structure retain meaningful line breaks.

The convention covers [development and creative skills](../../../../skills/), [operations skills](../../../skills/), and the repository-owned [desktop-control skill](../../../../deploy/compute-use/skills/cua-desktop-control/SKILL.md). Third-party checkouts and user-global skill installations are outside this repository formatting change. License and notice files retain their exact copied contents.

Plain-language paragraphs inside reviewer/implementer prompt examples follow the same convention, while commands and prompt structure remain separate. Reflowed imported art references retain upstream hashes; the [source lock](../../../../skills/art-creation/upstream-lock.json) records their current hashes and modified status, and the [source inventory](../../../../skills/art-creation/references/upstream-sources.md) explains formatting changes.

## Alternatives considered

- **A larger fixed column limit:** would still force arbitrary breaks and contradict the requested convention.
- **One sentence per source line:** would continue introducing breaks inside natural paragraphs. Separate lines correspond to semantic structure instead.
- **Flatten every newline:** would damage YAML metadata, list nesting, tables, code, commands, and deliberately structured output examples. Reflow targets prose paragraphs and preserves those structures.

## Consequences

Existing instruction content, frontmatter, links, runtime resources, and behavior remain intact. Skill source lines can be long; editors can use visual wrapping without adding source newlines. Validation compares Markdown structure and text before/after reflow, preserves code and command content, checks idempotence, and verifies skill metadata, resource links, and updated source hashes. This formatting change does not claim improved model behavior or require renderer execution.
