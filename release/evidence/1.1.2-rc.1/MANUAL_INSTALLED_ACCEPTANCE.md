# MANUAL INSTALLED ACCEPTANCE — StoryLens 1.1.2-rc.1

Installer:
`D:\Dstorylens-wt-hotfix-1.1.2-integration\dist\release\StoryLens_1.1.2-rc.1_x64-setup.exe`

SHA-256: `2C9ED3B8E898118391B56F7A297F96B9CFB8A9951C1226C851C5B7C1AEF1F61F`

本步骤**不会**自动安装。正式 AppData / 已安装 GUI / Sidecar 在您手动安装前保持不动。

## Mode A — Fresh install

1. 如需干净态验收：完全卸载 StoryLens，并删除 `%LOCALAPPDATA%\StoryLens`。
2. 安装上述 RC1 安装包。
3. 确认 UI / 产品版本显示 `1.1.2-rc.1`。
4. 确认本地服务 health 正常；Provider 配置可加载。
5. 确认默认 API Key 为空。
6. 导入 TXT / DOCX / EPUB smoke（无需 Provider）。
7. 确认单章入口可用；全书 / Native Overview / 独立 Journey 入口保持隐藏。
8. 确认 Sidecar 从安装目录启动；日志中 V2 config `source=bundled`。
9. 抽查 hotfix 能力（无需 Real Provider 也可看 UI）：
   - 任务中心存在「停止分析」；
   - 阅读旅程维度洞察 / 阶段颜色 / 综合阅读节点 / 钩子简化文案；
   - 场景边界人工校正入口（若有既有场景结果）。

## Mode B — Upgrade from v1.1.1 data（可选）

1. 使用 v1.1.1 用户数据副本或明确测试库（勿默认写正式库，除非您明确允许）。
2. 打开既有 Journey / 场景结果，不自动触发 Provider。
3. 确认迁移后旧书、章节、场景、旅程、Usage 可读。
4. 确认取消字段与边界 revision 字段可用。

完成后回复 `PASS` / `FAIL`。仅在 PASS 后可将 CHG-20260729-008 标为 `verified`，并进入正式 1.1.2 发布授权。
