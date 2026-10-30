## 0.6：额度、默认模型与思考强度

侧栏「账户额度」按本机/远程主机分别显示 Codex、Claude 当前登录账户的额度和重置时间。读不到会显示原因，不会估算。API 服务商暂不提供统一余额读取。

「设置 → 默认智能体、模型与思考强度」可设置三个角色的默认智能体，以及两个 CLI 各自的模型和思考强度。新建任务时还能分别修改，留空则沿用 CLI 自身配置。Windows Worker 要重新部署 0.6 才能使用这些新功能，更新 Mac App 不会更新 Windows Worker。

## 0.5：中文界面和字体大小

已安装 0.4：打开 Settings → App updates → 检查更新 → 安装并重启，即可升级到 0.5，无需重新下载安装包。

升级后默认中文、115% 字号。顶部可切换「简体中文 / English」和字号，也可进入「设置 → 显示设置」。支持 100%、115%、130%、150%，重启后保留选择。任务原文、智能体输出和文件路径不翻译。

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
