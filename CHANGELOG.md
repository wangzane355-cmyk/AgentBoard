# Changelog


## 0.4.0 — 2026-11-03 (source update)

- Validate chat scopes and recoverable cleanup with 176 offline tests on Windows, plus desktop/390px UI checks using a local simulator. An idle-only service restart preserved existing project and task records.

- Add project-free discussion with Codex selected, a permanent chat scope selector and draft preservation across scope/conversation switches. Scope navigation does not silently move an existing conversation.
- Add explicit idle-conversation project linking and project creation inside chat, including opt-in folder creation. Preserve history, clear the earlier task link and invalidate stale consensus/context when moving discussions. Background replies continue when viewing another scope.
- Add recoverable task/project deletion, recycle-bin restoration and a short undo action. Project deletion hides its associated visible work without deleting source folders, historical results or integrated changes. Active work/dependencies block deletion; restoration does not start tasks.

- Harden desktop startup with a cross-process startup lock, detached background process, actual health/page readiness, bounded slow-start waiting, visible progress/errors and fixed interpreter/working-directory selection.

- Add a plain-language Chinese beginner guide with an isolated first-task exercise, copyable verification fields, delivery acceptance and troubleshooting.

- Add a durable SQLite-backed Codex delivery supervisor: plan, build, immutable verification, independent review and bounded repair.
- Add per-phase checkpoints, exact process identity, pause/resume/stop, restart recovery, leader ownership, time/round/stall and no-progress limits. Default to one autonomous worker; opt in to two.
- Add Python/Node test recipes, controlled test commands, installed-browser desktop/mobile captures, zero-test rejection and fixed acceptance file hashes.
- Add goal-first bilingual delivery workspace, reports, evidence gallery, mobile navigation and a resizable right-side conversation workspace. Preserve the original board, executor settings and explicit integration/rollback.
- Add read-only connection diagnostics, idle-only backend restart and public-source packaging with SHA256 manifests.
- Validate offline lifecycle/integrity/process checks and separate live Codex trials. Tests do not assert that model claims establish product correctness. See docs/AUTONOMY.md for operational boundaries.

## Unreleased — 2026-11-03

- Support real Codex quota windows for weekly-only accounts, preserving the 15% cutoff, freshness checks, account restrictions and read-failure protection. Weekly capacity is no longer mistaken for an unavailable five-hour reading.
- Display the limiting quota window in both interface languages. Retain the five-hour field only when the account actually supplies it.
- Add offline parser and task/chat guard coverage, plus a dated research and autonomy roadmap. The research roadmap records the pre-0.4 baseline; the 0.4 entry and autonomy guide describe the implemented loop.

## 0.3.1 — 2026-10-29

- Consolidated the sidebar chat buttons into one Agent chat entry. Single/group mode, room membership, recipients and discussion controls remain available inside the shared chat interface.

- Added local Codex model and reasoning preferences, with capability-filtered choices from the installed client's model cache. Defaults remain inherited until explicitly changed; global Codex configuration is untouched.
- Added per-task overrides and invocation snapshots. Quota fallback drops Codex-only parameters, and preference edits are blocked during active Codex tasks or room batches.
- Task capsules, run details and chat replies distinguish requested settings from model/effort confirmed by the CLI startup log. Old records remain compatible.
- Added offline selection, persistence, capability, command, evidence and concurrency checks. No live model was invoked during validation. See docs/MODEL_SETTINGS.md.

## 0.3.0 — 2026-10-29

- Added managed DeepSeek runtime slots with a fixed local Node runtime, startup checks, explicit preparation/activation and manual rollback. Existing desktop applications and credentials remain separate.
- Preparing a new version preserves the selected version; failed checks never switch the pointer. Updates use exact official npm versions with lifecycle scripts disabled. Checks never call a model.

## 0.2.3 — 2026-10-29

- Fixed group chats waiting in an npx package-resolution step before DeepSeek had actually started. Discover installed executors and cached entries directly; no automatic downloads during conversations or tasks.
- Availability checks now require an installed DeepSeek entry rather than merely finding npx. An explicit entry override is supported.
- Chat status distinguishes executor preparation from waiting for a reply and displays elapsed time. Existing time, scope and quota limits remain unchanged.

## 0.2.2 — 2026-10-29

- Refreshed the bilingual release overview with current demo screenshots, agent-adapter documentation and an optional three-theme gallery; corrected English room-status labels and singular reply/round wording.

- Fixed empty HTTP responses from Windows desktop shortcuts using pythonw.exe without console streams. Windowless launcher diagnostics are saved locally, and reopening checks page readiness rather than only an occupied port.

## 0.2.1 — 2026-10-29

- Added local appearance preferences under Settings: Graphite, Construct and Obsidian, with original previews, instant switching and restore-default support. No executor or project behavior changes.

## 0.2.0 — 2026-10-29

- Agent management for local simulators, stdin/stdout command-line adapters and compatible non-streaming Chat Completions endpoints.
- Configurable chat recipients, room membership and slash commands; existing Codex/DeepSeek behavior retained. Discussions remain capped at six replies.
- API keys referenced through environment variable names, never stored as values. Configuration checks do not call models or claim live authentication success.
- Simulators work without accounts, keep saved simulation labels and cannot implement changes. API adapters support discussion and read-only investigation only.
- Existing Python scope checks apply to CLI adapters; running agent configurations cannot be edited. Live third-party provider/account behavior remains unverified.
- AgentBoard runtime data and worker roots are excluded from project copies and source hashes, including when developing AgentBoard itself. Both paths are normalized to handle Windows temporary-folder aliases.
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

