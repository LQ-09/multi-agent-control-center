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

## Account usage and model controls (0.6)

The sidebar shows **Account usage / 账户额度**, separated by execution host and CLI account. This covers the currently signed-in account for each CLI on each host; it does not add account switching or discover other logged-out subscriptions. It queries Codex's `account/rateLimits/read` and Claude Code's built-in `/usage` structured report. It displays the server's remaining percentages (`100 − used`), separate windows/scopes, reset timestamps, subscription type where available, and observation time. Multiple models may share a quota: the app does not invent a separate allowance for every model or convert tokens/context size/session cost into subscription quota.

Queries run in background, refresh on demand (15-second minimum spacing) and expire after five minutes. They do not submit model inference prompts. Native credentials remain CLI-owned; no tokens are copied into platform configuration. Account identifiers are short hashes of the CLI-reported email, held in memory. Queries use a temporary workspace and Claude disables customizations and session persistence. Native CLI maintenance, including auth refresh, remains controlled by the CLI itself.

**Unavailable means unknown, never 0% or 100%.** Missing commands, unsupported CLI versions, authentication/network errors and absent subscription meters are shown explicitly. Claude structured usage requires CLI 2.1.273+ and qualifying subscription credentials; API-key, usage-billed or insufficient-scope sessions may not expose it. Generic API profiles show a billing-unavailable note because Chat Completions does not provide a standard balance endpoint. Credits and monetary balances are not inferred from percentages. No automatic model/account switching is enabled.

In **Settings → Default models and effort / 设置 → 默认智能体、模型与思考强度**, choose the default CLI for planning/execution/review and the model ID and reasoning effort for Codex and Claude separately. Each new task also exposes per-role overrides. Selections are saved in the task's steps and passed as CLI arguments, rather than changing native CLI settings. Existing steps keep their selections. Blank model/effort fields intentionally inherit the execution CLI's configuration at run time; for reproducible choices, specify an exact model ID and supported effort. Codex model suggestions come from its account catalog when available. Claude aliases are conveniences, not guarantees of model availability. Unsupported combinations fail visibly.

Default roles are Codex/Codex/Codex until you change them. The task detail shows requested model/effort, and the timeline records the requested configuration plus the CLI's own events. API agents continue to use the model in their provider profile; CLI reasoning flags do not apply to those APIs.

**Remote hosts:** redeploy the v0.6 backend for remote usage and model controls. Older workers remain usable for default CLI tasks, but explicit model/effort overrides are rejected instead of silently ignored. A desktop update does not redeploy workers. In Windows-first split mode the sidebar separates local and remote accounts; role placement is unchanged.

Verified: parser fixtures, scoped-window handling, invalid/missing percentages, defaults persistence, task option immutability, database migration, CLI argument contracts and rendered controls. Live probes in the development environment did not establish working subscription percentages: Codex could not initialize its native state under the execution restrictions, and Claude returned a structured usage response with no plan meters. Actual quotas depend on the installed app's execution host and authentication.

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

### Connect your Codex CLI or Claude Code

These are built-in adapters, not profiles you add under Providers. The application searches for the `codex` and `claude` commands on the execution host. It does not bundle either CLI, install them, or sign in on your behalf. Installing only the Codex or Claude desktop application does not establish that its CLI is available.

1. Install whichever CLI you want to use on the execution computer, following that product's installation instructions. You do not need both.
2. Open that CLI in the terminal as the same operating-system user that runs this application (or the SSH worker), and complete its own sign-in. Confirm the CLI can handle a simple request on its own.
3. Check command discovery in that terminal:

   ```sh
   codex --version
   claude --version
   ```

   Run only the command for the CLI you installed. Version detection confirms the executable is available; it does **not** prove login, quota or model access.
4. Fully quit and reopen Agent Control Center after installing a CLI. Open **Hosts / 主机** and inspect the detected CLI version or error.
5. Create a task and select **Codex** or **Claude Code** for each role. The application starts CLI subprocesses in the background when you click **Run**; you do not need to keep an interactive terminal window open. Credentials stay managed by the CLI; do not paste CLI authentication files into Providers.

For SSH execution, perform installation and login on the **remote computer under the SSH account**. Your Mac's login does not log in the Windows worker. In the Windows-first split layout, local planning/review need their chosen CLI on Mac; execution needs its chosen CLI on Windows. Default single-computer mode needs no second environment.

If Hosts says the command was not found, verify its installation location and restart the app. Standard macOS Homebrew, user-local and nvm paths are searched. A nonstandard executable path currently has no manual picker in the UI. Shell-only environment overrides and custom authentication directories are not automatically imported from an interactive terminal.

**Current boundary:** these adapters start bounded task runs. They do not attach to an already-open terminal conversation or resume native historical sessions. Codex uses read-only tools; Claude Code's tools are disabled in this preview.

### 接入自己的 Codex / Claude Code（中文）

- 不用在「模型服务商」里添加，它们是内置 CLI 适配器；在执行任务的电脑上安装并登录 CLI 后，应用会尝试自动识别。
- 只安装桌面聊天软件不等于已安装 CLI。先在终端确认所需的 `codex --version` 或 `claude --version` 可用，并打开 CLI 完成登录、确认能正常响应。
- 安装后完全退出并重开本应用，在「主机」查看版本。检测到版本不代表登录或额度一定正常。
- 新建任务时给规划、执行、审查角色选择 Codex 或 Claude Code，点击运行后由应用后台启动，不需要一直开着终端。
- 远程任务需要在远程主机用 SSH 登录账户安装和登录；Mac 的登录不会自动传到 Windows。单机使用无需增加环境。
- 当前不会接管已有终端对话或恢复原生历史会话；Codex 只读，Claude Code 暂不启用工具。DeepSeek 等 API 服务商才需要在「模型服务商」里配置地址、模型和密钥。

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

49 automated tests cover task/lease behavior, local routing, environment isolation, SSH command quoting, provider contracts, credential non-persistence, redirects, incomplete responses and cancellation. Source and frozen-backend Demo smoke tests are run during release preparation. API tests use mocked responses; **live DeepSeek/OpenAI/Ollama calls and real cross-host CLI execution are not certified**. Native window interaction and installation still require manual testing. Passing a unit test or compiling the app does not establish those integrations.

## License

[MIT](LICENSE). Bundled third-party runtime components retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). This is an independent community project, not affiliated with the model providers or Microsoft.


### Task input, dictation and quota windows (0.7)

Describe the task; the title is optional and derives from the first line. Leave acceptance criteria blank to let the planning agent generate checkable criteria. These are stored before execution and passed to the executor/reviewer. A missing or invalid criteria block fails planning; final completion still requires your explicit acceptance. Existing manually supplied criteria are preserved. Remote workers need the matching 0.7 backend for automatic criteria.

The last successfully used execution directory is remembered separately for local/demo and each SSH alias + storage root. Local first use inherits the directory in Settings. A remote directory must be set once on its host; no Mac path is substituted. Switching environments never copies workspaces.

**Voice input:** click **Use system dictation** to focus the task description and show instructions, then use your OS dictation shortcut. On Mac, enable Dictation under System Settings → Keyboard and use the configured microphone/Fn shortcut. On Windows, use Win+H. The button itself does not start recording. ACC does not record or upload audio or call an agent to transcribe it. System language, hardware and privacy settings determine offline availability. Review recognized text before submitting. [Apple Dictation instructions](https://support.apple.com/guide/mac-help/mh40584/mac). Actual microphone input in the packaged app has not been verified in the build environment.

Quota cards show the lowest remaining percentage first (for example, 10% weekly ahead of 50% five-hour), with its window, scope, absolute reset time and live countdown. Expand **Other quota windows** for the rest. Reaching zero time does not fabricate a reset: wait for fresh CLI data. Unknown quotas remain unknown, and stale measurements remain marked.

**Hosts:** one computer can use both Codex and Claude. Open Hosts → Add or manage hosts to save additional SSH profiles (up to 16), then select the desired environment. Saved profiles are not represented as connected until selected and tested. This preview uses one authority at a time; it does not schedule one task across an arbitrary three-or-more-host fleet.

**中文：**任务标题可以留空，验收标准由规划 Agent 生成并传给执行与审查 Agent，最后仍由你确认验收。工作目录创建成功后按环境记忆。语音输入使用系统听写快捷键；页面按钮负责聚焦和引导，不会自行录音。额度优先显示剩余最低的窗口和重置倒计时，其余额度可展开。主机页可以添加多个 SSH 配置；单机也可同时配置多个 Agent，目前每次选择一个管理环境。
