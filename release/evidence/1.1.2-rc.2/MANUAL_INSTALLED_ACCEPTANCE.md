# MANUAL INSTALLED ACCEPTANCE — StoryLens 1.1.2-rc.2

## Status

PENDING — automated install-state PASS; awaiting human install of **RC.2 only**  
(do **not** overwrite a formal production install unless explicitly approved).

## Installer

- Path: `D:\Dstorylens-wt-hotfix-1.1.2-integration\dist\release\StoryLens_1.1.2-rc.2_x64-setup.exe`
- Safe copy: `D:\StoryLens-Local-Evidence\installer-archive\StoryLens_1.1.2-rc.2_x64-setup.exe`
- SHA-256: `CBE975E097E24A7DD5452C3B2B3BCB93DD75AFAED8B857EEF297B4C05FF94959`

## Must prove (CHG-009)

1. Settings → AI：配置阿里云百炼 / qwen3.7-plus，点击「重新验证」成功。
2. **立即**打开章节分析弹窗，选择「均衡·推荐」。
3. 健康状态 fresh；**无需**点「刷新状态」。
4. 点击开始：**不**返回 HTTP 409 `PROVIDER_HEALTH_STALE`；成功创建 Analysis Run。

## Constraints

- Prefer isolated / Fake validation where possible for engineering retests.
- Do not call real Provider unless the human acceptor explicitly chooses to.
- Do not write to / replace formal AppData DB as part of automated gates (already 0).
