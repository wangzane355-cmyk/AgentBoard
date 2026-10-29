# Adding agents

Open **Manage agents / Agent 管理** in the sidebar. Codex and DeepSeek retain their existing adapters and Codex quota guard. No new account is required to try the local simulator.

## Local simulator

Choose **Local simulator**, enter a stable ID such as `local-helper`, give it a display name and save. The simulator consumes no model usage and changes no files. Its replies and task runs are labeled `SIMULATION`, including in saved history. It validates scheduling and handoffs, not AI reasoning or implementation quality.

Create a read-only investigation task for it, or select it as a chat recipient. For a group rehearsal, select only simulator members before sending; unchecked agents are not invited. Address one member with `/local-helper Your question`. Rooms contain at most six members and discussions produce at most six replies.

## Command-line adapter

Install and authenticate the executor separately. Configure an executable as an absolute path or a command on PATH. Arguments are a JSON array, for example:

```json
["--headless", "--plain-text", "-"]
```

This is an illustrative contract, not a command guaranteed to work with every CLI. The program must accept the prompt on standard input and write its final plain text reply to standard output. JSON event streams require a wrapper that extracts the final reply. `{workspace}` and `{answer_file}` placeholders can be used in arguments; AgentBoard collects standard output for custom agents. Do not place credentials in arguments.

The working directory is an isolated project copy. Implementation is disabled by default; enable it only for a tool that can follow the task's scope. It must end a successful task answer with `AGENTBOARD_STATUS: DONE`. AgentBoard still checks file scope, protected paths, source drift, exit status and configured acceptance rules. A CLI's own permissions determine whether it can access other parts of the computer; this adapter does not create an OS sandbox.

## Compatible API adapter

Supply a full endpoint ending in `/chat/completions`, a model name and the **name** of an environment variable containing your key. The key value is never entered in the board, stored in its configuration, or returned by its settings API. Set it in the environment used to launch AgentBoard; restart the idle service if you changed that environment.

The bridge sends a non-streaming Chat Completions-style request with `model` and `messages`, and expects text in `choices[0].message.content`. HTTPS is required except for loopback services. Redirects are rejected. Provider error bodies and credentials are omitted from bridge diagnostics.

API adapters support discussion and read-only investigation only. They cannot execute tools or implement changes. Sending a message or starting a task transmits included project context to the configured provider and may incur charges; saving settings or checking configuration does neither.

## What a configuration check means

**Check configuration** only checks executable presence or whether the named environment variable exists. It does not verify login, connectivity, model permissions, billing or provider compatibility. This release was checked with a loopback fake provider and local subprocess fixtures; live third-party accounts have not been validated.

Settings are stored in ignored `data/agents.json`. You can edit or disable custom agents when they are idle. An agent cannot be reconfigured while it is used by a running task or room. Historical records retain IDs; disabled agents cannot start new calls. Existing rooms keep their membership; create a new room to choose a different set.
