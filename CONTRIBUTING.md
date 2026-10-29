# Contributing to AgentBoard

Contributions that make local agent coordination clearer, easier to verify and less expensive to supervise are welcome.

## Develop

```bash
python demo.py
python -m unittest -v test_server.py test_context_sources.py test_group_chat.py test_agent_registry.py test_launch.py test_executor_discovery.py test_managed_executors.py
node --check static/appearance.js
node --check static/executors.js
node --check static/agents.js
node --check static/i18n.js
node --check static/app.js
node --check static/chat.js
node --check static/context.js
```

Python 3.10+ is required. Node is only needed for JavaScript syntax checks and any executors installed through npm. The application itself has no third-party Python dependencies or frontend build step.

## Send a change

1. Describe the concrete user problem and expected behavior in an issue or pull request.
2. Make a focused change. Keep state reads compatible with older local records.
3. Add meaningful tests for execution, routing, data-integrity or cancellation changes. UI changes should include visual verification.
4. Update the relevant documentation and changelog.
5. Report checks that actually ran; identify any live behavior that remains unverified.

Never include `data/`, real chat transcripts, worker source copies, account credentials or private screenshots in a contribution. Use the built-in demo for public examples.

## Preserve the core contract

- Python controls scope, quota guards, deadlines, cancellation and peer-reply limits.
- Directed messages invoke only the selected recipient.
- Integration is explicit and rechecks the source and protected files.
- Rollback must not overwrite subsequent user edits.
- A model's completion claim does not substitute for independent evidence.
- Live smoke scripts are separate from offline tests because they can incur usage.

Read [DEEPSEEK_HANDOFF.md](DEEPSEEK_HANDOFF.md) for local task/API collaboration and [SECURITY.md](SECURITY.md) for security boundaries.

## Interface languages

The local UI catalog is in `static/i18n.js`. Keep translations limited to interface text. Project names, paths, task bodies, chat messages and result/log content must preserve their original text. Verify switching both ways in an open form and after an automatic refresh. Language changes must not submit a form or invoke an executor.
