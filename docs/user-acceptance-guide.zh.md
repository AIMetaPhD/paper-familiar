# G5 用户验收指南（作者本人盲评 + 本地熟悉度确认）

这一步只有你本人能做。Claude 与 Muse 都不能代签 `qa/user-acceptance.json`。
以下流程约 20–30 分钟，全部在本机完成，不需要联网。

## 准备

1. 安装并启动（任选一种已验证方式）：
   ```bash
   python -m venv .venv
   .venv\Scripts\python -m pip install dist/paperfamiliar-0.1.0-py3-none-any.whl
   .venv\Scripts\paperfamiliar serve
   ```
2. 浏览器打开 `http://127.0.0.1:8420`。

## 第一轮：先用 demo 校准预期（约 5 分钟）

- Load the offline demo → 确认点击 finding 能跳到正确文件/行/列；
- 导航器输入 `where is the optimization problem?` → 应命中 Problem Formulation；
- 输入一个不存在的话题 → 应明确 `not_found`；
- Style 页看 drift cards：4 篇合成旧论文、样本量与置信度都写着；
- Accept 一条、Export，确认导出目录里 5 个文件存在，且提示
  “Source hash unchanged after export.”

## 第二轮：你自己的真实论文（核心判断）

1. **上传 3–10 篇你本人主笔的旧论文**：Import → “My earlier papers”。
   每篇上传后点 “label sections”，把确实由你主笔的节标为 “I wrote it”，
   其余保持 Unknown / Coauthored（未标注的节不会进画像——这是特性）。
2. **上传当前待审稿**（新稿或在投的稿）：Import → “Paper to audit”，
   `.tex/.bib` 多选或直接选整个文件夹。
3. 按你最关心的三件事检验：
   - **可靠性**：Evidence 里每条 Verified error 是否真的能指回原文、
     且确实是错；有没有你觉得不该出现的误报。
   - **风格画像**：Style 页勾选你的旧论文后，drift cards 描述的差异
     是否符合你对自己写作的感觉；有没有把正常题材用语误当风格偏离。
   - **认知熟悉度（盲评关键）**：把中间源码栏当作唯一视图，用导航器和
     Paper Map 回答三个你自己定义的问题（例如 “P1 优化问题在哪节”、
     “某符号首次出现在哪”）。记录定位耗时与是否找对。然后合上工具，
     凭记忆在稿子里人工找到同一处，对比两种方式哪个更快更确定。
     这就是“秒接上下文”的 n=1 主观判断——没有统计显著性宣称，
     你的实际感受就是验收依据。
4. **导出给写作 Agent**：点 Export，把 `agent-feedback.json` +
   `author-style-guide.md` + `cognitive-structure-profile.json` 丢给你日常
   用的写作 Agent（Claude/Codex 均可），让它按约束先出 diff。看它是否
   能在不读全文的情况下用这些文件理解你的结构与文风。
5. 全程可随时关页面、重启服务再打开，确认工作区与决定都还在；
   最后用 **Data** 面板删除测试工作区（你导入路径型原始文件不会被删）。

## 签收

三项都符合预期（或你愿意接受的偏差）后，编辑 `qa/user-acceptance.json`
（模板 `qa/templates/user-acceptance.template.json`）：

- `decision` 改成 `APPROVED`（或 `DECLINED` 并说明原因）；
- `commit_sha` 填你测试时 `git rev-parse HEAD` 的值；
- `user_confirmation` 写一句你本人的话（≥20 字符），比如你实际测了什么、
  接受了哪些偏差；
- `blind_test_evidence_path` 指到你能找回去的一份记录（笔记/截图目录均可）；
- `public_release_authorized` **保持 false**（推送授权是另一回事，另行口头确认）。

然后运行 `python scripts/check_gates.py --root .`——若 Muse 五份 verdict 已
齐且全 VERIFIED，它应输出 exit 4（此前）→ 你签收后变 exit 0（合同完整）。
它只校验证据形状；最终判断仍然是你和 Muse 的。

## 你可以合理判不合格的情形（提前说明，省得将就）

- Verified error 出现你确认的误报，或引用跳转经常对不上行列；
- 画像把合作者/非主笔内容明显当作你的风格；
- 导出文件对你的写作 Agent 毫无可用信息；
- 数据面板删不干净、重启后状态丢失。

出现任何一条，告诉我具体复现步骤即可，我修完会请 Muse 在新 commit 全量复测。
