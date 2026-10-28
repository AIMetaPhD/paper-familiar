# PaperFamiliar

**核对研究，保留作者的声音。**

PaperFamiliar 是本地优先、LaTeX 优先的论文工作台。它只展示能够指回原文的证据：机械可判定的引用错误、诚实的文献元数据，以及对你写作习惯的描述。它不修改原稿、不编译 TeX，也不会在你没有明确选择时联网。

- 无账户、无 API Key、无遥测、无 CDN。
- 每条结论都必须能在不可变源文件中逐字复现引用位置。
- 风格差异只被描述，不被打分，也不会被当成学术错误。

## 当前状态（2026-10-28）

这是 **v0.1 技术候选版本**，不是已验收发布。

| 项目 | 状态 |
|---|---|
| Windows 11 x64 自测 | 本机通过（原生启动、演示、审计、导出） |
| macOS Apple Silicon | **未运行**，开发会话无法访问 Mac；`BLOCKED_PLATFORM_UNTESTED` |
| Muse 独立 QA（G1–G5） | 未完成；通道已验证，裁决待回传 |
| 用户盲测签收（G5） | 尚未请求 |
| 推送 | 未推送；仓库仅在本地 |

## 运行

Windows PowerShell：

```powershell
.\scripts\start-windows.ps1
```

macOS：

```bash
./scripts/start-macos.sh
```

首次运行需要网络安装依赖；之后可运行 `python scripts/build_wheelhouse.py` 建立离线 wheelhouse。最终用户不需要 Node、Docker、WSL 或 TeX 发行版。

## 能做什么

- 解析多文件 `.tex` 与 `.bib`，给出精确的文件、行、列位置，支持 CRLF 与 Unicode。
- 检出未定义引用、未定义 `\ref`、重复 `\label`、BibTeX 缺字段、越界 `\input`。
- 以 `candidate` 标注一个保守的符号启发式，并明确其局限。
- 无模型生成章节树、环境序列、标签拓扑与符号索引。
- 只使用“本人主笔且已批准”的散文建立可解释的风格画像；样本不足时明确弃权。
- 导出 `report.json`、`report.md`、`agent-feedback.json`、`author-style-guide.md`、`cognitive-structure-profile.json`，默认不含全文。

## 明确不做

查重、AI 文本检测、Turnitin 类服务、论断真伪证明、docx/OCR、自动改写、自动投稿、TeX 编译。

## 安全

仅监听 `127.0.0.1`；校验 `Host` 与 CSRF；ZIP 导入拒绝路径穿越、符号链接、特殊文件与压缩炸弹；`\input` 不得越出工作区；所有结论必须通过逐字引用门禁。详见 `docs/threat-model.md`、`SECURITY.md`。

## 许可

MIT。第三方声明见 `THIRD_PARTY_NOTICES.md`。`academic-refchecker` 会引入 GPL 传递依赖，因此不随本项目分发。
