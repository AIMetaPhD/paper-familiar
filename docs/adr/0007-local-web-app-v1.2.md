# ADR-002 — PaperFamiliar 采用 Local-first Web App

- 日期：2026-10-28
- 状态：**Accepted by product owner (architecture decision)**，尚待 Claude P0 验证具体实现。
- 替代：V1.1 的 Windows/macOS 原生客户端和双机实体 Gate 为强制要求的描述。

## 决策

**用浏览器充当唯一 UI，本机 FastAPI 进程处理文稿解析、审查、数据存储、AI 路由。** 本机默认打开 `http://127.0.0.1:8420`，不发行 `.exe/.app` GUI、Electron/Tauri、多套平台 UI。由 Python 包在运行时提供同源预构建的 React/Vite 静态文件；Node 仅开发/构建需要。

**最低可用部署**：安装 Python 发行包 → `paperfamiliar serve` → 浏览器访问 → 本地目录/SQLite 持久化 → 导入 `.tex/.bib/.zip` → 运行严格离线审核。`pipx`/`uv tool`、Docker Compose 都是安装路径而非必须采用的运行架构。

**跨平台含义**：宿主 OS 仍需可运行 Python（Python ABI、路径、文件权限需兼容）；浏览器渲染 UI 不因 OS 改写。单次 E2E 主验证 + Chromium/Firefox/WebKit 交互覆盖 + 代码级跨平台冒烟，是 V1.2 验收合同。**跨平台浏览器访问不等于后端在所有系统上未经测试也能运行。**

## 防止误读

- Local-first Web App != 纯静态网页/HTML 文件；服务关闭时网页没有完整业务能力。
- Local-first != 可以从公网访问。v0.1 默认仅 loopback；LAN 功能暂缓，并应有鉴权/TLS/限流。
- Browser-only UI != 文档自动上传 SaaS。所有用户原文默认仅本地处理；Cloud 逐次告知 payload 并批准后才送出。
- 离线能力 != 首次离线可完成互联网安装。下载依赖是 setup 阶段；完成安装后测试运行时零外联。
- Browser UI 可以调用本机 AI 服务，但模型服务并非必需；无模型时静态审查和结构图照常。
- Web App 不需要 PWA service worker；首版不做 PWA 安装到桌面/缓存全文 IndexedDB，避免脱敏和数据残留复杂化。

## 建议最小代码形态

```text
paper-familiar/
  backend/paperfamiliar/
    app.py                     # FastAPI: same-origin API + bundled static
    config.py                  # localhost bind / app_data_dir / providers
    storage.py                 # SQLite + local persisted workspace
    ingestion/                 # LaTeX/Bib/Zip safe parser + SourceSpan
    verification/              # deterministic checks + evidence gate
    style/                     # author voice & cognitive fingerprint
    providers/                 # offline/local/cloud consent gate
    cli.py                     # paperfamiliar serve | audit
    static/                    # included built frontend assets in release
  frontend/                    # React/TS/Vite source, Node at build time only
  tests/                       # pytest + Playwright + security
  fixtures/                    # entirely synthetic demo corpus
  qa/                          # Muse artifacts; no secrets/unpublished text
  pyproject.toml
  README.md
```

实际安装构建应使用经验证的 `pyproject.toml` wheel packaging 机制，证明 wheel 包含最新的 frontend dist；不得把开发环境的 `npm run dev` 当最终用户启动步骤。确保 API 返回合理错误，并给进程健康检查 `/api/health`；默认仅 `127.0.0.1`。

## 数据生命周期与端点安全

- SQLite 及上传/编辑记录存于明示用户数据目录，不将未发表全文写浏览器 localStorage/analytics。刷新和服务重启必须可恢复，删除 workspace 时删除关联版本、向量缓存、导出缓存与可见历史。
- 原文哈希只读不变，任何建议变更需用户明确审批、产生 diff（默认不写盘）。
- 本机 Web 后端仍面临恶意浏览器网页对 loopback 的跨源访问风险：需要 Host allowlist、Origin 校验、CSRF 防护和适当的本机会话/token；不使用 `Access-Control-Allow-Origin: *`，不允许 `0.0.0.0` 默认绑定。
- 避免浏览器 SSRF：用户自定义 AI endpoint 限制目标、二次确认；可访问公网的 compatible endpoint 按 Cloud 策略处理。
- 离线资产（字体、icon、Math renderer）全部内置；Network tab、服务器日志与出口观察证实无第三方请求。
- 运行时不动态下载模型、字体、JS bundle；无自动更新检查。安装/更新单独显式进行。

## 审批与退出标准

G1：本机服务可运行，桌面浏览器打开完整 UI，离线操作、持久化、关掉浏览器再恢复；同源静态资源；不用 OS 原生 GUI。G4：三大浏览器引擎 E2E + 离线/云 consent + 数据删除实测。G5：Muse 独立核验、用户签字。不同 OS 的兼容程度按已执行平台如实在 README 写明；不设置 Windows/macOS 原生客户端打包目标。
