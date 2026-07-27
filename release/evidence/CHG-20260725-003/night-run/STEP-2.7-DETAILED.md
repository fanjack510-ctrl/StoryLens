# StoryLens Cursor Prompt｜STEP 2.7 Windows 1.1.0 发布候选验证

```text
AMENDED BY CHG-20260726-004
```

```text
Amendment: Windows Smoke must use Free Native Overview (no VIP required).
RC may enable Feature Flag via test config. Provider must be configured.
Do not require activating VIP to enter native whole-book overview.
Still verify License system loads and future Pro capabilities remain protected.
Prerequisite: EFFECTIVE STEP 2.G6 PASSED UNDER CHG-20260726-004.
```

## 1. 任务标识

```text
STEP：2.7
阶段名称：Windows 发布候选验证
版本目标：StoryLens 1.1.0
候选标识：1.1.0-rc.1
Change ID：CHG-20260725-003 (+ entitlement CHG-20260726-004)
主轨道：I
协作轨道：A / C
审计轨道：D
前置门禁：EFFECTIVE STEP 2.G6 = PASSED UNDER CHG-20260726-004
目标门禁：STEP 2.G7
```

唯一目标：

> 在不正式发布、不修改正式版本治理状态的前提下，生成并验证本地 Windows 发布候选（含 Free 原生全书概览 Smoke）。

---

## 2. 权限边界

### 允许

* 使用项目现有构建脚本；
* 使用本地编译缓存；
* 创建项目内发布产物；
* 使用临时测试目录；
* 安装到安全测试位置；
* 运行 Sidecar；
* 使用测试数据库；
* 本地 Commit 修复构建 P0/P1。

### 禁止

* 安装全局新软件；
* 修改系统环境变量；
* 修改注册表；
* 修改全局 Git；
* 永久修改正式 VERSION；
* 创建 Tag；
* Push；
* GitHub Release；
* 自动 Updater 正式发布；
* verified。

---

## 3. 版本治理

正式仓库：

```text
VERSION 必须继续为 1.0.5
```

优先通过以下方式设置 RC 构建版本：

* 环境变量；
* 构建参数；
* Staging Manifest；
* 临时未提交文件；
* 项目现有 Release Override。

候选标识：

```text
1.1.0-rc.1
```

构建结束后必须确认：

```text
git status clean
VERSION = 1.0.5
```

如果构建工具只能通过永久 Commit VERSION 才能运行：

```text
VERSION_GOVERNANCE_BLOCKED
```

停止 Windows Gate，不得自行提交正式版本号。

---

## 4. 构建前检查

读取：

```text
gate-2g6.md
windows-release.yml
smoke_windows_release.ps1
Tauri 配置
Sidecar 配置
Updater 配置
Private Engine 打包配置
```

记录：

```text
Public HEAD
Private HEAD
Build Toolchain
Rust Version
Node Version
Python Runtime
Feature Flag
RC Version Method
Output Directory
```

不得修改全局工具链。

---

## 5. 发布候选内容

候选包必须包含：

* React 前端；
* Tauri；
* FastAPI Sidecar；
* Public Python 代码；
* 所需 Private Engine 运行组件；
* Migration；
* License；
* Provider 配置读取；
* Pro Native Overview UI；
* Evidence Deep Link。

候选包不得包含：

* 测试小说；
* Canonical Fixture 正文；
* `fixture-native-overview-v1` 默认产品入口；
* 测试数据库；
* API Key；
* 私人日志；
* Structure WIP；
* 无关 Lab；
* 开发截图；
* `.env`；
* 源码仓 Git 目录。

---

## 6. Private Engine 打包边界

检查：

* 正式 Engine 能被 Sidecar 加载；
* 缺失时返回明确错误；
* 不自动使用 Fixture；
* Private 不创建数据库；
* Private 不读取 Keyring；
* Private 不包含 API Key；
* Public/Private Contract Version 一致。

仅验证现有闭源交付边界。

不得声称实现绝对不可反编译。

---

## 7. 构建步骤

按项目已有流程执行：

1. Public 构建前检查；
2. Private 依赖准备；
3. Frontend Build；
4. Typecheck；
5. Backend Sidecar 打包；
6. Tauri Build；
7. Installer；
8. 产物 Hash；
9. 文件清单审计。

保存日志：

```text
release/evidence/CHG-20260725-003/night-run/windows-build-log.md
```

产物保存在项目已有 release 输出目录。

---

## 8. 安装测试环境

不得使用正式用户数据。

使用：

* 临时 Windows 用户数据目录；
* 测试用 `%LOCALAPPDATA%` 等价路径覆盖；
* 或项目已有 Smoke 隔离机制。

安装流程：

```text
卸载旧测试候选（仅测试安装）
→ 安装 RC
→ 首次启动
→ Sidecar 健康检查
→ 数据目录确认
→ 退出
→ 重启
```

不得卸载用户正式 StoryLens。

---

## 9. 1.0.5 升级 Smoke

在测试数据目录放置 1.0.5 数据库副本。

启动 RC：

* Migration 成功；
* 旧书存在；
* 旧章节存在；
* 旧单章结果存在；
* Reader Journey 存在；
* 新 Pro 表可用；
* 再次启动安全。

不得操作正式用户数据库。

---

## 10. Free Smoke

验证：

* 启动；
* 书库；
* 打开书；
* Chapter；
* Reader；
* 单章旧结果；
* Reader Journey；
* 章节聚合洞察；
* 设置；
* 删除保护；
* 原文件保护。

---

## 11. Free Native Overview Smoke + Pro Protection

### Free Native Overview Smoke（CHG-20260726-004）

* 无 VIP License；
* Feature Flag 使用 RC 测试配置开启；
* Provider 配置有效；
* Free 用户可进入「原生全书概览」；
* 可 Preflight / 创建 Run（或读取 G5 completed / Fake Transport）；
* Evidence 可跳转；
* 重启可读取；
* **不得**要求激活 VIP 才能进入原生全书概览。

### License / Future Pro Protection

* License 系统仍可加载；
* 未来 Pro Capability（如章节聚合洞察）无授权仍受保护；
* 不需要在 1.1.0 开发新 Pro 销售页。

### Provider

* 读取现有测试 Provider 配置；
* 不在日志输出 Key；
* 不永久修改默认配置。

如需要在安装包中重新执行 Live：

* 必须继续遵守 ¥9.00 夜间预算；
* 必须先查看费用台账；
* 不得为 Windows Smoke 无必要重复花费。

可以使用 Fake Transport 测试安装包流程，但必须明确：

```text
Windows execution smoke transport = fake
Live Provider correctness evidence = STEP 2.G5
```

不得把 Fake 当 Live。

---

## 12. Sidecar 验证

检查：

* 只监听 `127.0.0.1`；
* 自动分配端口；
* 健康检查；
* 无黑色控制台窗口；
* 端口冲突恢复；
* 退出后 Sidecar 终止；
* 重启后不残留旧进程；
* 数据路径正确；
* 日志不含秘密。

---

## 13. Updater 验证

本阶段只验证：

* Updater 初始化不阻断启动；
* 无签名或无网络时不崩溃；
* 检查更新失败不影响本地功能；
* 不发布更新清单；
* 不上传安装包；
* 不触发正式 Release。

---

## 14. 安装包审计

列出安装包或解包文件清单。

检查：

* 无测试数据库；
* 无测试小说；
* 无 API Key；
* 无 `.env`；
* 无用户绝对路径；
* 无 Structure WIP；
* 无不必要源码；
* 无 Git 元数据；
* 无 Fixture 默认入口；
* Private 组件存在；
* License 组件存在。

---

## 15. 退出和清理

验证：

* 应用退出；
* Sidecar 退出；
* 无孤儿进程；
* 测试临时目录可安全清理；
* 不清理用户正式目录；
* 不删除项目工作树；
* 不删除构建证据。

---

## 16. STEP 2.G7 通过条件

必须全部满足：

* [ ] STEP 2.G6 已通过；
* [ ] RC 版本不永久修改 VERSION；
* [ ] Frontend Build 成功；
* [ ] Typecheck 成功；
* [ ] Sidecar Build 成功；
* [ ] Tauri Build 成功；
* [ ] Installer 生成；
* [ ] 产物 Hash 已记录；
* [ ] 安装成功；
* [ ] 首次启动成功；
* [ ] Sidecar 健康检查成功；
* [ ] 1.0.5 数据库副本升级成功；
* [ ] Free Smoke 成功；
* [ ] License Smoke 成功；
* [ ] Pro Overview 读取成功；
* [ ] Evidence 跳转成功；
* [ ] 重启后结果存在；
* [ ] 退出后 Sidecar 清理；
* [ ] Updater 失败不阻断；
* [ ] 安装包不含测试资产；
* [ ] 不静默降级 Fixture；
* [ ] 无 P0；
* [ ] D-Audit = PASS；
* [ ] Public Integration clean；
* [ ] Private Integration clean；
* [ ] VERSION = 1.0.5；
* [ ] v1.0.5 未移动；
* [ ] release/1.0.5 未移动；
* [ ] Structure WIP 未变化；
* [ ] 未 Push；
* [ ] 未 Tag；
* [ ] 未 Release；
* [ ] 未 verified。

任意一项不满足：

```text
STEP 2.G7 = BLOCKED
```

不得进入自动正式发布。

---

## 17. Gate 报告

写入：

```text
release/evidence/CHG-20260725-003/night-run/gate-2g7.md
```

必须包含：

```text
RC Version
Version Override Method
Build Commands
Build Results
Installer Path
Installer Hash
Install Test
Migration Test
Free Smoke
Pro Smoke
Private Engine
Sidecar
Updater
Package Audit
P0/P1/P2
Public HEAD
Private HEAD
VERSION
Result
Next Step
```

下一步只能是：

```text
STEP 2.8 用户人工验收
```
