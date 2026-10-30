# Agent Control Center

**A native desktop workspace for planning, execution and review across agent CLIs and text models.** Start on one computer; add SSH environments when you need them.

Tauri 2 · React · TypeScript · Python · SQLite · MIT

> **Preview software.** The current workflow is read-only: Codex can inspect files, Claude Code is tool-free, and API models receive text only. This is not an autonomous coding agent, a trading system, or a production multi-user service. See [limitations](#current-limits) before relying on results.

## Install

[Download the latest release](https://github.com/LQ-09/multi-agent-control-center/releases).

The supplied `.pkg` is for **Apple Silicon macOS**. Quit an older running version, double-click the package, follow the installer, then open **Agent Control Center** from Applications. The backend runtime is included: no Python, Node, Rust or Terminal launcher is needed to open the installed app.

The build is ad-hoc signed, **not Apple Developer ID signed or notarized**. macOS may require explicit confirmation in System Settings → Privacy & Security. There are no Intel Mac, Windows or Linux desktop installers in this release. The Python remote service supports Windows, macOS and Linux; only its local POSIX handshake has been tested here.

## Update without reinstalling

Starting with **0.4.0**, open **Settings → App updates → Check for updates → Install and restart**. The app downloads the signed macOS update from this repository, verifies its signature and signed version, replaces the application and restarts. Settings, databases and native agent sessions remain in their existing locations.

If you currently have 0.3.x or older, quit it and install the 0.4.0 `.pkg` once over the existing app. **Do not uninstall or delete application data.** Later versions can use the in-app updater. Pause/cancel pending work first; updating is refused for active/queued/blocked tasks or an unknown remote state. A failed check/download can be retried. macOS may ask for permission to replace an app in Applications.

The updater covers the desktop and its bundled local backend. Separately deployed SSH workers are not automatically upgraded. Releases remain preview software even when published on the updater's default GitHub release channel.

## Language and text size

Version 0.5 adds **简体中文 / English** and four text sizes: **100%, 115%, 130%, 150%**. Use the controls in the top bar or **Settings → Appearance** (中文：**设置 → 显示设置**). New display preferences default to Chinese and 115%; selections apply immediately and persist across restarts. Themes remain independent.

Language changes affect interface labels, task states and common messages. Your task text, model output, paths and technical diagnostics are preserved. No content is sent to a translation service. Larger text wraps controls and panels; narrow boards can scroll horizontally.

## First task: one computer is enough

1. Open the app. New installations select **This computer**; no SSH connection is required.
2. Install and authenticate **Codex CLI**, or configure a text provider under **Providers**. Claude Code is optional. The app does not install or log in to agent CLIs for you.
3. Choose **New task**. Enter a goal, acceptance criteria and an existing absolute workspace directory on the selected execution host.
4. Choose an agent for **Planner**, **Executor** and **Reviewer**. You may use the same agent for all three.
5. Create the draft, then click **Run**. Inspect the attributed timeline and handoffs.
6. The task stops at **Verifying**. Click **Accept result** only after checking the evidence yourself.

For a no-cost walkthrough, select **Demo** from the environment menu. Demo uses simulated agents and a separate local database; it never makes model requests or imports native history. Local mode is real execution, not a demo.

## Three themes

The top-right theme selector offers **Light (black on white)**, **Dark (white on black)** and **Dark blue**. The preference is saved locally. Theme changes cover the dashboard, task details, logs, providers, settings and dialogs. This is a native app using an embedded WebView, not a hosted web dashboard.

## Agents and providers

| Adapter | Authentication | Capabilities in this release |
|---|---|---|
| Codex CLI | Your existing CLI login | Read-only workspace analysis; structured CLI output |
| Claude Code CLI | Your existing CLI login | Text reasoning; tools and MCP explicitly disabled |
| DeepSeek | Session API key or `DEEPSEEK_API_KEY` | Text planning, analysis and review via Chat Completions |
| OpenAI-compatible API | Session key or a named host environment variable | Text responses; exact model ID and base URL are configurable |
| Ollama / compatible local server | Usually no key for local Ollama | Text responses from a model you already installed; no automatic model downloads |

**CLI agents and model APIs are different.** Adding a model endpoint does not give it shell, filesystem, browsing or MCP tools. API agents receive only the task brief, acceptance criteria and bounded text handoffs. Native transcripts are not automatically attached.

### Connect DeepSeek

1. Open **Providers** on the environment where the requests should run.
2. Choose the DeepSeek preset: base URL `https://api.deepseek.com`, model `deepseek-flash` (editable).
3. Save the profile. Select **Set session key**, paste your key and apply it. Alternatively set `DEEPSEEK_API_KEY` in the execution host's service environment.
4. Select the provider for a role when creating a task. No paid request runs until you click Run.

The preset follows the [official DeepSeek quickstart](https://api-docs.deepseek.com/). Model names and access can change; use an exact model ID available to your account. **No live paid DeepSeek request was used to validate this release.**

### Connect another compatible API

In Providers, enter a unique lowercase ID, display name, **base URL** (for example `https://api.example.com/v1`), exact model ID and the environment variable containing its key. The adapter appends `/chat/completions`; do not include that suffix in the base URL. It sends `model`, `messages`, `stream: false`, and `max_tokens: 4096`.

The endpoint must implement the OpenAI-style Chat Completions response with `choices[0].message.content`. Tool-call responses, incomplete responses, multimodal payloads, Responses API and Anthropic Messages API are not supported by this adapter. Some providers/models need additional parameters and may not work yet.

For local Ollama, use `http://127.0.0.1:11434/v1`, an installed model ID, and a blank key environment field. See [Ollama's compatibility documentation](https://docs.ollama.com/api/openai-compatibility). Local URLs refer to the **execution host**, not necessarily the desktop client.

### Key handling and data boundaries

- Session keys stay in the selected backend's memory only. They disappear when that backend exits or the SSH service disconnects. A remote session key travels through authenticated SSH to the explicitly selected host.
- Only non-secret provider configuration is persisted. Keys are not returned in snapshots, written to task history or committed to Git. Optional environment-variable keys are read on the execution host.
- Changing a provider's endpoint clears its session key. Provider redirects are rejected so authorization headers are not forwarded to another URL.
- HTTPS is required except for loopback HTTP model servers. TLS verification uses a bundled CA trust store in the release app.
- Clicking Run authorizes transmission of the task text and handoffs to the chosen API endpoint. Provider charges may apply. Cancelling cannot retract an already submitted HTTP request or guarantee a refund; late results are discarded.
- Requests have bounded input/output, a network timeout, lease heartbeats and **no automatic retry**. Do not put secrets in prompts. Redaction is best-effort, not a guarantee.

## Add another environment

An environment is a selected execution authority with its own task database and workspace paths. **Only one authority is active in the desktop at a time.** You can save up to 16 profiles and switch between them. This release does not concurrently schedule a task over an arbitrary pool of hosts.

### 1. Prepare SSH

Install Python 3.11+ and whichever CLI agents you want on the remote computer. Configure an SSH alias, key authentication and a verified host key using your normal SSH client. Tailscale is useful when machines are on different networks, but any authenticated reachable SSH connection works. No unauthenticated HTTP execution server is exposed.

Example `~/.ssh/config` (replace all placeholders):

```sshconfig
Host my-worker
    HostName YOUR_PRIVATE_HOSTNAME_OR_IP
    User YOUR_REMOTE_USERNAME
    IdentityFile ~/.ssh/YOUR_KEY_FILE
```

Verify `ssh my-worker hostname` in your own terminal. The app uses noninteractive SSH (`BatchMode=yes`) and strict host-key checking; it does not enroll unknown hosts or prompt for passwords.

### 2. Copy the worker sources

Clone this repository on the remote host, or copy its `backend/` directory. Do not copy the desktop cache, database, native sessions or credentials.

Linux/macOS example from the local checkout:

```sh
ssh my-worker 'mkdir -p ~/agent-control-center'
scp -r backend my-worker:agent-control-center/
```

Windows convenience script (run from the source checkout):

```sh
python3 scripts/deploy_windows.py my-worker
```

This creates `AgentControlCenter/backend` under the Windows user's home and copies only application Python sources. It does not install Python/CLIs or alter native authentication. Update the worker sources when upgrading the app. With a source checkout, `python3 -m pip install -r requirements.txt` supplies the CA bundle used by API providers; a system trust store is the fallback when it is absent.

### 3. Add a profile in the app

Open **Settings**:

| Field | Meaning / example |
|---|---|
| Execution mode | SSH environment |
| Remote OS | Linux/macOS or Windows |
| Execution layout | All three roles on the remote host |
| SSH alias | `my-worker` |
| Remote Python | `python3` on POSIX, or the full Python executable path on Windows |
| Remote service.py | Absolute path to `backend/service.py` |
| Remote storage | A writable, host-local directory dedicated to this environment |
| Local planning workspace | Used only by the optional split layout |

Give the profile an ID and name, save it, then select it from the environment menu. Or use **Apply environment** to select the currently edited settings immediately. **Test saved connection** checks the applied settings, not unsaved form edits.

The app launches the stdio service through SSH; there is no extra port to open. Configure API profiles and session keys *after selecting the environment*, because providers belong to that authority. A new remote single-host profile requires the v0.3 worker (`protocol: 2`).

### Optional Windows-first layout

Select **Local plan/review + Windows execution** when you specifically want that arrangement. Windows remains the canonical database/history/artifact host; only planning and review run locally. This layout requires a Windows authority. API providers are currently selectable only for its remote Executor role; local planning/review use Codex or Claude CLI.

Existing v0.2 Windows-first settings are preserved on upgrade. They are not silently switched to local mode. A disconnected remote blocks live actions and shows the actual error; it never silently reroutes Windows work to Mac.

### Switching and storage

Pause/cancel or reconcile pending work before changing environments or provider settings. Existing tasks stay in their original authority; profiles are not database migrations. Use separate storage roots for different execution layouts. Do not share an active SQLite database or native agent session directory over a network filesystem.

Local metadata admission stops around 80 MB. The displayed 1 GB desktop cache budget is a **design target**, not comprehensive enforcement of WebView, runtime and workspace storage. The app does not clone repositories, download models/datasets or bulk-copy archives. Large artifact sync and automatic cleanup are not implemented.

## Troubleshooting

| Symptom | What to check |
|---|---|
| Remote not connected | Read the full connection error. Check the applied alias, remote OS, Python, service path and storage directory. Use Reconnect; failures are not silently retried. |
| `Permission denied (publickey)` | Confirm the same alias authenticates noninteractively with SSH keys. The app does not prompt for SSH passwords. |
| Host key verification failed | Verify the host fingerprint in your normal SSH client; do not disable host-key verification. |
| Remote timeout / protocol mismatch | Deploy the current backend, use the correct OS/layout, and ensure startup scripts do not print extra stdout. |
| CLI not found | Install it on the execution host. Finder launches discover standard Homebrew, local-bin and nvm paths. Unusual installations may need source-level configuration; a custom executable-path UI is planned. |
| API HTTP 401/403 | Check the key on the selected authority. Session keys expire when the backend closes. |
| API HTTP 400/404 | Verify the exact model ID and compatible Chat Completions base URL. |
| Task Blocked after disconnect | The previous execution outcome is unknown. Inspect/reconcile it before cancelling or creating another task. No automatic replay. |

## Architecture and collaboration

- `src/`: native WebView UI, themes, environments and providers.
- `src-tauri/`: narrow Rust IPC and bundled backend launcher.
- `backend/core.py`: SQLite tasks, immutable events, leases and acceptance.
- `backend/agents.py`: CLI execution and text-API step lifecycle.
- `backend/providers.py`: provider contracts, secret isolation and HTTP adapter.
- `backend/bridge.py`: local authority and SSH connection management.
- `backend/service.py`: cross-platform remote stdio service.
- `backend/history.py`: explicitly requested, bounded, read-only native JSONL indexing.
- `tests/`: behavior tests; no live provider credentials required.

Read [architecture](docs/architecture.md), [roadmap](docs/roadmap.md), [contributing](CONTRIBUTING.md), [agent collaboration rules](AGENTS.md) and [security](SECURITY.md). Contributions and additional adapters are welcome; use scoped branches/worktrees and include evidence with handoffs.

## Build from source

Development requires Python 3.11+, Node.js 22+, Rust and the OS prerequisites for Tauri 2. The packaged Mac app does not require those developer tools.

```sh
git clone https://github.com/LQ-09/multi-agent-control-center.git
cd multi-agent-control-center
python3 -m venv .build-venv
.build-venv/bin/python -m pip install -r requirements-build.txt
npm ci
export ACC_PYTHON="$PWD/.build-venv/bin/python"
npm run tauri dev
```

Release build and `.pkg` instructions are in [CONTRIBUTING.md](CONTRIBUTING.md). `npm run dev` serves development assets for Tauri, not a functional standalone browser product.

## Current limits

Fixed Plan → Execute → Review workflow; explicit human acceptance; read-only CLI/tool profiles; text-only APIs; one active authority at a time. No arbitrary planner-generated DAGs, native-session resume, arbitrary tool execution, MCP context server, unattended durable worker service, full offline task queue, Git worktree automation, large artifact transfer, multi-user ACLs, comprehensive backup/restore or notarization yet.

Native history imports are opt-in and bounded (100 files / 4 MB per scan); parsing covers basic JSONL formats, not every agent/version or desktop database. Same-size in-place rewrites and cross-source deduplication need further work. Imported records are limited in the UI; it is not a complete global search engine.

## Validation status

Display tests also check bilingual rendered settings, preference persistence, font limits and unchanged paths (`npm run test:display`).

37 automated tests cover task/lease behavior, local routing, environment isolation, SSH command quoting, provider contracts, credential non-persistence, redirects, incomplete responses and cancellation. Source and frozen-backend Demo smoke tests are run during release preparation. API tests use mocked responses; **live DeepSeek/OpenAI/Ollama calls and real cross-host CLI execution are not certified**. Native window interaction and installation still require manual testing. Passing a unit test or compiling the app does not establish those integrations.

## License

[MIT](LICENSE). Bundled third-party runtime components retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). This is an independent community project, not affiliated with the model providers or Microsoft.
