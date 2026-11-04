# Security and privacy

AgentBoard is an early-stage workbench for a trusted user on a local computer.

## Deployment boundary

- The main service remains bound to loopback by default (normally 127.0.0.1:8765). It has no multi-user permission system or public hosting layer.
- Optional phone access requires an explicit desktop action and a second listener bound to a selected private IP (normally port 8767). It does not change the main listener to 0.0.0.0.
- Do not expose either listener through a reverse proxy, router port forwarding or a public/untrusted network.
- The app can read configured local references and copy project files. Use trusted projects and carefully review allowed paths and executor permissions.
- Source copies, file hashes and post-execution checks do not replace OS sandboxing. Agent processes inherit the runtime and credentials configured for their external CLI.

## Optional paired phone access

**Included in the 2026-11-04 GitHub source update.** The working tree has passed 250 Python offline tests and 51 JavaScript regressions; these test supported behavior, not an independent security audit. Phone checks include authentication, origin/host validation, expiry, rate limits, revocation, restart persistence and mocked firewall authorization. Android Chrome pairing and workspace entry were verified on a real device. The new mobile layout has browser verification; its touch and soft-keyboard experience still needs device review. This source update does not create a packaged release or version tag.

Use only a trusted phone on the same trusted Wi-Fi. The eight-digit pairing code is single-use and expires after five minutes. A paired-device session persists for up to 30 days. The desktop can revoke individual devices; disabling phone access immediately revokes all paired sessions. Treat a paired phone as access to the user's project, conversations and supported task controls, not as a separate limited user account.

This listener uses **HTTP**. Pairing controls access but does not encrypt traffic. A person able to observe or alter that network traffic may obtain private content or session credentials. Do not use it on public Wi-Fi or assume that pairing makes an untrusted network safe. Keep codes, session credentials and private network diagnostics out of screenshots and issues.

Desktop-only system restart, executor configuration and native path-picker operations are not exposed to paired phones. A phone may select an existing project or request a new project folder managed by the computer. These restrictions do not provide OS-level isolation for model execution.

If Windows blocks the connection, grant only the intended Python executable, TCP listener port and local subnet on the appropriate network profile. Do not disable the firewall or add an unrestricted all-program/all-network exception. Whether a one-time Windows authorization is needed depends on the machine; installation instructions must not claim it has already been granted. Shared apartment Wi-Fi may isolate clients even after a correct firewall rule. A private router, or a separately designed private-network solution, may be needed; opening a public router port is not a workaround.

Keep the computer awake and the service running. Closing a phone browser does not stop tasks or revoke its saved session; revoke the device on the computer when access is no longer wanted.

## Private material

`data/` contains project paths, messages, task prompts, logs, reference snapshots and backups. Worker copies may contain project source. Neither directory belongs in a public repository. Do not share raw diagnostics without reviewing and redacting them.

Codex and DeepSeek credentials are managed by their own tools. AgentBoard does not bundle accounts or API keys. Never put real keys in examples, screenshots or issues.

## Reporting a vulnerability

Use this repository's private vulnerability reporting option if GitHub exposes it. If unavailable, open a minimal issue requesting a private reporting channel without including credentials, private data or an exploit affecting another user's system.

There is no guaranteed response-time or supported-version SLA at this early stage. Please include the affected commit, OS, a safe reproduction and the impact you observed.

Custom executors are trusted local configuration, not sandboxed plugins. Keep `data/agents.json` private. API adapters read keys from the service environment; linked project context is sent only when a user starts a task or sends a message. Configuration checks do not contact providers. Bridge redirects are blocked, and provider error bodies are omitted from diagnostics.
