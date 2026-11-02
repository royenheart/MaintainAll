# DSH session event schema (observed)

A `result.json` from the SDK carries `events` with `type`, `seq`, `time`, and `data`.
Common types:

- `turn/start`, `step/start`, `step/end`, `turn/end`;
- `assistant/message` — model content and `usage`
  (`inputTokens`, `outputTokens`, `cacheReadTokens`, `cacheWriteTokens`,
  `totalTokens`);
- `tool/call` — `callId`, `name`, `arguments` (JSON string);
- `tool/result` — `toolCallId`, `message.content[]`, `message.isError`;
- `request/context` — `provider`, `model`, `contextWindow`;
- `request/header` — config and tool schema;
- `system/message` — system prompt;
- `compaction/start`, `compaction/end`, `compaction/summary`, `compaction/prune`;
- `job/registered`, `job/settled` — shell jobs.

Raw session logs are zstd-compressed JSONL; `session_events.py` decompresses without
printing content. Never paste prompts, tool outputs, credentials, or `.npmrc` into a
report.
