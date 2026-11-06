# Parallel task graphs — 0.14.0

The planner emits an `acc_plan` with 1–24 assignments. Each node has a unique `id`, `depends_on`, `role`, `slot`, `instruction`, `access` and `browser`. Dependency IDs refer to nodes in that plan. Cycles, missing dependencies and disconnected final delivery are rejected before any assignments start. The final node is Deliver and must transitively join all other nodes.

Example:

```json
{"steps":[
  {"id":"city_a","depends_on":[],"role":"Execute","slot":0,"instruction":"Research city A and verify dated hotel prices.","access":"read-only","browser":"isolated"},
  {"id":"city_b","depends_on":[],"role":"Execute","slot":1,"instruction":"Research city B and verify dated hotel prices.","access":"read-only","browser":"isolated"},
  {"id":"compare","depends_on":["city_a","city_b"],"role":"Deliver","slot":2,"instruction":"Compare evidence and deliver the recommendation.","access":"read-only","browser":"isolated"}
]}
```

The authority schedules at most three simultaneous calls per host, including calls from other tasks. Nodes become ready when their own dependencies succeed. Unrelated branches need not finish first. The broker, SSH service and interactive Windows worker all support concurrent dispatch. No task is moved between hosts.

Task details show the graph immediately; branches appear after planning. Click a node to inspect instructions, prerequisites, requested model, output and errors. Pending nodes distinguish dependency waits from waiting for capacity or shared resources. Older ordered tasks render as a chain.

A Deliver node may emit a follow-up `acc_plan` plus a succeeded `acc_result` with `accepted:false`. Its node becomes Coordinate; new roots depend on it, inherit upstream evidence, and end in another Deliver. Up to three follow-up rounds are allowed. Final delivery requires `accepted:true`. Failed Review/Deliver can identify `rework_ids`; those upstream executors and their descendants rerun, with feedback, after running calls settle. Without explicit IDs all upstream executors are reconsidered. Unrelated successful branches are retained. Unknown native outcomes are never replayed automatically.

## Resource boundaries

- `browser:isolated` gives each node a persistent ACC-only profile and independent lock. Login handoff opens that exact profile. Sessions/cookies are never copied between profiles.
- `browser:shared` uses the existing ACC shared login profile. Shared browser calls queue; they do not compete for the same live profile.
- `access:read-only` is enforced even when the task permits writes. Workspace writes require Codex Execute/Deliver and explicit task write permission. A write excludes concurrent reads/writes in overlapping workspace directories. Parallel editing/automatic Git branch merging is not included.
- Old ordered plans, legacy tasks and native authentication remain compatible. A 0.14 desktop rejects new adaptive submissions to workers advertising only the 0.13 capability.

## Validation and handoff

130 Python tests cover dependencies, atomic multi-connection claims, concurrency limits, early joins, sibling failures, pause/cancel, targeted rework, follow-up rounds, lost leases, resource ownership and multiple login blockers. Frontend build and graph layout/render checks pass. JSON bridge smoke tests demonstrate overlapping simulated agents. Frozen backend checks run with Python absent from PATH and include fake native CLI session resume and managed workspace acceptance.

Real Windows CLI and website/login concurrency have not been verified in this development environment. Browser visual/click inspection is unavailable in this session; graph rendering and geometry were checked through React rendering and assertions. Windows uses the existing `scripts/update_windows.ps1` backup/upgrade/probe path after extracting the matching source version. Mac release assets must be published before in-app update can offer 0.14.0.
