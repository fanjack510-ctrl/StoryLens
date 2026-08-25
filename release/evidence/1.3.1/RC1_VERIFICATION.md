# StoryLens 1.3.1 RC1 验证记录

- 候选提交：`95e046a2`
- 基础版本：`1.3.0`
- 目标版本：`1.3.1`
- 验证日期：2026-08-25

## 自动验证

- 后端发布关键路径：118 passed
- 前端发布关键路径：最终 104 项通过（首次运行 103 passed / 1 个旧断言失败；断言按“激活成功必须有提示、正式 Pro 共 5 项能力”修正后，相关文件 8 passed）
- TypeScript typecheck：通过
- `scripts/check_project.py`：通过
- `scripts/license/check_license_release_config.py`：通过
- 变更登记隔离测试：17 passed

## 人工验收

本轮知识库、场景边界编辑、长短篇入口、书库主页、Pro 授权与读者旅程等页面已经过连续人工查看；对应截图保存在 `release/evidence/takeover/`。

## 发布安全审计

- 暂存内容未发现私钥、生产授权码、GitHub Token、云厂商 API Key。
- 生产授权配置只包含 Ed25519 公钥和爱发电商品地址。
- 本机 `.env` 被 `.gitignore` 排除，未进入提交。
- 本地 1017 本参考小说的扫描索引包含本机来源路径，已整体排除；小说原文未进入提交。
- 授权私钥、100 个授权码及发行台账均位于仓库外，未进入提交。
- 数据库、日志、安装包、sidecar 和用户上传文件均由既有忽略规则排除。

## 非阻断说明

- Pytest 报告一个 Starlette/httpx 弃用警告。
- 当前工作区的 pytest cache 目录不可写，产生缓存警告；测试本身通过，且该目录不进入版本库。
