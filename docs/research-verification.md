# Research tools handoff

Changed: live Codex search; Claude WebSearch/WebFetch; per-task ACC browser MCP injection; capability diagnostics; query forms permitted; reviewer source rechecking and dated price evidence required. Native auth/configuration is unchanged.

Checked locally: 109 Python tests, TypeScript/frontend build, JSON bridge simulated orchestration. These checks do not establish Windows browser launch or live Ctrip prices.

## Execution-host rollout

1. Stop pending/running ACC work and preserve unknown outcomes. Back up the deployed backend; compare it with this checkout and preserve any host-specific Claude authentication fixes. Do not overwrite state, native authentication or session directories.
2. Deploy the updated backend Python files. Under the same logged-in Windows account, install Node.js 18+ and Microsoft Edge if absent, then run `python backend/install_browser.py`. This installs the pinned MCP runtime only; it does not authenticate websites.
3. Restart the existing interactive worker when idle and reconnect ACC. Confirm `hello.research` and the next task's `agent.capabilities` event. `configured-unverified` is not a browser health result.
4. Run a Windows-only Codex Plan → Codex Execute → Claude Review task. Execute must use live search and ACC browser navigation/snapshot on a public page. Review must independently reopen the source. Preserve tool events as evidence.
5. Retry the travel task only after the browser check passes: 3–5 diverse Chinese cities, dates 2026-12-14–15 and 2027-01-11–12, two adults/one room. Capture actual Ctrip room offers with observation time, URL, room/area, currency, total and fee/cancellation terms. Do not replace prices with estimates. Respect any previously denied site access; login/CAPTCHA/permission requirements remain blocked until resolved by the user.

Windows deployment and live research are outstanding because this session has no permitted remote deployment channel. No release or completed travel result is implied by the local checks.
