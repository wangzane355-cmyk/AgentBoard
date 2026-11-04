# Model and reasoning preferences

Open **Manage agents → Codex model and reasoning**. Choose a model and an advertised reasoning level, or keep **Follow Codex defaults**. Saving does not invoke a model. Preferences live in ignored local `data/model-settings.json`; AgentBoard never edits the global Codex configuration.

The picker reads only model IDs, names and supported reasoning levels from the local Codex `models_cache.json`. It does not transmit credentials or fetch a model list. The catalog is a cached reference, not proof that the current account can invoke every entry. Refresh the model catalog in Codex itself if it is missing or outdated, then refresh AgentBoard. Without a catalog, the root configuration's model remains selectable, with no unverified reasoning options.

The displayed local defaults are a reference from root-level `config.toml` keys. Project, profile or managed settings may differ. Leaving preferences empty passes no model/effort override. Selecting only an effort pins the referenced model for that invocation, so a project default cannot pair the chosen effort with a different model. Model changes with inherited effort must still pass capability validation.

## Per-task settings

Selecting Codex on a task reveals optional model/effort overrides. Empty fields inherit AgentBoard's agent settings. Resolve and validate settings at launch, and snapshot them in the run record. Later preference changes cannot change a started run. A quota-triggered fallback to DeepSeek drops all Codex model parameters. The existing 15% quota cutoff, scope checks and deadlines still apply.

Chats use the agent preferences for each reply. Preference changes are blocked while Codex is involved in a running task or room batch, including when another room member is currently replying.

## Requested versus confirmed

Runs, task capsules and Codex chat replies retain requested settings. A supported CLI startup header can additionally confirm the model and reasoning effort from the executor log. The UI labels settings as **Requested (unconfirmed)** until such evidence exists. Selecting a model or receiving a settings-save response does not verify account access. Old records without metadata remain readable.

DeepSeek continues using its Harness profile. Generic CLI adapters keep their configured arguments; API adapters retain their existing model field. This release does not invent universal reasoning controls for these connections. No new account is required.

## Validation

Offline checks cover model/effort compatibility, persistence, argument boundaries, defaults restoration, configuration isolation, per-task snapshots, quota fallback and active-work guards. Browser checks use an isolated sample workspace. No live model call or account-access verification is part of these checks.

Codex argument behavior follows the official [developer commands](https://learn.chatgpt.com/docs/developer-commands) and [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference). The installed client's cached capabilities determine the actual picker options.
