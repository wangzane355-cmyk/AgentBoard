# Managed DeepSeek runtimes

Open **Manage agents → DeepSeek runtime versions and startup checks**. This manages the background CLI, not the desktop GUI. The [official headless interface](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/headless/README.md) supports version/help checks without a model call.

- **Pin installed copy:** copy the installed CLI's complete dependency tree and Node runtime into a dedicated local version slot. Existing desktop applications, npm caches and credentials are not moved or deleted. Windows copies exclude directory junctions; any incomplete copy must pass checks before it can be selected.
- **Check official updates:** fetch version metadata from the official npm registry. This neither downloads nor activates a version.
- **Prepare version:** enter an exact version. The optional installer uses official npm, exact package selection, engine checks and disabled lifecycle scripts. Dependencies needing install scripts may fail validation; the current version remains selected. Preparation can take several minutes and has a ten-minute subprocess limit. Node/npm must be installed for the first network preparation; a managed copy keeps its own runtime and npm tooling when available.
- **Use this version:** recheck the package version and headless help, then change the current pointer. The former selection becomes the rollback target. Switching and checking are refused while tasks or conversations run.
- **Roll back:** recheck and select the retained previous slot. No old slot is automatically removed. A first installation has no previous slot; rollback becomes available after a later switch.

Preparation never activates automatically. Failed and interrupted staging directories may remain for diagnosis; no startup path deletes or repairs them automatically. Installer diagnostics stay in ignored `data/executor-installer.log`.

Slots normally live outside projects in `%LOCALAPPDATA%/AgentBoard/executors` on Windows or `~/.local/share/AgentBoard/executors` elsewhere. Override with `AGENTBOARD_EXECUTORS_DIR` before the first preparation. Selection metadata lives in ignored `data/executors.json`; do not share it. Once a slot is selected it takes precedence over cache/PATH discovery. Missing or failed managed versions produce a clear failure rather than silently choosing another program.

Startup checks confirm the selected version and file availability. A changed profile gets a full help check; full preparation/activation checks use an empty temporary working directory. No credentials are copied into slots and no model requests are made. Account sign-in, provider connectivity and tool behavior still need a separately authorized live test. Node/system upgrades and automatic background updates are outside this feature.

Local snapshot transfer copies existing package licenses alongside the software. Remote preparations follow [npm's documented installation behavior](https://docs.npmjs.com/cli/v11/commands/npm-install/). AgentBoard's GitHub repository distributes its manager code, not third-party executors or user configuration.
