# Setup guide / 首次使用

## Application

Install Python 3.10 or later. On Windows, enable **Add Python to PATH** during installation. The web app uses only the Python standard library. The optional native file picker needs Tkinter, normally included with the Windows Python installer.

```bash
python --version
python demo.py
```

The demo opens at http://127.0.0.1:8766/ and never calls an agent. For your own workspace, run `python launch.py` or double-click `start.cmd` on Windows. Use `python3` instead of `python` where required by your installation.

## Codex

Install the [official Codex CLI](https://github.com/openai/codex), following its current installation instructions. Make `codex` available on PATH.

```bash
codex login
codex login status
```

AgentBoard reuses that CLI login; it does not ask for or store your OpenAI credentials. See [official authentication guidance](https://learn.chatgpt.com/docs/auth).

The capacity guard uses `codex app-server` and the signed-in account's actual quota windows. It supports five-hour, weekly-only and multiple-window readings. It stops new Codex calls when any readable window reaches 15% remaining, on an expired reading or on a read failure. A missing five-hour value stays unavailable; it is never estimated from a weekly reading. The header names the most constrained window (`5h`, `7d`, or its duration in minutes). API-key-only authentication may not provide usable quota windows and is blocked by the guard. Do not assume API billing and subscription quotas are interchangeable.

On Windows the adapter uses the unelevated workspace sandbox compatibility options. On other platforms those Windows-only options are omitted. Live execution on non-Windows systems is not yet fully validated.

## DeepSeek

Install [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) before starting a chat. AgentBoard uses an installed `dsh`, a standard Windows user installation, or a previously installed npm-cache entry invoked directly through Node. It never runs an automatic package download during a task or conversation. If none is found, it fails immediately with setup guidance instead of waiting for npm dependency resolution. An explicit absolute CLI or JavaScript entry can be set with `AGENTBOARD_DEEPSEEK_ENTRY`.

```bash
dsh --profile headless --help
```

**Authentication is a separate setup step.** The shipped headless profile does not automatically consume the GUI's saved sign-in. Configure the credentials for your chosen Harness provider using the [official headless credentials guide](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/headless/README.md#credentials). If using saved Harness sign-in, that guide explains how to enable its stored-auth components. Keep that configuration outside this repository.

An alternative profile can be selected with `AGENTBOARD_DEEPSEEK_PROFILE`; it must accept a task on stdin and print only the final response to stdout, matching headless behavior.

The app's “available” badge detects the command, not whether a model account can successfully answer. A real test call can consume your account's quota or API balance.

## First project

1. Open http://127.0.0.1:8765/ and add an existing local project folder.
2. Add absolute paths for files or directories that must be protected, such as player saves.
3. In **Project references / 项目资料**, attach logs, handoffs and reference pages. Preview the selected text before saving.
4. Start a conversation or a group room. Save the agreed scope and turn it into a task draft.
5. For implementation, provide allowed relative paths and independent acceptance rules.
6. Start a small task; inspect the evidence before integrating its changes.

There is no preloaded personal project. Your own `data/` is created on first use and stays local.

## Web checks

Static webpage checks require Node 22+ and an installed Edge/Chrome. No npm dependencies are needed: the bundled browser probe uses Node built-in WebSocket and the browser DevTools protocol. It sets exact device metrics and verifies the measured viewport, visible text and horizontal overflow before saving a screenshot. This avoids Chromium’s minimum window-size cropping on narrow screens.

## Optional checks and environment

| Variable | Purpose | Default |
| --- | --- | --- |
| `AGENTBOARD_AUTONOMOUS_WORKERS` | Autonomous task concurrency, 1 or 2 | `1` |
| `AGENTBOARD_BROWSER_EXECUTABLE` | Optional installed Edge/Chrome executable | Auto-discover |
| `AGENTBOARD_DATA_DIR` | State, conversations and run logs | `data/` beside the app |
| `AGENTBOARD_WORKSPACES_DIR` | Isolated source copies | `~/AgentBoardWork` |
| `AGENTBOARD_DEEPSEEK_ENTRY` | Optional absolute installed CLI or JavaScript entry | Auto-discover installed executors |
| `AGENTBOARD_DEEPSEEK_PROFILE` | Harness profile compatible with headless stdin/stdout | `headless` |
| `AGENTBOARD_UNITY_EDITOR_VERSION` | Override editor version for the Unity adapter | Read `ProjectSettings/ProjectVersion.txt` |

Legacy task checks compile Python for syntax. Autonomous delivery additionally runs real unittest/Node tests and configured commands; syntax alone cannot establish delivery. See [autonomous delivery](AUTONOMY.md). The Unity adapter requires a compatible `unity` CLI and installed editor. A missing compiler is reported as an unrun check, not a successful build. Configure and validate the toolchain before relying on it for acceptance.

## Desktop startup

The desktop launcher opens a ready AgentBoard immediately, or starts one hidden background process and waits for its health endpoint and page. A cross-process startup lock protects rapid repeated clicks. Slow startup shows a small progress window and waits up to120seconds for bounded local checks. Closing the progress window cancels that opening attempt; it does not stop existing background work. Startup or browser failures show a visible message with the local URL and private log path.

The launcher uses its current Python executable and a fixed application directory. The command-file fallback prefers the installed Python launcher (`py -3`), then `python`.

## Troubleshooting

- **Command not found:** check PATH and restart the terminal/app after installing a CLI.
- **DeepSeek authentication failure:** check the headless profile, not just the GUI login.
- **Codex blocked:** inspect the quota error, account login and `codex app-server` availability.
- **Reference read failure:** correct the local path or page URL. The app will not silently substitute stale references.
- **Source changed since the task ran:** rerun the task against the current source to avoid overwriting newer edits.
- **Port already occupied:** `launch.py` opens the existing board only after its page responds normally. Make sure it is your AgentBoard service; you can run `python server.py --port 8767` separately.

Windows is the primary manually verified platform. Report your OS, Python/CLI versions and a redacted error when asking for help.
