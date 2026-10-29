# Security and privacy

AgentBoard is an early-stage workbench for a trusted user on a local computer.

## Deployment boundary

- The service binds to loopback. It has no multi-user authentication or public hosting layer.
- Do not expose the port through a reverse proxy, port forwarding or an untrusted shared host.
- The app can read configured local references and copy project files. Use trusted projects and carefully review allowed paths and executor permissions.
- Source copies, file hashes and post-execution checks do not replace OS sandboxing. Agent processes inherit the runtime and credentials configured for their external CLI.

## Private material

`data/` contains project paths, messages, task prompts, logs, reference snapshots and backups. Worker copies may contain project source. Neither directory belongs in a public repository. Do not share raw diagnostics without reviewing and redacting them.

Codex and DeepSeek credentials are managed by their own tools. AgentBoard does not bundle accounts or API keys. Never put real keys in examples, screenshots or issues.

## Reporting a vulnerability

Use this repository's private vulnerability reporting option if GitHub exposes it. If unavailable, open a minimal issue requesting a private reporting channel without including credentials, private data or an exploit affecting another user's system.

There is no guaranteed response-time or supported-version SLA at this early stage. Please include the affected commit, OS, a safe reproduction and the impact you observed.

Custom executors are trusted local configuration, not sandboxed plugins. Keep `data/agents.json` private. API adapters read keys from the service environment; linked project context is sent only when a user starts a task or sends a message. Configuration checks do not contact providers. Bridge redirects are blocked, and provider error bodies are omitted from diagnostics.
