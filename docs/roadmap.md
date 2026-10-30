# Roadmap and acceptance gates

This is an implementation plan, not a list of shipped features.

## P0 — Make the preview dependable

1. **Connection diagnostics**: staged SSH/auth/Python/protocol/CLI checks, copyable redacted report, explicit configuration migration. Gate: real Mac↔Windows and Mac↔Linux tests, disconnect and reconnect with no duplicate task execution.
2. **Public onboarding**: first-run CLI/provider detection, custom executable paths, optional worker deployment wizard. Gate: clean Mac can install and complete a task without a terminal when using a text provider.
3. **Packaging and updates**: Apple Developer ID signing/notarization, installed-upgrade/rollback acceptance testing, Intel/Windows/Linux builds. Gate: installed upgrade preserves profiles and state; rollback tested. Requires maintainer signing credentials and CI runners.
4. **Usability/accessibility**: keyboard navigation, theme contrast, screen-reader labels, screenshots from real native UI, multi-language UI. Gate: three themes pass contrast and focus checks on every screen.

## P1 — Reliable work and context

5. **Dynamic task graph**: validate planner output, dependency-cycle detection, host/resource/tool constraints. Gate: no Windows-only task runs elsewhere; invalid plans cannot start.
6. **Isolated write-enabled execution**: Git worktrees, approval UI, bounded file grants, patch review and independent test runners. Gate: parallel tasks never write the same tree; external side effects require explicit approval.
7. **Native session continuation and robust history**: version-specific parsers, file rotation/truncation, resume IDs, source deduplication and tested redaction. Gate: restart/reimport is idempotent and native stores remain unchanged.
8. **MCP context server**: task-scoped tools for context, handoffs, history and artifacts; freshness/provenance and grant expiry. Gate: one task cannot retrieve another task's private context without a grant.

## P2 — Multiple workers and storage

9. **Durable worker service**: supervised startup, per-host identity, cancellation and leases across service restarts. Gate: kill/restart does not duplicate execution or falsely mark completion.
10. **Worker pool routing**: multiple simultaneous workers with OS/tools/resources/data-locality constraints. Current saved profiles are not a worker pool. Gate: offline hosts leave tasks explicitly queued/blocked without silent fallback.
11. **Resumable artifact sync**: content hashes, chunk verification, manifests and provenance. Gate: interrupted transfer resumes without corruption or unexpected full downloads.
12. **Backups and disk budgets**: Windows-first retention, bounded Mac offline queues, measured cache cleanup and recoverable snapshots. Gate: large archives/datasets do not accumulate on Mac; unsynced work is never evicted.

## Provider expansion

Add native Anthropic Messages and OpenAI Responses adapters, explicit capability discovery, usage/cost reporting and real opt-in integration tests. Keep text-model providers distinct from tool-using agents. Model selection should come from provider discovery where supported instead of hardcoded marketing names.

## Contribution priorities

Reproducible bug reports with redacted diagnostics; contract tests for provider variants; cross-platform release CI; native UI/accessibility testing. Do not report fake percentages of completion. Each milestone needs its own evidence and acceptance gate.

Implemented in 0.4: signed in-app macOS updates, download progress, task quiescence and restart. Installed GUI upgrade validation remains outstanding.
