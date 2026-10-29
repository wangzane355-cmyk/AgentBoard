# AgentBoard contributor instructions

- Read README.md, CONTRIBUTING.md and CHANGELOG.md before changing behavior.
- Keep public code and documentation free of personal paths, private transcripts and credentials.
- Never commit data/, executor configuration or worker copies.
- Preserve state compatibility and Python-controlled scope, quota, deadlines and routing.
- Keep live model calls out of offline tests; they require explicit task authorization.
- Verify changes with relevant checks and state precisely what was actually tested.
- Use demo.py for public screenshots; label sample data clearly.
- Do not restart a local server while a user task or chat batch is active.
