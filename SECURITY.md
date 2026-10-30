# Security and data boundaries

This preview is intended for a single owner on trusted machines. Do not expose the internal JSON protocol as a public HTTP/TCP endpoint. SSH authentication is the remote security boundary; task-scoped multi-user authorization is not implemented.

- Native agent sessions and authentication are never moved into this project or Git.
- Session API keys are memory-only. Optional environment keys remain managed by the operator.
- API endpoints use verified TLS (loopback HTTP excepted), no redirects and no automatic retries.
- Tasks and handoffs can contain sensitive information. Review what you send to a model provider.
- History import is explicit, read-only and best-effort redacted; redaction cannot guarantee secret removal.
- A cancellation is not rollback, and cannot retract an external API request already sent.
- Prefer private network access, verified SSH host keys and least-privilege host accounts.
- Back up the authority before upgrading or changing storage layouts. Do not use this preview for trading, destructive actions, credential operations or external submissions.

Do not post secrets, raw transcripts or exploitable private details in public issues. Use GitHub private vulnerability reporting when available; otherwise report a non-sensitive summary first and request a private channel.
