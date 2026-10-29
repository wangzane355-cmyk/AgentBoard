# Changelog

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

### Known limitations
- Early release, primarily manually verified on Windows.
- No token streaming, public hosting authentication or automatic history summarization.
- CLI authentication and OS sandbox behavior remain external dependencies.
- Source copies and file checks are not a replacement for OS isolation.

