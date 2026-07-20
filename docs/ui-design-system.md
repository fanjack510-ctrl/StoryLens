# StoryLens UI 设计系统（阶段 1）

视觉定位：沉静、专业、适合长时间阅读与分析的桌面写作研究工具。墨绿色品牌，浅色/深色清晰层级，内容优先。

## 1. 原有样式入口

| 入口 | 说明 |
|------|------|
| `apps/desktop/src/main.tsx` | 引入顺序：`tokens.css` → `base.css` → `global.css` → `components.css` |
| `apps/desktop/src/styles/global.css` | 历史页面布局与业务专用样式；`.app` 上挂载遗留别名 `--bg/--surface/--accent` 等 |
| `apps/desktop/src/components/readerJourney/*.css` | Reader Journey 专用（本阶段不改结构） |
| `apps/desktop/src/components/chapterResult/*.css` / `chapterAnalysis/*.css` | 结果与分析面板专用 |

原先几乎无独立 token 文件，色彩与字号散落在 `global.css` 的 `.app` 与局部硬编码中。

## 2. 新增 token

- `apps/desktop/src/styles/tokens.css`：字体、字号、行高、字重、间距、圆角、浅/深色语义色、轻阴影、控件高度
- `apps/desktop/src/styles/base.css`：`box-sizing`、body UI 字体、标题语义字号、focus-visible、selection、滚动条；**明确保护** `.prose` / `.reader h1` 使用 `--font-reading`
- `apps/desktop/src/styles/components.css`：Button / Field / Switch / Badge / Card / Tabs / Dialog / Table / StateView 的共享视觉

遗留变量映射（`.app`）：`--bg`→`--color-bg-app`，`--surface`→`--color-bg-surface`，`--accent`→`--color-brand`，其余同理。

## 3. 基础组件映射

| 规范 | 实现 |
|------|------|
| Button | `components/ui/Button.tsx` + `.primary/.secondary/.ghost/.danger-btn` |
| Input / Textarea / Select | `components/ui/Input.tsx` + `.sl-input` 等；表单容器内原生控件统一外观 |
| Checkbox / Radio / Switch | `components/ui/Checkbox.tsx`；设置页继续用 `.settings-switch` / `.consent` |
| Badge | `components/ui/Badge.tsx` + `common/States.tsx` 的 `Badge` 兼容层 |
| Dialog | `components/ui/Dialog.tsx`（标准外壳）；复杂分析弹窗暂不强制迁移 |
| StateView | `components/ui/StateView.tsx`；`Loading` / `Empty` / `ErrorState` 复用 |
| PageHeader 等 | `components/ui/PageHeader.tsx`（低风险试用，未全站替换） |

## 4. 深浅色变量

- 浅色：`--color-bg-app #f5f5f1` … 品牌 `--color-brand #2f6b57`
- 深色：挂在 `.app[data-theme="dark"]` / `[data-theme="dark"]`；表面与页面背景可区分，输入框使用 surface 而非白底
- AppShell `data-theme` 驱动；启动页可挂 `data-theme="light"` 以保证 token 可用

## 5. 后续页面改造规范

1. 新增/修改样式优先用 token，禁止再引入 Inter 或网络字体。
2. UI 文案用 `--font-ui`；小说正文仅 `.prose` / 阅读区用 `--font-reading`；Provider/模型 ID 用 `--font-mono`。
3. 用共享组件 class，避免无边界的 `button {}` / `input { width:100% }` / `* { color }`。
4. 普通卡片以边框为主，不用重阴影；圆角不超过 `--radius-lg`（对话框 `--radius-dialog`）。
5. 复杂页（工作台三栏、Journey 图表、Boundary Review、Tasks 列、Onboarding 结构、Library 卡片）本阶段结构冻结，后续分阶段换肤。
6. 不得删除 `data-testid`、不得改路由/API/Provider/consent 业务逻辑。
7. 全局 CSS 若导致超过约 20 张审计截图明显位移，应缩小选择器范围后重试。
