# Codex `--json` metrics

`codex exec --json` writes JSONL events. The useful records are:

- `turn.completed.usage`: `input_tokens`, `cached_input_tokens`,
  `cache_write_input_tokens`, `output_tokens`, `reasoning_output_tokens`;
- `item.completed.item.type`: `agent_message`, `command_execution`, `file_change`,
  `mcp_tool_call`, `error`.

The Codex trial runner writes the JSONL to `codex-events.jsonl`; the last message is
also written with `-o`. Cache hit rate uses cached input over input+cached. Codex
events do not expose the same compaction/summary structure as dsh; report absence as
"not exposed", not zero.

Do not claim that a skill was opened from catalog presence alone; inspect item/tool
evidence or the activation audit.
