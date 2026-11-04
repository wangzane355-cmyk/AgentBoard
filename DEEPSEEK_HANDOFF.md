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
- Project chat checks protected files before and after each reply even without a source snapshot. External game autosaves can therefore stop a reply before it is displayed. This means content changed during that reply, not that a stale chat baseline or file corruption has been established. Keep the guard; suggest free discussion or retrying after save writes stop rather than excluding protected saves.
- Preserve quota protection, explicit routing, reply limits and cancellation.
- Never publish `data/`, executor credentials or diagnostic logs.
- Use public examples and clearly labeled sample screenshots in documentation.
- Prefer small changes and suitable reusable components when they reduce total maintenance work.
- Run relevant offline checks. Live smoke scripts consume model usage and are separate.
- Update CHANGELOG.md and affected user documentation.
- Check for active jobs before restarting a user's server.

## Group chat protocol
Assistant bubble colors are presentation only: `chatBubblePalettes` assigns `data-chat-palette` on assistant articles; `static/chat-colors.css` loads after mobile/theme styles. Keep Codex blue and DeepSeek purple, and retain textual sender labels. Custom IDs receive deterministic, collision-avoiding choices within a bounded room; histories with more than six distinct agents may reuse colors. Do not change routing or persist credentials for a color preference.

Create rooms with `mode: "group"`, send to `agent: "all"`, or use directed slash commands.
Ordinary group/all sends pass the visible `discussion_rounds` selector (1–3). Python schedules every invited member once per round, independent of optional model handoff markers. The batch remains capped at six replies and 25 minutes total. `/all` explicitly requests one reply per member; slash-directed and selected-member sends always invoke only that member once. A room with one member also replies only once.
Only a complete round whose members all emit a standalone final `AGENTBOARD_TO: DONE` may end a discussion early; absent/inline markers are not votes. The UI says the members indicated they can end, not that their conclusions were independently verified. Preserve quota, stop, failure and integrity checks; a quota skip must not cause one remaining agent to talk to itself.
Batch metadata includes `requested_rounds`, `round`, `completed_rounds`, `skipped_agents`, `end_reason` and `finish_detail`; older records without these fields remain readable. Reasons distinguish `agents_done`, `round_limit`, `reply_limit`, `quota_limited`, `broadcast_complete`, `directed_complete`, `stopped`, `deadline` and `reply_failed`.
The round-count fix is included in the 2026-11-04 GitHub source update. The working tree passed 250 Python offline tests on Windows. Two simulator members produced four replies at two rounds and six at three rounds through the actual UI; a directed simulator message produced one. The 390px composer kept round selection and results visible. No real model was used for this verification. Keep its private evidence under the ignored runtime data directory.
Never expand a directed message into unsolicited calls to other agents.

## Chat scope and project links — locally implemented and verified

This source update passed 178 offline tests locally on Windows. Desktop and 390px UI checks covered task/project deletion and restoration, free discussion using a clearly labeled local simulator, scope drafts, project creation/linking, deleted-scope fallback and English labels. No real model was invoked for those UI checks. An idle-only service restart preserved existing project and task records. Keep detailed run evidence private under data/.

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

## Optional phone gateway — 2026-11-04 source update

The cross-platform compatibility follow-up sets address reuse before binding on POSIX so saved listeners can restart while earlier connections are in TIME_WAIT. Windows retains exclusive socket ownership and does not enable address reuse. Keep the configured bind address and active-port collision protection unchanged. Managed-project tests resolve both the returned path and expected root before containment checks, so Windows temporary-directory aliases do not weaken the scope assertion. Two new offline regressions cover platform socket policy and an active listener retaining its port. After these fixes, the full 252-test Python suite passed locally on Windows; 51 JavaScript regressions and JavaScript syntax checks had already passed. Local tests do not establish remote matrix results; see the repository [Checks](https://github.com/wangzane355-cmyk/AgentBoard/actions) for cross-platform verification.

The 2026-11-04 source update adds `static/mobile-workspace.js` and `static/mobile-workspace.css` after the existing phone/chat assets. At widths up to 760px, it presents Chats, Projects, Tasks and Me as separate pages, reusing existing conversation, project, task and delivery actions. `openSavedChat(id)` in `chat.js` shares the existing history-selection flow so opening a saved conversation preserves drafts rather than starting a fresh discussion. Chat's mobile settings are grouped into context, members, history and consensus/tasks. Keep desktop-only operations hidden on paired clients and keep navigation free of executor side effects. Project creation enters its new detail page. Browser Back must honor cancellable dialog events, including busy project forms, and return through chat settings before closing the conversation.

Local browser verification used artificial sample data without real model calls: 390×844, 360×640, 390×420 and 760×700 had no horizontal overflow, while 768px and 1440px restored desktop layout. Verified saved-history continuation, two-level chat settings and browser Back, drafts, phone/desktop input restoration, project creation/detail/back, project-task return, task drawer/delivery detail/forms, light/dark themes and Chinese/English. An unchanged list restored scroll from 336.8 to 336.8 after tab switching. The simulated remote sign-out entry was inspected, not activated. Existing 51 JavaScript offline regressions, three relevant syntax checks and diff checks passed; the existing regressions do not specifically cover the new navigation. That browser verification did not restart the live service. Source synchronization is recorded separately from a formal GitHub Release or tag. Android device experience remains for user review; the earlier pairing validation below is separate evidence.

The local phone conversation layout now uses `static/chat-mobile.css` and `static/chat-mobile.js`, loaded last after the existing chat/phone assets. At widths up to 760px it fills the visual viewport, retains a single message scroll container, and toggles the existing scope/sidebar controls as a separate settings page. Do not duplicate/reparent their IDs or reset the conversation when toggling settings. Preserve drafts, positive message scroll positions, keyboard-safe composer sizing and desktop restoration. `agentboard:chat-layout` updates the mobile chrome after existing chat controls refresh. This UI follow-up used only isolated simulator data; real Android soft-keyboard validation is still pending and is distinct from the earlier verified phone pairing.

Phone access is included in the 2026-11-04 source update. Its initial verification passed 230 Python offline tests and 14 login JavaScript regressions locally on Windows; the later combined working tree passed 250 Python tests and 51 JavaScript regressions. A 390px browser trial exercised actual pairing, a local-simulator chat, managed project creation, persistent login and revocation redirect. Firewall rules were mocked in isolated UI QA. Real Windows authorization was then verified after explicit user approval, including the narrow program/port/subnet scope and unchanged global firewall settings; Android Chrome pairing and entry into the real workspace have been confirmed by the user. A simulated viewport is not a real phone-network test.

- Keep the primary listener on loopback (normally 127.0.0.1:8765). Desktop **Settings → Phone access** explicitly enables a second listener on a selected private IP, normally port 8767. Do not silently bind the main service to 0.0.0.0 or expose all interfaces.
- Pair a same-Wi-Fi phone through an eight-digit, single-use code with a five-minute lifetime. Device sessions persist for up to 30 days. Support desktop per-device revocation; disabling the gateway revokes all device sessions immediately. Private codes, sessions, addresses and runtime paths must not enter public docs, test output or screenshots.
- Phone access uses HTTP. Pairing is access control, not encryption or a multi-user permission model. Support trusted Wi-Fi only; never configure public hosting, router port forwarding or an unrestricted reverse proxy as a shortcut.
- Paired phones can use discussion, select existing projects and create projects with computer-managed folders. Desktop-only system restart, executor configuration and native path selection are not mobile operations. Preserve existing source, scope, quota and integration checks for supported task actions.
- Keep the computer awake and the service running. Closing the phone page does not stop tasks or revoke the session. Recovery still requires restarting the desktop service after a computer restart; no OS boot service is installed.
- Inspect Windows firewall requirements read-only before proposing an exception. Authorize only the intended Python executable, TCP listener port and local subnet on the appropriate network profile; never disable the global firewall or open every program/network. A one-time user authorization may be necessary and must be reported according to the actual machine. Shared Wi-Fi client isolation may require a private router or a separately designed private network, not a public port.

Use public placeholders such as 192.168.1.20 and a generic project-directory label. Keep real local network diagnostics in private handoff/runtime records.

## Autonomous mission API

- POST `/api/missions` with normal task fields plus `policy.checks`, limits and explicit boolean `start`. Omitted start creates a paused draft.
- GET `/api/missions/<id>` returns public mission evidence and events. POST `/pause`, `/resume` or `/stop` under that path controls it.
- GET `/api/projects/<id>/verification` suggests or reads a recipe; POST saves a validated project recipe.
- GET `/api/health` reports service identity. POST `/api/system/doctor` runs read-only diagnostics. Restart/shutdown reject active jobs or chats.
- Never edit running state or SQLite outside the service. Never recompute delivered workspace baselines on recovery.
- Update local development logs and handoffs at every implementation step. Private live evidence belongs in ignored runtime data; public images use labeled demo samples.


Restoring a project rejects a source-directory conflict with another live project. A task may retain its historical discussion link after that discussion moves projects; editing that task is allowed, while execution excludes the moved discussion and new cross-project links are rejected.

Phone-login follow-up: pair success must be followed by a fresh `/phone/client` response with status 200 and `remote === true` before navigation. A consumed code is cleared, and failed cookie confirmation stays on the form with a clear remedy. `status.handshake_checks` is desktop-only, memory-only and capped at 20 outcomes; never add raw codes, tokens, hashes, IPs, UA or query values. The verified real Chrome chain was pair issued → authenticated client → authenticated home/state requests. This does not establish why the earlier vendor browser failed.
