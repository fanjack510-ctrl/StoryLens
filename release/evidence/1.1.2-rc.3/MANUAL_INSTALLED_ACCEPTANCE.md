# MANUAL INSTALLED ACCEPTANCE — StoryLens 1.1.2-rc.3

Installer:
`D:\Dstorylens-wt-hotfix-1.1.2-integration\dist\release\StoryLens_1.1.2-rc.3_x64-setup.exe`

Safe archive:
`D:\StoryLens-Local-Evidence\installer-archive\StoryLens_1.1.2-rc.3_x64-setup.exe`

Automated install-state: PASS (CWD 6/6, health, security, isolated Fake Provider).  
本清单供人工安装验收；自动化步骤不会覆盖正式安装。

## Checklist

1. 安装 RC.3（建议隔离目录或明确测试机；勿与正式 Stable 混淆）。
2. UI / 产品版本显示 `1.1.2-rc.3`。
3. Provider：验证成功后一分钟内启动分析不出现 PROVIDER_HEALTH_STALE。
4. 旅程 interrupted：仅显示已中断，不同时显示正在生成。
5. Revision 确认 6：各页只显示 S01–S06，无重复、无内部 Scene ID。
6. 待确认：仅“确认场景”；无阅读旅程入口；无场景分析顶栏。
7. 确认后直接进入旅程进度（无“尚未开始”中间页）。
8. 钩子 Rich：一句总判断 + 1–3 问题卡 + 悬念轨迹 + 洞察；无重复说明。
9. 钩子 Empty：简洁空状态。
10. 任务停止：stopping → cancelled；不显示为失败；停止后无新 Provider 调用。
11. 刷新与 API 重启后状态保持。
