# Agent Control Center — native app 0.2

A Tauri 2 / React / TypeScript desktop client with a Python subprocess bridge and a Windows SQLite authority. The macOS Apple Silicon app includes its Python backend runtime; users do not need Python, Node or Rust to open it. Developer ID signing and notarization are not configured. There is no hosted web dashboard or public execution API.

## What works in the prototype

- Native application source with dashboard, task board/detail, chronological logs, host status, handoffs, artifact viewer, read-only history import and connection settings.
- Persistent tasks/events with a fixed three-step DAG: **Mac plan → Windows execute → Mac review → human acceptance**. Agent choice is configurable for each role.
- Mac Python broker owns SSH; local Codex never needs to open SSH from its sandbox. Background CLI subprocesses use stdin prompts and structured output.
- Live mode stores task/event/history/handoff data in the configured Windows root. Mac retains connection settings and an in-memory live snapshot; it never falls back to a local live database.
- Explicit, labelled demo mode uses its own small local database and simulated agents. Nothing launches until Run is pressed. Demo mode never scans native history.
- Read-only Codex adapter (`-a never`, `exec --json --sandbox read-only`); tool-free Claude adapter (`--tools ''`, empty strict MCP configuration). This build is for analysis and patch proposals, not autonomous file modification.
- Idempotent task creation, serialized SQLite writes, per-attempt leases, dependency enforcement, pending pause/cancel, process-group stop, hash-labelled text artifacts and redacted log events.
- Incremental bounded native JSONL import with original source paths and byte offsets. Records stay Windows-side; latest 100 are paged into the UI.

## Install on Mac

Download the macOS `.pkg` installer from GitHub Releases, double-click it and follow the installer. Then open **Agent Control Center** from **Applications**. No terminal launcher or Python installation is needed. This personal build is ad-hoc signed, not notarized; macOS may require explicit confirmation in Privacy & Security.

The frozen Python backend is included inside the bundle. Existing Codex/Claude CLI installations and authentication stay outside the app. The app adds standard Homebrew, local-bin and nvm installation paths for Finder launches. Saved Live settings connect once at startup; failures preserve the actual transport error and provide a Reconnect button. No execution command is automatically replayed.

Initial mode is Demo: create a task, Run, inspect three simulated handoffs, then Accept. No model requests are made in Demo. Windows live connectivity and native UI interaction are still pending end-to-end validation.

See [CONTRIBUTING.md](CONTRIBUTING.md) for source builds and [AGENTS.md](AGENTS.md) for multi-agent collaboration rules. The original architecture in [docs/architecture.md](docs/architecture.md) is a roadmap, not a claim that every phase is implemented.

## Connect your Windows machine


Run this small deploy helper from the Mac Terminal where SSH already works:

```bash
python3 scripts/deploy_windows.py my-worker
```

It creates `%USERPROFILE%\AgentControlCenter`, probes Python/Codex versions, and copies only the five backend Python sources. It does not install an agent, move sessions, copy authentication or alter SSH settings. Re-running replaces these application source files only. Python 3.11+ must already be installed on Windows. Keep the native app disconnected while deploying an update.

In the native app, Settings:

1. Set mode to Live.
2. Use SSH alias `my-worker`.
3. Set Windows Python to its actual executable, or `python` if visible to SSH.
4. Set service path to `<Windows user home>\AgentControlCenter\backend\service.py`.
5. Choose Windows persistent storage root, e.g. `<Windows user home>\AgentControlCenter\state`; a larger drive is preferable once verified.
6. Choose an existing Mac directory for read-only planning/review. Save, then Test connection.

The connection performs strict SSH host-key checks and a service handshake, reports installed agent versions and root, and rejects a non-Windows authority. A missing service or CLI appears as an error; it never becomes a simulated success.

Create a small read-only task first. The Windows workspace must exist. Mac steps receive the brief and preceding text handoffs, not a mirror of the Windows repository. Claude is tool-free in this prototype, so it can review supplied text but cannot inspect files. Codex can read its configured workspace. All native provider authentication remains with the installed CLI and user account. API/subscription compatibility and billing have not been certified.

## Verification

```bash
python3 -m unittest discover -s tests -v
python3 scripts/smoke_demo.py
npm run build
```

At delivery:

- 20 Python tests pass, including a real subprocess protocol test with a fake CLI, two-connection lease claim race, restart persistence, scope routing, idempotency, lease expiry, acceptance and source immutability.
- The actual JSON-lines bridge smoke test passes with simulated agents through final explicit acceptance, both from source and from the frozen backend with Homebrew/Conda absent from PATH.
- TypeScript strict type-check and esbuild production bundle pass using locally cached packages.
- Native Tauri/Rust release compilation and macOS `.app` bundling pass with Rust/Cargo 1.99.1; bundle size approximately 44 MiB including the frozen backend.
- Visual/browser runtime QA: **blocked** by the execution environment's Chromium process permission error. No screenshot is represented as a verified native window.
- Real Windows service, Codex/Claude execution, cancellation and SSH reconnection: **not integration-tested** from this restricted session. User Terminal SSH success alone does not establish these.

## Storage and limits

Live authoritative SQLite and history are Windows-local; no shared live native database. Text handoffs are bounded to 24 KB, each step's incoming output is capped at 2 MB, only 160 events / 200 tasks / 100 history records are returned in a snapshot. Prototype metadata admission stops above 80 MB, leaving headroom for control messages. There is no large artifact transfer, dataset download or automatic repository clone.

Mac UI shows the **1 GB design budget** and measured files under the app cache. Demo state uses a separate 80 MB admission cap. Full process-wide enforcement (WebView cache, updater staging, active workspace monitoring, native-runtime growth) is **not implemented**, so the 1 GB number is a target, not a certified whole-app guarantee. Native sessions and active workspaces are excluded and are never deleted by this code.

History scan: up to 100 files and 4 MB per host, 256 KB/file per scan, maximum record size 64 KB. Oversized/partial records stop that file's scan; other files continue. Current parser covers basic JSONL text/metadata, not all version-specific desktop formats. File rotation/truncation is handled with identity and offset; same-size in-place rewriting and cross-source duplicate correlation are not fully handled. Redaction is best-effort; do not import sensitive history before expanding redaction tests. Files are opened read-only and no native SQLite is opened.

## Recovery boundaries

Closing the bridge gracefully stops owned local processes. SSH service EOF stops its Windows child processes. Lost leases become Blocked and are never automatically retried. Pause interrupts a step and restarts that step on resume; native-session continuation is not implemented. A hard process/OS crash can leave an external operation outcome unknown: reconcile it before starting a new task. Cancellation is not a rollback.

This prototype uses SSH identity and a single-owner, private stdio connection. It does not claim production multi-user/task-scoped RPC authentication; internal service operations are not exposed to an agent or public network. Do not expose this JSON protocol through an unauthenticated server. Native agent restrictions are not a replacement for a production OS isolation policy. Do not use this build for trading, credential operations, external submissions or destructive tasks.

## Deferred from the full architecture

Dynamic planner-generated DAGs; arbitrary host reassignment; MCP context server and per-tool grants; unattended durable Windows service; offline durable live task queue; large artifact chunk sync; Git worktree provisioning/merge; native store migration; independent verification runners; full backup/restore; signing/installers; end-to-end cache accounting. Controls not implemented are labelled or omitted instead of mocked as working.

The full architecture review remains the roadmap. This prototype intentionally validates the central interaction: native Mac UI → local broker → local planner + SSH Windows executor → attributed handoff → local reviewer → explicit acceptance.
