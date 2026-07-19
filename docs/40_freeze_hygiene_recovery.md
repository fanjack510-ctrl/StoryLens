# docs/40｜Freeze Hygiene Recovery（Phase 1C-C.2.5.2-Hygiene）

**性质：** 冻结基线卫生修复。不开发 UI 功能；不改 Manifest 旧哈希；不改 v1/v2 thaw；不写库。

## 1. CRLF-only 恢复

审计来源：`frozen-drift-audit-2.5.2.json` 中 `line_ending_only=true` 的 12 个路径。

每个文件：仅当 raw≠baseline 且 LF 归一 SHA==baseline 时写回 LF 字节；BOM/可见字符不变。

恢复后 raw SHA 全部等于 `core-freeze-manifest.json` baseline。

## 2. 防再发 CRLF

新增根目录 `.editorconfig`（`end_of_line = lf`）。  
当前不是 Git 仓库，**不能**声称 `.gitattributes` 已生效；未来迁 Git 后再加。

## 3. Thaw v2-2

新增 `ui-presentation-thaw-v2-2.json`：

- 批准 Phase 点击：set activePhase / 高亮区间 / 显示 Phase Inspector
- 禁止：自动改 activeScene、改 Scene 点击、Scroll Spy、Evidence、URL scene、第二套选择状态
- 仅 `ReaderJourneyWorkspace.tsx` + `ReaderJourneySyncWorkspace.tsx`

`check_core_freeze` / `check_ui_presentation_thaw` 默认叠加 **v1+v2+v2-2**；禁止 thaw 列入 FROZEN_CORE/CONTRACT。

## 4. `_readonly_audit.py`

原副作用：默认写死 `database-baseline.json`。  
现行为：默认 **零文件写入**（stdout）；`--output` 写新文件；已存在需 `--overwrite`。SQLite 仍只读 URI。

旁路记录：此前审计曾刷新 `database-baseline.json` 元数据；本阶段不猜测/回滚其历史内容。

## 5. Freeze 门禁

仍以 **raw SHA** 为最终 FAIL 条件。可打印 normalized-LF 提示，但不得静默接受换行漂移。

## 6. 已知非本阶段问题（只报告）

Books 嵌入路由上，Rhythm/Curve 点击会写入 `inspector` URL；与 `useJourneySelection` 的 `scene` 写入存在竞态时，可能用旧 `scene` 覆盖。Hygiene **不修复**该 UI 竞态（禁止功能改动）。E2E 改用 `structured-scene-header-*` 验证 Scene 选择语义。

## 7. 验证结果（本阶段实测）

| 门禁 | 结果 |
|------|------|
| check_core_freeze | PASS（CORE/CONTRACT modified=0） |
| check_ui_presentation_thaw | PASS（含 v1+v2+v2-2） |
| pytest | 279 passed |
| ruff | All checks passed |
| typecheck / lint | PASS |
| vitest | 205 passed |
| e2e | 34 passed |
| build | PASS |
| SQLite integrity / FK | ok / [] |
| `_readonly_audit` 默认 | 零写入；baseline JSON 与 DB SHA/mtime 不变 |
| 模型 / 新 Run | 0 |

**是否允许继续 UI 开发：** 是（在既有 thaw 白名单内）。
