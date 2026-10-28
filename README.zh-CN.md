# PaperFamiliar 中文说明

**核对研究，保留作者的声音。**

PaperFamiliar 是一个 **Local-first 本地网页应用**（v1.2 架构）：本机启动一个
Python/FastAPI 服务，浏览器打开 `http://127.0.0.1:8420` 即是完整产品。数据、
审查状态与作者画像都保存在本机目录。不安装任何 Windows/macOS 图形客户端，无
Electron、无 Docker 要求、无账户、无遥测、无 CDN。

核心承诺：

- 只展示能指回原文的证据：每条 finding 必须逐字命中不可变源文件的引用门禁。
- 原文永远只读；导入、审查、导出不改变任何字节（导出后会重新校验哈希并报告）。
- 风格差异只做描述，不打分、不判对错；样本不足时明确弃权，绝不输出伪置信度。
- 默认完全离线；云端 AI 必须逐次预览实际 payload 并明确确认后才发送。

## 运行

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -e .     # Windows
.venv/bin/python -m pip install -e .         # macOS / Linux
.venv\Scripts\paperfamiliar serve            # 自动打开 http://127.0.0.1:8420
```

或安装 wheel 后直接 `paperfamiliar serve`。运行时不需要 Node、Docker、TeX。
端口被占用时给出明确报错并退出，不会偷偷换绑到其他地址。

## 使用路径

1. **Load the offline demo**：四篇合成"作者旧论文" + 一篇带植入缺陷的合成新稿。
2. 右栏 Evidence ledger：区分 *Verified error*（机械可证）与 *Candidate*
   （启发式候选，需要你判断）。
3. 点击 finding → 中栏跳到精确 文件:行:列 并高亮引文；Paper Map、导航器、
   结构芯片全部支持同一跳转。
4. **Familiarity navigator**：输入 `where is the optimization problem?` 能定位
   Problem Formulation；找不到就返回 `not_found`，不编造位置。
5. **Style 页**：勾选哪些旧论文属于你、逐节标注贡献（只有 "I wrote it" 进入
   画像），得到带样本量和置信度的 Drift Cards；旧论文不足 3 篇时诚实弃权。
6. Accept/Dismiss 后 **Export**：`report.json`、`report.md`、
   `agent-feedback.json`、`author-style-guide.md`、
   `cognitive-structure-profile.json`，默认不含全文。
7. 刷新页面、关闭浏览器、重启服务后，工作区与审查决定都在（SQLite）；
   **Data** 面板可删除任意工作区或清空全部本机数据。删除上传型工作区会删除
   数据目录内的副本；路径导入型只解除登记，绝不动你的原始文件。

## v0.1 不做什么

查重、AI 文本检测、Turnitin 类服务、论断真伪证明、定理证明、docx/OCR/PDF
编辑、自动改写、自动投稿、TeX 编译（任何情况下都不编译上传的 TeX）、
局域网/公网监听、"xx% 像作者"式伪分数。

## 状态与验收（2026-10-28）

**v0.1 技术候选版本**。全部单测 + 三引擎（Chromium/Firefox/WebKit）浏览器 E2E
在本机（Windows 11 x64）自测通过；G1–G5 独立验收尚未完成：Muse 通道已探测可用
（muse-1 成功回执），但独立 verdict 尚未产生；作者本人盲评签收（USER-01）保留给
用户。macOS / Linux 宿主为 `UNTESTED_PLATFORM`（同一代码路径，未跑过就写未跑过）；
真实云 API 为 `UNTESTED_CLOUD_REAL`（consent 流程用 mock endpoint 验证）。
未创建远端仓库、未推送、未发布。

验收治理：`04_ACCEPTANCE_MATRIX.csv`、`schemas/`、`qa/`、
`scripts/check_gates.py`、`docs/adr/0005`。安全模型见
`docs/threat-model.md` 与 `SECURITY.md`。

## 许可

MIT。第三方声明见 `THIRD_PARTY_NOTICES.md`；`academic-refchecker` 因引入 GPL
传递依赖而不随本项目分发。
