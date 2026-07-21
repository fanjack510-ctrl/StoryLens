# StoryLens 版本管理与发布

## 1. 唯一版本源

仓库根目录的 `VERSION` 是**唯一版本真相来源**。

- 只写合法 SemVer（例如 `1.0.1`）
- 不要写 `v` 前缀
- 不要附加说明文字

所有发布相关脚本必须以 `VERSION` 为准，通过：

```bash
python scripts/version_manager.py sync
```

同步到 Tauri / Cargo / npm / FastAPI / updater 模板等受控文件。

## 2. 日常开发不自动升版

功能开发、UI 打磨、缺陷修复**默认不改版本**。

只有在准备正式发布时才执行 `bump`。

当前仓库版本：

```text
1.0.1
```

## 3. patch / minor / major 规则

| 级别 | 命令 | 示例 | 何时使用 |
|------|------|------|----------|
| patch | `python scripts/version_manager.py bump patch` | `1.0.1` → `1.0.2` | 缺陷修复、小改进、不破坏兼容 |
| minor | `python scripts/version_manager.py bump minor` | `1.0.2` → `1.1.0` | 向后兼容的功能增量 |
| major | `python scripts/version_manager.py bump major` | `1.1.0` → `2.0.0` | 不兼容变更或重大产品线切换 |

也可显式设置：

```bash
python scripts/version_manager.py set 1.2.0
```

拒绝：非法 SemVer、空版本、`v1.2.0`、`1.2`、版本倒退、与当前相同（正式流程）。

特殊恢复才允许：

```bash
python scripts/version_manager.py set 1.0.0 --allow-downgrade
python scripts/version_manager.py set 1.0.1 --allow-same
```

## 4. 从 1.0.1 发布到 1.0.2

完成本轮功能修改并准备发布时：

```bash
python scripts/version_manager.py check
python scripts/version_manager.py bump patch
python scripts/version_manager.py check
```

预期：`1.0.1` → `1.0.2`，并同步所有受控文件。

然后执行正式 Windows release 脚本（会自动再次 `check` + `release-guard`）。

查看下一版本推导（发布 Prompt 不要手写死版本）：

```bash
python scripts/version_manager.py release-info
```

## 5. 发布前检查

至少执行：

```bash
python scripts/version_manager.py check
python scripts/version_manager.py release-guard
python scripts/check_project.py
```

`check_project.py` 已内置调用 `version_manager.py check`。

正式构建脚本 `scripts/build_windows_release.ps1` 在开始前必须通过版本门禁；不一致则停止。

## 6. updater 与安装包版本同步

- 模板：`packaging/updater/latest.json.template`（使用 `{{VERSION}}` 占位，不写死具体版本）
- 安装包命名：`StoryLens_<VERSION>_x64-setup.exe`（由 `release-info` 给出）
- Git tag：`v<VERSION>`
- `latest.json` / updater bundle / `.sig` 中的版本必须与 `VERSION` 一致

生成发布产物后可用：

```powershell
./scripts/check_release_artifacts.ps1
```

## 7. 版本回滚原则

- **不要**用 Windows 已安装版本反推源码版本
- 已安装版本只用于升级验收
- 若必须回退源码版本号，使用 `--allow-downgrade`，并单独记录原因；普通发布禁止使用
- 回滚已发布安装包属于运维操作，不是 `bump` 的逆过程

## 8. 禁止重新生成 updater 密钥

发布或升版时：

- **禁止**重新生成 updater 密钥对
- 公钥继续使用 `tauri.conf.json` 中已提交的值
- 私钥仅存本机 / CI Secret，禁止提交

详见 `docs/windows-desktop-updater-keys.md`。

## 9. 预发布版本

合法 SemVer 预发布（如 `1.1.0-rc.1`）可通过 `set` 写入，但仍需：

1. `check` 全量一致
2. 标签使用 `v1.1.0-rc.1`
3. 正式 GA 再 `set 1.1.0` 或从 rc bump 到正式号（按发布计划）

历史文档 / audits / 测试 fixture 中的旧版本字符串允许保留；门禁使用白名单，不做全仓粗暴替换。

## 10. 修复版本不一致

```bash
# 查看各文件实际值
python scripts/version_manager.py show

# 以 VERSION 为准写回受控文件
python scripts/version_manager.py sync

# 再校验
python scripts/version_manager.py check
```

若 `VERSION` 本身错了，先 `set` 到正确值，再 `check`。

常用命令速查：

```bash
python scripts/version_manager.py show
python scripts/version_manager.py check
python scripts/version_manager.py sync
python scripts/version_manager.py bump patch|minor|major
python scripts/version_manager.py set <version>
python scripts/version_manager.py release-info
python scripts/version_manager.py release-guard [--artifacts-dir dist/release]
```
