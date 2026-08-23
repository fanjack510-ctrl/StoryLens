# 素材库融合 · 给并行会话的交接说明

两个会话同时在同一个工作区里改代码。这份文件的作用是把边界划死，
让我们不会改到同一个文件——那是并行开发唯一真正会出事的地方。

**你负责**：把 `D:\10010 五代十国\00-小说工作\novel-material-lab` 的引擎搬进 StoryLens。
**我负责**：其余全部（存储、构建、验收里报出来的界面问题）。

---

## 一、先读这两份

- `novel-material-lab/docs/FEATURE_SUMMARY.md` —— 那个项目做了什么
- `novel-material-lab/docs/DATA_MODEL.md` —— 它的 31 张表

已经量过的耦合情况（不用重新量）：

| 模块 | 行数 | 依赖 | 处置 |
|---|---|---|---|
| `lexicon.py` 本体词典/同义折叠/量词 | 294 | **零项目依赖** | 整块搬 |
| `genre_templates.py` 10 类型 · 97 类目 | 482 | **零项目依赖** | 整块搬 |
| `atoms.py` 9 类 Story Atom 抽取 | 240 | 只依赖 lexicon | 整块搬 |
| `materials.py` 创作抽象 / corePattern | 358 | atoms + templates + lexicon | 整块搬 |
| `quality.py` 10 项质量评分 | 161 | lexicon + dedup 纯函数 | 整块搬 |
| `textseg.py` 章节/场景切分 · 超长再切 | 270 | 只依赖 lexicon | 整块搬 |
| `dedup.py` 三级去重 | 161 | 相似度纯函数 + **持久化绑 db** | 只搬纯函数那半边 |
| `db.py` / `api.py` / `pipeline.py` 等 | 1,940 | — | **不搬**，按 StoryLens 的结构重写 |

约 1,800 行纯逻辑可以原样搬，而它正好是那个项目全部的独到之处。
45 个端点、31 张表、13 个页面**不要原样移植**——那等于在 StoryLens 里塞进第二个应用。

---

## 二、文件所有权（这一段最重要）

### 只有你能碰

```
apps/api/app/narrative_core/material_lab/        ← 新目录，引擎搬进这里
apps/api/app/db/material_lab_models.py           ← 新文件，你的表定义
apps/api/app/routers/material_lab_router.py      ← 新文件
apps/api/tests/test_material_lab*.py             ← 新文件
apps/desktop/src/pages/MaterialLabPage.tsx       ← 新文件
apps/desktop/src/services/materialLabApi.ts      ← 新文件
```

### 只有我能碰（你改了会冲突）

```
apps/desktop/src/pages/LibraryPage.tsx
apps/desktop/src/styles/global.css
apps/desktop/src/styles/components.css
apps/desktop/src/pages/BookRoutePage.tsx
apps/api/app/services/library_listing.py
```

### 需要同时改的三处 —— 每处只加一行，加完立刻提交

1. `apps/api/app/db/models.py` —— **不要在这里加表**。
   新建 `app/db/material_lab_models.py`，`from app.db.models import Base` 复用同一个 Base，
   表定义全写在你的新文件里。models.py 已经 52 张表，再加会变成冲突热点。

2. `apps/api/app/main.py` —— 挂路由。照抄现有写法，加两行：
   ```python
   from app.routers.material_lab_router import router as material_lab_router
   # ...
   app.include_router(material_lab_router)
   ```

3. `apps/api/app/narrative_core/migrations/` —— 迁移。
   **你的编号是 `20260823_025_material_lab`**（024 是书单，我已占用）。
   照 024 的写法：`__init__.py` 加常量、`runner.py` 加函数并在顺序表里追加。
   建表用 `_table_names(engine)` 判幂等，不是 `_column_names`。

---

## 三、接口在哪儿

```
导入 → 编码识别 → Chapter → Paragraph  │  场景切分 → Story Atom → 创作资料 → 模式簇
      ↑ StoryLens 已有，直接用          │  ↑ 你搬进来的
```

`Chapter` 和 `Paragraph` 是**导入产物**，正好是 `textseg` 场景切分要的输入。

**一个必须绕开的坑**：StoryLens 的 `Scene` 表绑在 `created_by_run_id` 上——
它是**分析产物**，不是解析产物。素材库不能复用这张表，需要自己的场景概念，
或者直接按章处理。这一条没看出来的话，会在实现到一半时才发现表建不出来。

新增的表 4–5 张就够：`story_atom` / `material` / `pattern_cluster` /
`source_evidence`，外加一张任务表。不是 31 张——那 31 张里一大半是它自己的书库、
平台、类型、收藏、导出记录，StoryLens 已经有对应的东西。

---

## 四、已经定下来的产品决策

- **素材库跑本地确定性引擎**（`provider='local'`），不调云端模型、不要密钥、不联网。
  这是它在 StoryLens 里最特别的地方：现在每个实质功能都要花用户的钱，这个不花。
- **基础资料库免费**，组合器 / 导出 / 跨书统计归 Pro。
  理由：对一个我们不花钱、用户也不花钱的功能收费，和产品其余部分的定价逻辑对不上。
- **两套类型体系各留各的**，不强行合并。material-lab 的 10 类型模板决定「抽什么样的
  资料」，StoryLens 的作品画像五轴决定「分析按什么侧重进行」——不是一回事。
  画像可以给类型模板一个默认建议，但不绑死。
- **旧库那 40,967 条资料不迁移**，在 StoryLens 里重新导入重跑（本地引擎不花钱，只花时间）。
  除非那 28 本书的原始文件已经找不到了。

---

## 五、这个仓库的几条硬规矩

- 测试从**仓库根**跑：`python -m pytest apps/api/tests/...`。
  要读仓库里的文件用 `tests/paths.py` 的 `REPO_ROOT` / `config_file()`，
  **不要写相对路径**——那正是刚修完的一个坑（两批相对路径互相矛盾，
  没有任何工作目录能让全部测试通过）。
- 前端：`npx tsc --noEmit -p tsconfig.app.json`（**不是** `tsconfig.json`，
  那个是 `files: []`，检查不到任何东西）。
- 不要 `git add -A`。显式 add 你自己的文件。
- 生产库 `C:\Users\msi\AppData\Local\StoryLens\database\storylens.db` **只读，永不写入**。
  要真数据就复制一份出来。

---

## 六、第一步做什么

不要一上来就搭全套。先做**一条能跑通一本书的最小链路**：

1. 搬 `lexicon` + `genre_templates` + `atoms` + `materials`（纯逻辑，无数据库）
2. 写一个函数：吃 StoryLens 的 `Chapter` / `Paragraph`，吐 `Material` 列表——**先不落库**
3. 拿书库里现有的书真跑一遍，把结果打出来看
4. **和 material-lab 跑同一本书的结果对一遍**——对不上说明搬的过程中丢了东西

这一步跑通之前不要建表、不要写接口、不要做界面。
那四样都建立在「引擎搬过来还是原来那个引擎」这个前提上，而这个前提要先被证明。
