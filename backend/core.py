"""ACC prototype domain model. No third-party Python dependencies; no public listener."""
from __future__ import annotations
import hashlib
from contextlib import contextmanager
import json
import os
import re
import shutil
import sqlite3
import threading
import time
import uuid
from agent_settings import DEFAULTS, defaults, selection
from pathlib import Path, PureWindowsPath, PurePosixPath
from datetime import datetime, timezone

STATES = {'Draft','Queued','Planning','Running','Waiting for Dependency','Waiting for Approval','Waiting for Login','Paused','Blocked','Failed','Verifying','Completed','Cancelled'}
MAX_DB = 80_000_000
MAX_LOG = 8_000

def now(): return datetime.now(timezone.utc).isoformat()
def uid(): return str(uuid.uuid4())
def digest(text): return hashlib.sha256(text.encode()).hexdigest()
def redact(text):
    text = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----', '[REDACTED PRIVATE KEY]', str(text), flags=re.S)
    text = re.sub(r'(?i)(bearer\s+)[\w.\-]+', r'\1[REDACTED]', text)
    text = re.sub(r'(?i)((?:api[_-]?key|access[_-]?token|password|secret)\s*[=:]\s*["\x27]?)[^\s,"\x27}]+', r'\1[REDACTED]', text)
    text = re.sub(r'\bsk-[A-Za-z0-9_-]{12,}', '[REDACTED]', text)
    return text

def clean(value, limit=12000): return redact(str(value))[:limit]

def validate_execution_workspace(workspace):
    path=PureWindowsPath(workspace) if PureWindowsPath(workspace).drive else PurePosixPath(workspace)
    if not path.is_absolute() or len(path.parts)<3 or '..' in path.parts or workspace.rstrip('/\\').casefold()==str(Path.home()).rstrip('/\\').casefold():
        raise ValueError('Choose an absolute project directory, not a drive root or home directory')
    protected=[str(Path.home()/name) for name in ('.codex','.claude','.ssh','.aws')]
    protected += [os.environ[key] for key in ('SystemRoot','ProgramFiles','ProgramFiles(x86)','CODEX_HOME','CODEX_SQLITE_HOME','CLAUDE_CONFIG_DIR') if os.environ.get(key)]
    if PureWindowsPath(workspace).drive:
        protected += ['C:/Windows','C:/Program Files','C:/Program Files (x86)']
    if any(part.casefold() in ('.codex','.claude','.ssh','.aws') for part in path.parts):
        raise ValueError('Native agent and credential directories cannot be execution workspaces')
    for item in protected:
        # Resolve native paths so aliases cannot grant access to protected stores.
        if os.name=='nt' or not PureWindowsPath(item).drive:item=str(Path(item).expanduser().resolve())
        other=PureWindowsPath(item) if PureWindowsPath(item).drive else PurePosixPath(item)
        if type(path) is type(other) and (path==other or other in path.parents or path in other.parents):
            raise ValueError('System, native agent and credential directories cannot be execution workspaces')
    return workspace

def result_contract(output, required=False):
    """Parse the final handoff, never infer success from a CLI exit code."""
    opening='<acc_result>'; closing='</acc_result>'
    if opening not in output:
        if required or '<acc_result' in output: raise ValueError('Missing structured agent result; outcome is unverified.')
        return None
    if output.count(opening)!=1 or output.count(closing)>1:
        raise ValueError('Expected exactly one structured agent result.')
    payload=output.split(opening,1)[1]
    missing_close=closing not in payload
    if not missing_close:payload=payload.split(closing,1)[0]
    try: result=json.loads(payload)
    except (ValueError,TypeError): raise ValueError('Invalid structured agent result JSON.')
    # Preserve a complete negative outcome when only the wrapper was omitted.
    # Never promote an incomplete success handoff or accept truncated JSON.
    if missing_close and (not isinstance(result,dict) or result.get('status') not in ('blocked','failed')):
        raise ValueError('Missing structured agent result closing tag; outcome is unverified.')
    if not isinstance(result,dict) or result.get('status') not in ('succeeded','blocked','failed'):
        raise ValueError('Invalid structured agent result status.')
    summary=result.get('summary'); details=result.get('details')
    if not isinstance(summary,str) or not summary.strip() or len(summary)>160 or '\n' in summary or '\r' in summary:
        raise ValueError('Agent summary must be one line of 1–160 characters.')
    if not isinstance(details,str): raise ValueError('Agent result details must be text.')
    return {**result,'summary':clean(summary.strip(),160)}

class Store:
    def __init__(self, root, demo=False, host=None):
        self.root = Path(root).resolve(); self.root.mkdir(parents=True, exist_ok=True)
        self.host = host
        self.demo = demo; self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root/'control.sqlite', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON'); self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL'); self.db.execute('PRAGMA journal_size_limit=4194304')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, title TEXT NOT NULL, prompt TEXT NOT NULL, status TEXT NOT NULL,
            created TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, workspace TEXT NOT NULL, acceptance TEXT NOT NULL, demo INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS steps(id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), position INTEGER NOT NULL,
            role TEXT NOT NULL, agent TEXT NOT NULL, host TEXT NOT NULL, status TEXT NOT NULL, output TEXT NOT NULL DEFAULT '',
            attempt TEXT, session TEXT, lease REAL, error TEXT, UNIQUE(task_id,position));
        CREATE TABLE IF NOT EXISTS events(sequence_number INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
            task_id TEXT, step_id TEXT, agent_type TEXT NOT NULL, host_id TEXT NOT NULL, native_session_id TEXT,
            timestamp_utc TEXT NOT NULL, event_type TEXT NOT NULL, status TEXT NOT NULL, input_summary TEXT NOT NULL,
            output_summary TEXT NOT NULL, artifact_references TEXT NOT NULL DEFAULT '[]', source_log_reference TEXT,
            UNIQUE(event_id));
        CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), ste…30563 tokens truncated…5219和所需输入。只能产生本地分支/待发布产物，不能离线更新 Windows 的 shared/latest 或项目目录册。
- 重连后先校验 repo、base commit、规则修订和输入 hashes，再导入候选提交；冲突需明确合并。既有 Windows 任务不复制重跑。
- 清理前确认 worktree 无活动租约、提交/产物已收到、dirty/untracked 文件已处理；使用 Git 原生命令管理 worktree。未同步内容和原生 agent 会话不自动删除。

## 8. 实施顺序与验收

A. 项目目录册与主机映射、启动自动上下文、路径与版本校验。任务从“填路径”变为“选项目”。
B. 自动 worktree 与独占写入租约、发布/合并队列；接上最新版本产物 UI。
C. 两个 CLI 的同一 MCP 接口与共享 Skill；文本 API 保留快照模式。

必须验证：
- ACC 与其他项目登记后，切换项目不能沿用前一个项目的备用目录。
- 两个 agent 并发编辑同一个相对文件，物理工作树不同；互写被拒绝。
- 规划、执行、审查读到匹配的 context revision 和固定输入版本；旧 handoff 不自动充当最新结果。
- Codex 与 Claude 都接收相同语义的目录规则；Claude 真正完成授权 MCP 读取，而不只是初始化成功。
- 路径穿越、Windows 大小写/盘符别名、symlink/junction 越界、过期租约、跨项目资源请求被拒绝。
- Windows 离线时，错误仓库、缺失 commit 或 Windows-only 数据阻止 Mac 启动；已有任务不重放。
- 大数据、归档日志和全部仓库不累积到 Mac；只有小快照和活动任务文件落地。
- agent 在 ACC 外运行与平台内受控执行被明确区分；不能将 Markdown 当文件权限隔离。

## 9. 官方资料与复用选择

- Git worktree： https://git-scm.com/docs/git-worktree
- Codex 项目指令： https://learn.chatgpt.com/docs/agent-configuration/agents-md
- Codex Skills： https://learn.chatgpt.com/docs/build-skills
- Claude 指令、AGENTS.md 与导入兼容： https://code.claude.com/docs/en/memory
- Claude Skills： https://code.claude.com/docs/en/skills
- Agent Skills 公共规范： https://agentskills.io/specification
- Codex MCP： https://developers.openai.com/codex/mcp/
- Claude MCP： https://code.claude.com/docs/en/mcp
- 官方 MCP Python SDK（MIT）： https://github.com/modelcontextprotocol/python-sdk

资料核查日期 2026-10-31。各机器实际安装版本和 ACC 限权启动参数仍需做能力测试；官方支持不等于当前 ACC 已接入。此次没有修改业务逻辑、运行 agent 任务、迁移目录或更改原生存储。
