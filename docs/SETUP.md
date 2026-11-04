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

## Android phone / 安卓手机（同一 Wi-Fi）

**已包含在 2026-11-04 本次源码更新中；安卓 Chrome 实机配对和进入工作区已确认。** 本次工作区已通过 250 项 Python 离线测试和 51 项 JavaScript 回归，手机新布局完成了浏览器检查，触摸与软键盘手感仍待实机确认。源码提交不代表新的安装包、正式 Release 或标签。

首次配对需要在电脑操作一次：

1. 正常启动 AgentBoard，电脑访问 **http://127.0.0.1:8765/**。
2. 打开 **设置 → 手机访问**，明确开启第二个私有 IP 入口，默认端口 **8767**。主入口仍只供本机使用，不改为全网监听。若提示没有 Windows 许可，点 **允许 Windows 手机连接**，在管理员确认窗口点 **是**；界面会重新检查实际规则。
3. 让安卓手机与电脑连接同一个可信 Wi-Fi。在手机浏览器输入设置中显示的地址，例如 **http://192.168.1.20:8767/**。示例地址请换成电脑实际显示的地址，手机不能用 127.0.0.1 访问电脑。
4. 在手机输入电脑显示的 **8 位单次配对码**，5 分钟内完成。过期后重新生成，不要把配对码发给别人。

配对成功后，该设备可保持登录 30 天；电脑可撤销单台设备。关闭手机访问会立即撤销所有配对设备，再次开启后需重新配对。关闭手机网页不会停止任务，也不会撤销设备授权。

手机可自由讨论、选择已有项目，也可新建项目并让电脑自动创建文件夹，不必在手机上输入电脑目录。需要指定已有电脑目录时，可先在电脑添加项目，再在手机选择它。后台重启、执行器配置和电脑原生路径选择仍在电脑完成。

电脑必须开机、不睡眠，AgentBoard 后台必须运行。电脑重启后先重新启动 AgentBoard；本版不会自动安装开机系统服务。

**只用于可信 Wi-Fi。当前使用 HTTP；配对不是传输加密。不支持公网、路由器端口转发或把电脑暴露到互联网。**

连不上时按顺序检查：

- 地址是否与电脑当前显示的一致，手机是否真的连到同一个 Wi-Fi；电脑换网络后地址可能变化。
- 手机访问是否开启，电脑是否仍开机且后台运行。
- Windows 是否拦截了这个入口。可能需要一次防火墙授权，具体以本机检查与提示为准；只为实际使用的 Python 程序、TCP 端口和本地网段放行，适用网络配置应与当前连接一致。不要关闭整个防火墙，也不要添加所有程序、所有端口、所有网络都能访问的规则。
- 公寓或公共 Wi-Fi 可能禁止设备互相访问。此时正确放行防火墙也可能无效，可改用自己的私人路由器，或后续配置专门的私有网络；不要用公网端口转发绕过。

安全边界见 [SECURITY.md](../SECURITY.md)。

## Troubleshooting

- **Command not found:** check PATH and restart the terminal/app after installing a CLI.
- **DeepSeek authentication failure:** check the headless profile, not just the GUI login.
- **Codex blocked:** inspect the quota error, account login and `codex app-server` availability.
- **Reference read failure:** correct the local path or page URL. The app will not silently substitute stale references.
- **Source changed since the task ran:** rerun the task against the current source to avoid overwriting newer edits.
- **Port already occupied:** `launch.py` opens the existing board only after its page responds normally. Make sure it is your AgentBoard service; choose an unused local port if you need a separate instance; the optional phone listener normally uses 8767.

Windows is the primary manually verified platform. Report your OS, Python/CLI versions and a redacted error when asking for help.
