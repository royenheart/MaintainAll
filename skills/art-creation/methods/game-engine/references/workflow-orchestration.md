# Enforced Creative Workflow

Use this when moving the human/agent loop into an application. The skill supplies creative methods; application code owns durable state and allowed transitions.

A useful state model is `brief → experiment → playable build → awaiting feedback → revise or accept → representative slice → delivery`. Each transition names the evidence it needs. User decisions carry the build ID, question version and current workflow revision so answers to an older preview can be recognized and reconciled. The runtime owns accepted decisions; workers receive the task and its relevant evidence.

| Responsibility | Runtime mechanism |
|---|---|
| Route the next experiment | Explicit state transition and prerequisite checks |
| Establish feedback readiness | Reusable authoring/viewing route, small test artifact, observed conditions and response channel |
| Construct or inspect an artifact | Bounded worker task with native project input and immutable output identity |
| Wait for a user | Persisted pending questions and build-linked response event |
| Retain accepted choices | Structured decision records and dependency checks |
| Recover interrupted work | Durable execution history, attempt identity and idempotent output adoption |
| Explain progress | Stage status, actual artifacts, observations and current question |

[Temporal](https://docs.temporal.io/workflows) fits long-running build/review work with durable waits and worker recovery. Put model calls, engine processes and file I/O in Activities. Workflow code makes deterministic decisions over recorded results. Use [Queries for reads, Signals for asynchronous feedback, or Updates for validated responses](https://docs.temporal.io/encyclopedia/workflow-message-passing). Activity retries can repeat external work; give each build/attempt an identity and define retry/cancellation behavior around the actual side effects. Store large artifacts outside event history and reference their hashes.

[LangGraph interrupts and checkpoints](https://docs.langchain.com/oss/python/langgraph/interrupts) are a smaller starting point when most work is a conversational graph. [XState persistence](https://stately.ai/docs/persistence) suits an explicit interactive state model; persistence and worker execution still need application-level integration. Choose one authoritative workflow state, with agent loops inside bounded tasks if needed.

The runtime controls task dispatch, output adoption, and delivery transitions. Models propose the next action; the application validates it against current state and evidence. The existing skill and Godot helper supply the creative methods and engine operations for these tasks.
