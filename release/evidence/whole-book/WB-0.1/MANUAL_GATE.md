MANUAL GATE：
MG-WB-0.1

对应 Step：
WB-0.1-BASELINE-FREEZE

对应 Change：
CHG-20260728-002

验收等级：
L1

验收目的：
确认 v1.1.1 基线、37 步编号、37 个 Gate、证据路径和保护规则已冻结。

验收环境：
只读文档与 Git 信息（本机 worktree）

是否真实 Provider：
NO

预计调用数：
0

最大调用数：
0

预计 Token：
0

费用上限：
0

正式数据库写入：
NO

构建：
NO

用户操作：
1. 核对 `release/evidence/whole-book/WB-0.1/BASELINE.json` 中完整 SHA；
2. 核对 `docs/whole-book/EXECUTION_REGISTRY.json` 含 37 steps / 37 changes / 37 gates；
3. 运行 `python scripts/verify_whole_book_execution_registry.py` 应为 PASS；
4. 核对 `docs/whole-book/PROTECTED_WORKTREES.md`：两棵脏 WIP 仅登记、未修改；
5. 核对状态规则：Cursor 不得自行 `verified`；
6. 核对 `git diff` / 提交仅文档与 registry，无业务源码、无 VERSION 变更。

预期结果：
- VERSION=1.1.1
- v1.1.1 Tag target = `38c85ab4eda0eaa03bd6a7bf8fda7d8deb11a5db`
- Public HEAD = `b2c6a89fa5b1be664120adfcaa7bb9dab514e3a3`（含 Tag）
- Private HEAD = `30d8dad8cd649e832999874f7bf16cc1661cf221`
- Registry verification PASS
- 无业务源码修改；保护 WIP 未触碰

禁止出现：
- 业务 FastAPI/React/Private 算法改动
- VERSION / Tag / Release 变更
- Provider 调用
- 正式 AppData 写入
- 自动开始 WB-0.2
- 修改两个 structure-empty-policy 脏工作树

PASS 标准：
用户明确回复：

```text
MG-WB-0.1：
PASS
CHG-20260728-002：
verified
允许进入：
WB-0.2-DATA-CONTRACTS
```

BLOCKED 标准：
编号冲突、基线 SHA 不符且未解释、缺 Gate、保护 WIP 被改、出现业务源码改动。

通过后允许进入：
WB-0.2-DATA-CONTRACTS（仅在用户批准后另开 Prompt）

失败后回到：
修订 WB-0.1 文档/Registry，重跑本 Gate

Evidence：
release/evidence/whole-book/WB-0.1/
