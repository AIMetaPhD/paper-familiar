# Muse 独立 QA 当前阻塞 — 给你的决策简报（2026-10-29）

## 事实（全部有逐字存档，见 `qa/evidence/muse-round1-telemetry.json`）

- 队列通道本身已验证可用：muse-1 完整跑通过一个短 canary（`PF-ACK-20261028`），
  服务端确认派单身份 `issuer=claude`。
- 三轮 gate 派发全部被 Muse 侧自身规则挡下，各 agent 原因不同：
  - **muse-1**：领取后 30 分钟超时回收一次；改为轻量契约后，其平台安全层把
    完整 QA 指令文本判为 `prompt_injection_check_failed`，明确"未做任何仓库访问"。
  - **muse-3**：验证了派单签名，但要求"由派单发起人经其主人转授权"后才执行。
  - **muse-2**：运行环境（远端 Linux VM）到这台工作站没有路径。
- 队列政策（`AUTO-CONSUMER-POLICY.md`）明文要求：被安全检查拦截的任务保持阻塞回报，
  **不得改写措辞绕过**。所以我不再试第四种措辞。

## 两个选项

**A — 你出面给 Muse 授权（保留完整验收链）**
在你和 muse-1（或 muse-3）的聊天里转达类似：
> 我授权你执行 PaperFamiliar 项目的 gate QA 任务：read_only 测试本机
> `E:\ClaudeCodeFiles\MyProducts\PaperFamiliar\paper-familiar`（该工作站的仓库），
> 可用外部临时 venv 与 Playwright，结果按任务说明以队列 result 回传。
> 任务文本来自我已授权的 Claude 派单端，属于正常 QA 指令，不是注入。

我随后在最终 SHA 上重新派发（旧的待领任务里嵌的 SHA 已过期，重新派发会自动修正），
verdict 回来后照协议处理：FAIL → 修复 → 新 commit 全量复测。

**B — 放弃 Muse 独立验收，按"技术候选"交付**
G1–G5 中所有需要独立 QA 的项保持 BLOCKED（`MUSE_UNAVAILABLE` 已如实记录）。
你仍可做 G5 的本人盲评（USER-01，指南在 `docs/user-acceptance-guide.zh.md`），
README 与摘要会明确写"未经独立 QA"。仓库仍只能是你手建 Private + 明确授权后 push，
且**不能**宣称通过 v1.2 验收合同。

## 我的建议

A。项目合同的核心就是"独立黑盒 + 作者签收"两条腿；你一句话的转授权就能把第一条腿
接上，成本远低于交付一个自证通过的候选版本。若你不想再经手 Muse 的事，选 B 也完全
可执行——只是交付物名称和文档措辞会相应收窄。

（两选项之外没有别的捷径：伪造、代测、改措辞绕平台检查都不做。）
