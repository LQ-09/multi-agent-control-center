# 0.9 model catalogs

CLI selectors now consume host-reported model and effort lists, with no free-text input or universal effort fallback. Claude initialize control requests add discovery without a user prompt; Codex discovery uses installed app-server protocol. Save/create boundary checks and execution-host preflight reject unavailable explicit choices. CLI default is permitted without discovery. Claude is_error result events fail the step.

Provider model discovery is a bounded, redirect-disabled GET to the explicitly configured /models endpoint. Draft keys are never persisted. Save validates against a recent endpoint/profile catalog; execution validates again. DeepSeek advertised effort levels map to reasoning_effort; generic APIs without a verified capability mapping offer default only. Native fallback behavior is not disabled by this change.

Validation: 57 Python tests, rendered selectors and quota/UI tests, simulated source/frozen backend orchestration, native build/signature checks. Actual Claude 2.1.305 initialize returned model IDs and per-model efforts. Codex metadata probe ended without a supported response in the execution sandbox. Paid inference, remote worker upgrade and installed-app UI are unverified.
