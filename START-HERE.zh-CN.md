## 0.4 起可在 App 内更新

旧版先退出，再覆盖安装 0.4.0 一次；无需删除旧 App 或任务数据。之后打开 Settings → App updates → 检查更新 → 安装并重启。

有运行中、排队中或待排查的任务时先处理任务；远程状态未知时先重连。更新包会校验签名，失败可重试。更新包含 Mac App 及其内置后端，不会自动更新单独部署的 Windows Worker。

# Agent Control Center 0.3

## 安装

Apple Silicon Mac：双击 `.pkg`，按向导安装，然后从 Applications 打开。无需用 Terminal 或 Python 启动。此预览版尚未 Apple 公证；若 macOS 拦截，请在“隐私与安全”中确认打开。

## 开始使用

- 新安装默认“本机”，不需要第二台电脑。已有的 Windows 优先配置会保留。
- 右上角可选择白底黑字、黑底白字、黑底蓝色主题，选择会保存。
- 使用已登录的 Codex CLI／Claude Code，或在 Providers 配置 DeepSeek、Ollama、兼容 Chat Completions 的接口。
- API Key 可以在界面临时输入，仅保留到当前后台关闭；不会写入配置文件。
- New task → 填目标、执行机器上的工作目录、验收标准 → 选择三个角色的 agent → Create → Run。
- 查看结果后手动 Accept。需要零模型费用演示时，右上角切换 Demo。

## 添加其他环境

Settings → SSH environment → 填系统类型、SSH 别名、远程 Python、service.py 和存储路径 → 保存 profile → 从右上角选择。每个环境使用独立数据；不会自动搬迁工程或任务。远端需部署当前版本的 backend 目录。详细 Windows/Linux/macOS 操作见 README。

当前可以保存并切换多个环境，不是同时调度任意数量的 worker。CLI 为只读／无工具模式；API 是文本模型，不具备文件和命令工具。真实付费 API、Windows 跨机执行与原生 GUI 交互仍需实测；不要把编译通过当成这些能力已经验证。
