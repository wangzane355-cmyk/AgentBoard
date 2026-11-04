# Agent handoff guide

This guide applies to Codex, DeepSeek and human contributors working on AgentBoard.

## Read first
- README.md: user-visible behavior and limitations.
- CHANGELOG.md: current capabilities.
- docs/SETUP.md: external executors and authentication.
- CONTRIBUTING.md: development and verification.

## Updating task cards
Use the local HTTP API while the app is running. Do not edit `data/state.json` behind the running server.

1. GET `/api/state` to obtain current project/task IDs.
2. Match existing cards before adding a new one.
3. POST `/api/tasks` to create, or `/api/tasks/<id>/update` to update a non-running task.
4. Provide a concrete goal, allowed paths, dependencies and acceptance criteria.
5. Follow the user's executor preference. Codex autonomous delivery is available via `/api/missions`; ordinary cards retain their existing executor options. Keep drafts unstarted unless execution is authorized.
6. Read back the state and report the IDs that actually changed.

Preparing cards does not authorize starting jobs or integrating code. Follow the user's current scope. Do not fabricate completed runs for historical work.

Projects accept `context_files` (absolute local file/folder paths) and `context_urls`. Task references supplement project references. A `discussion_id` links the consensus and recent conversation. Changing a room's task marks prior consensus for review.

## Current supervision boundaries

Codex quota checks use the account's real available windows. Weekly-only accounts are supported; never copy weekly capacity into the five-hour field. The cutoff, stale-reading checks and account restrictions apply to both tasks and chats.

Codex autonomous missions now use a durable plan/build/check/review/repair loop with bounded rounds and time, checkpoint recovery, separate reviewer snapshots and immutable final workspace hashes. Ordinary legacy tasks remain single-attempt. Read `docs/AUTONOMY.md` and `docs/ARCHITECTURE.md` before changing either workflow. No queued card or single success establishes unlimited unattended execution. The dated research document describes the earlier baseline and cited design sources.

## Modifying the application
Work from the repository root. Avoid concurrent edits to the same files.
- Preserve private state and backward-compatible reads of existing records.
- Preserve source-copy checks, protected-file hashes and integration/rollback checks.
- Preserve quota protection, explicit routing, reply limits and cancellation.
- Never publish `data/`, executor credentials or diagnostic logs.
- Use public examples and clearly labeled sample screenshots in documentation.
- Prefer small changes and suitable reusable components when they reduce total maintenance work.
- Run relevant offline checks. Live smoke scripts consume model usage and are separate.
- Update CHANGELOG.md and affected user documentation.
- Check for active jobs before restarting a user's server.

## Group chat protocol
Create rooms with `mode: "group"`, send to `agent: "all"`, or use directed slash commands.
Only explicit bounded discussions may schedule peer handoffs. Python validates the target, remaining replies, time and stop state.
Never expand a directed message into unsolicited calls to other agents.

## Chat scope and project links — locally implemented and verified

This source update passed 176 offline tests locally on Windows. Desktop and 390px UI checks covered task/project deletion and restoration, free discussion using a clearly labeled local simulator, scope drafts, project creation/linking, deleted-scope fallback and English labels. No real model was invoked for those UI checks. An idle-only service restart preserved existing project and task records. Keep detailed run evidence private under data/.

- The sidebar Agent chat entry opens free discussion with Codex selected. POST `/api/chats` accepts `project_id: null`; free discussion has no project references, source snapshot or task creation. The main planning entry and task discussion entry retain their project/task context.
- The permanent chat scope selector opens that scope's history and a new conversation, preserving unsent drafts when switching within the page. It does not reassign an existing conversation or stop a background reply.
- POST `/api/chats/<id>/project` with `project_id` as a valid project ID or null explicitly moves an idle conversation. Preserve history, clear `task_id`, and invalidate old consensus/context snapshots. Reject moving an active conversation. Task discussion handoffs must verify that the task and conversation still belong to the same project.
- Chat has its own create-project form. POST `/api/projects` accepts the explicit boolean `create_directory` for a new folder. Creating a project does not invoke a model or start a task. The “from this discussion” action links the current idle conversation after creation; retry only the link if creation succeeded but linking failed.
- Chat's task-draft button continues to use the ordinary task workflow. Use autonomous missions for the durable check/review/repair cycle.

## Recoverable workspace cleanup — locally implemented and verified

- POST `/api/tasks/<id>/delete` or `/restore`, and `/api/projects/<id>/delete` or `/restore`, move records into or out of the recycle bin. Use the running API; never edit private JSON behind it.
- `public_state` exposes visible projects/tasks/chats/missions and `trash` summaries. Project deletion hides its associated work; restoring a project returns its previously visible records. Tasks deleted separately remain in the recycle bin until separately restored.
- Local source folders, run history/results and already-integrated code changes are retained. Record deletion is not integration rollback; restoring a task does not start it.
- Active/queued work, active chat and active dependencies can block deletion. Follow the specific guard message instead of terminating unrelated processes or deleting files directly.

## Autonomous mission API

- POST `/api/missions` with normal task fields plus `policy.checks`, limits and explicit boolean `start`. Omitted start creates a paused draft.
- GET `/api/missions/<id>` returns public mission evidence and events. POST `/pause`, `/resume` or `/stop` under that path controls it.
- GET `/api/projects/<id>/verification` suggests or reads a recipe; POST saves a validated project recipe.
- GET `/api/health` reports service identity. POST `/api/system/doctor` runs read-only diagnostics. Restart/shutdown reject active jobs or chats.
- Never edit running state or SQLite outside the service. Never recompute delivered workspace baselines on recovery.
- Update local development logs and handoffs at every implementation step. Private live evidence belongs in ignored runtime data; public images use labeled demo samples.


Restoring a project rejects a source-directory conflict with another live project. A task may retain its historical discussion link after that discussion moves projects; editing that task is allowed, while execution excludes the moved discussion and new cross-project links are rejected.
