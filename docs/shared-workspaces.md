# Shared projects and task workspaces (0.12)

## Use

1. Select the execution environment. With Windows-first routing, connect its updated backend.
2. Open **Projects → Register project**. Enter an existing Git repository root on that host, a name, optional committed text documents, and common file-storage rules.
3. Create a task and select the project. The original directory is registered, never moved. The task pins the current committed revision; uncommitted files in the original checkout are deliberately excluded.
4. Run the task. ACC creates a branch and worktree under the authority's `workspaces/` directory. The task detail shows the actual directory and expandable context; Projects lists retained worktrees.
5. Review the result in that worktree. Acceptance does not merge or copy files into the original project. Use the displayed branch/worktree when reviewing or integrating the changes through Git.

Existing tasks and the explicit unmanaged-directory workflow remain available. Existing native Codex/Claude sessions, credentials, project locations and default working directories are not rewritten.

## Rules attached to every agent

Every role and execution attempt receives project ID/name, policy revision, attempt ID, actual host and worktree, branch/base commit, source fingerprint, output/scratch paths, selected shared-document contents and project rules. The package is hashed and recorded in SQLite before an agent starts. The adapter uses that same worktree as its actual cwd. Shared document text is a fixed input, not a grant of additional permissions.

- Read source from the assigned worktree and shared documents from the pinned context.
- Write source only in that worktree when the Execute role has workspace-write permission.
- Put generated deliverables in `.acc-runtime/outputs/`; put temporary files in `.acc-runtime/scratch/`.
- Do not modify other tasks, the original checkout, native agent directories, credentials, or branch metadata.
- Include changed paths, verification evidence and unresolved issues in the handoff. Do not auto-merge or claim user acceptance.

Codex, Claude and text API adapters all receive the same context structure. This is unconditional prompt attachment, so a model does not have to discover or load a Skill. Claude remains tool-free and API adapters remain text-only; receiving project documents does not grant them filesystem/MCP capabilities. OS/CLI sandbox restrictions still enforce the existing execution scope. This release adds no global Skill installation and no MCP server.

## Isolation and handoff

Different tasks get different physical worktrees and branches. A task's sequential Plan/Execute/Review roles share its worktree, protected by the existing transactional claim/attempt lease. There is no simultaneous writer inside a task. New attempts get distinct context records. Retry preserves partial work in the same task worktree and explicitly reruns only the failed role; restart retains the old worktree and allocates a fresh one from the task's original pinned commit. Unknown process outcomes remain blocked by the existing reconciliation requirement.

Before the next role starts, ACC compares HEAD, tracked changes and eligible untracked files with the previous handoff fingerprint. Read-only roles cannot successfully publish a source mutation. Acceptance rechecks the reviewed source fingerprint. External programs are not controlled by these leases; detected external modifications block the next role/acceptance instead of silently redefining the reviewed version.

Generated output/scratch contents and Git-ignored files are excluded from the source fingerprint. Source diff and each untracked source file are limited to 2 MB, with at most 1,000 untracked files. Large data/binary workflows require a separate artifact/version design. Automatic merge, artifact-file synchronization and worktree deletion are intentionally absent: retained or unsynced work is never silently removed. Worktree contents are excluded from the metadata-size polling traversal.

## Windows and offline use

The directory registry, task records and worktrees live with the selected authority. Windows-first tasks put all three roles on Windows. Managed projects reject the older split-host layout because its handoffs cannot guarantee one physical worktree across hosts.

To enable Mac fallback, connect Windows and use **Verify and pair local clone** on the project. ACC checks the existing local Git repository's history identity and presence of the exact remote commit, then caches the small project/document context. It does not clone a repository, move files, copy datasets, check out another branch or change the local HEAD. Re-pair while connected to refresh the cached committed version.

Offline tasks use that fixed cached commit, only with a mapping belonging to the selected SSH environment. Arbitrary paths and the global Mac directory no longer authorize new offline fallback. Windows-only tasks remain blocked. Uncertain remote submissions stay pinned remotely; existing Windows tasks are never replayed locally. Reconnection does not merge offline results or move a task already started on Mac.

## Compatibility and verification

Schema changes are additive: `projects`, `workspaces`, `task_contexts`, plus three task columns. Old tasks retain their original paths and behavior. New clients require the remote `shared_workspaces` capability before submitting a managed project. Update the Windows backend separately using the existing deployment workflow; updating the desktop alone is insufficient.

Automated checks use temporary real Git repositories and a fake CLI subprocess. They exercise isolation, unchanged original files, context/cwd injection, retry/restart, stale attempts, external mutation detection, acceptance, path/document validation, offline pairing and legacy compatibility. These checks do not establish actual Windows connectivity or live Codex/Claude model execution.
