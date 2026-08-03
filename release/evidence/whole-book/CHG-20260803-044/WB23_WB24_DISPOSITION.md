# WB-2.3 / WB-2.4 Disposition — CHG-20260803-044

## WB-2.3-STORYLINES

| Field | Value |
|---|---|
| Historical title | Storylines |
| Historical change_id | CHG-20260728-020（change 文件仍 ABSENT；不伪造） |
| wb_status | **planned**（不改为 completed/verified/started） |
| scope_disposition | **deferred** |
| target_version_bucket | **pro_future** |
| required for V1.2.0 | **NO** |
| Action | 保留历史 Registry 记录；不删除；不改历史 Commit；不开始编码 |

## WB-2.4-FIRST-FOUR-PRODUCT

### Original goal (audit)
Registry title: **First-four product integration**.  
Phase2B first-four modules document defines:

| Phase2B module | DTO |
|---|---|
| A book_overview | BookOverviewResultDto |
| B structure_stages | StructureStagesResultDto |
| C chapter_functions | ChapterFunctionsResultDto |
| D storylines | StorylinesResultDto |

Therefore WB-2.4 originally meant integrating that Phase2B quartet (including Storylines), not the current product Free four.

### Current product Free four (already delivered)

| Product Free module | Delivered via |
|---|---|
| 全书总览 | Wave D / overview path |
| 主要人物与关键事件 | Free characters_events path |
| 故事结构 | WB-2.1 |
| 章节功能 | WB-2.2 |

Storylines is **not** in the Free four.

### Disposition

| Field | Value |
|---|---|
| wb_status | **planned**（历史状态保留；不伪造 verified） |
| scope_disposition | **superseded_by_current_free_four_modules** |
| target_version_bucket | historical_phase2b |
| required for V1.2.0 | **NO** as a new coding step |
| Do not | 重复实施 Storylines；把 WB-2.4 当作下一功能步骤 |

## Naming collision (resolved)

| Term | Meaning |
|---|---|
| Phase2B / registry “first-four” | overview + structure + chapter_functions + **storylines** |
| V1.2.0 Free four | overview + characters_events + structure + chapter_functions |

After CHG-044, only the **product Free four** is authoritative for V1.2.0.
