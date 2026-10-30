# Agent collaboration rules

- Read README.md and docs/architecture.md before changing architecture.
- The selected authority owns tasks and events. New installations default to local. Preserve explicit Windows-first profiles and never silently move a remote step to this computer.
- Keep native Codex/Claude session directories and authentication files unchanged.
- Do not commit credentials, transcripts, databases, local configuration or build environments.
- Use one branch/worktree per concurrent task; include a brief handoff with changes, checks and unresolved issues.
- Run Python unit tests, the JSON bridge smoke test and npm run build for affected changes.
- Release validation must also exercise the frozen backend without Python on PATH.
- Explicitly distinguish simulated tests from real CLI and cross-host tests.
- Never mark a task Completed without explicit acceptance. Preserve unknown execution outcomes on disconnect.
