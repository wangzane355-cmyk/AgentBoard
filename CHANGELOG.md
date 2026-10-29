# Changelog

## 0.2.0 — 2026-10-29

- Agent management for local simulators, stdin/stdout command-line adapters and compatible non-streaming Chat Completions endpoints.
- Configurable chat recipients, room membership and slash commands; existing Codex/DeepSeek behavior retained. Discussions remain capped at six replies.
- API keys referenced through environment variable names, never stored as values. Configuration checks do not call models or claim live authentication success.
- Simulators work without accounts, keep saved simulation labels and cannot implement changes. API adapters support discussion and read-only investigation only.
- Existing Python scope checks apply to CLI adapters; running agent configurations cannot be edited. Live third-party provider/account behavior remains unverified.
- AgentBoard runtime data and worker roots are excluded from project copies and source hashes, including when developing AgentBoard itself.
- Offline adapter tests use local subprocesses and a loopback fake provider, including directed routing, persisted simulation records, capability checks and credential/error redaction.

## 0.1.1 — 2026-10-28

- Chinese / English interface switch in the page header and modal dialogs, with browser-local preference persistence.
- Local translation catalog for controls, forms, task states and conversation status; no translation API or model calls.
- Switching languages preserves open forms, user drafts, task names, project paths and conversation text. Reference bodies, delivery output and diagnostic logs keep their original language.
- Automatically generated planning and consensus requests follow the selected interface language.

## 0.1.0 — 2026-10-28

First public source release.

### Workspace
- Local task board with Codex and DeepSeek executors, explicit scope and time limits.
- Empty first-run state; no personal projects or machine-specific project paths.
- Read-only sample workspace via `python demo.py`, without credentials or model calls.
- Large conversation workspace: controls and history on the left, messages and composer on the right.

### Planning and collaboration
- Project references refreshed before each turn, with source manifests and bounded text snapshots.
- Task-aware planning, saved consensus and discussion-to-task handoffs.
- Shared agent rooms with broadcast, strict directed commands and bounded peer handoffs.
- Default 25-minute task limit and chat-batch deadline; maximum six replies per discussion.

### Review
- Python evidence for file scope, protected files, source drift and configured checks.
- Text diffs, task capsules, explicit integration and hash-guarded rollback.
- Five-hour Codex quota checks with a 15% remaining threshold.

### Distribution
- MIT license, bilingual documentation, contributor guidance and CI configuration.
- Private runtime state, conversations, logs, snapshots and credentials excluded from Git.
- Unity editor version read from the project; DeepSeek profile name configurable.
- Offline test scheduling mocks stay local to the board, preserving Windows subprocess pipe readers; sample child processes use UTF-8.

### Known limitations
- Early release, primarily manually verified on Windows.
- No token streaming, public hosting authentication or automatic history summarization.
- CLI authentication and OS sandbox behavior remain external dependencies.
- Source copies and file checks are not a replacement for OS isolation.

