# Agent Control Center 0.2 安装版

适用：Apple Silicon Mac。

1. 双击 Agent-Control-Center-0.2.0-arm64.pkg，按安装向导安装到 Applications。
2. 从 Applications 双击打开。无需 Terminal、Python、Node 或 Rust。
3. 如 macOS 提示开发者无法验证，在系统设置 → 隐私与安全中确认打开本应用。本版没有 Apple Developer ID 签名或公证。
4. 已保存的 Live 配置会自动连接。首次使用可先运行 Demo，再到 Settings 配置 my-worker。

Windows 执行服务仍需要 Windows 上的 Python 3.11+ 和相应 Agent CLI。你的 Windows 部署可继续使用，不需要重复部署。Mac 的 Codex/Claude CLI 和登录状态也仍需保留。

本版内置后台运行时，修复 Finder 启动时的常见 CLI 路径问题。Windows 连接失败会显示具体错误并提供 Reconnect Windows。安装完成不代表真实跨机链路已验证。

已验证：20 项单元测试、JSON 演示流程、原生编译。打包后台及安装包的验证结果见发布说明。
