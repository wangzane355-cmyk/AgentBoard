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
5. Default to DeepSeek, 25 minutes and `auto_start: false` unless the user requests otherwise.
6. Read back the state and report the IDs that actually changed.

Preparing cards does not authorize starting jobs or integrating code. Follow the user's current scope. Do not fabricate completed runs for historical work.

Projects accept `context_files` (absolute local file/folder paths) and `context_urls`. Task references supplement project references. A `discussion_id` links the consensus and recent conversation. Changing a room's task marks prior consensus for review.

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

