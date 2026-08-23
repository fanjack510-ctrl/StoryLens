# 02｜领域模型与数据对象

## 1. 内容层级

```text
Book
 └─ Volume（MVP 可选）
     └─ Chapter
         └─ Scene
             └─ NarrativeUnit
                 └─ ParagraphEvidence
```

## 2. 核心实体

### Book

- id
- title
- author
- source_file_name
- source_file_hash
- import_status
- language
- created_at

### Chapter

- id
- book_id
- chapter_index
- title
- start_paragraph_id
- end_paragraph_id
- word_count

### Paragraph

- id：稳定业务 ID，例如 `B0001-C0003-P0028`
- book_id
- chapter_id
- paragraph_index
- raw_text
- normalized_text
- char_start
- char_end
- source_page（可空）

### Scene

- id
- chapter_id
- scene_index
- start_paragraph_id
- end_paragraph_id
- time
- location
- viewpoint_character
- goal
- obstacle
- turning_point
- result
- confidence

### AnalysisRun

记录每次模型任务：

- id
- task_type
- provider
- model
- prompt_version
- schema_version
- input_hash
- status
- started_at
- completed_at
- raw_output
- validated_output
- error_message

### EvidenceLink

- analysis_item_id
- paragraph_id
- evidence_role
- quote_hash

## 3. 分析结果原则

每条结论必须分离：

1. 客观事实；
2. 叙事判断；
3. 可复用写法；
4. 原文证据。

---

## 一本书的两个属性：它是什么，和怎么读它

这两件事必须分开，因为它们回答的不是同一个问题。

| 字段 | 取值 | 回答什么 | 谁决定 |
|---|---|---|---|
| `books.material_kind` | `fiction` / `reference` | **这是什么书** | 导入时问用户，之后可改 |
| `books.analysis_form` | `long` / `short` | **怎么切它** | 只对小说有意义 |

`material_kind` 决定这本书能用哪几种读法：

* `fiction` → 评测（看自己的书）、拆文（看别人的书）
* `reference` → 读懂（逐节给出主张、依据、能照做的动作）

`analysis_form` 只在 `fiction` 上有意义。工具书按**节**读，没有「短篇」这一说——读懂的分析单元
是节，不是场景。所以导入时选了工具书，第二步根本不会出现，并且 `analysis_form` 直接落到 `long`。

### 为什么要新增 material_kind

在它之前，导入面板问的是「这本书按哪种读法切？整本 / 短篇」——一个关于**怎么切**的工程问题。
而提示文案里写着：

> 专著、教材、工具书选「整本」

也就是说，产品在让用户**自己把书的类型翻译成切法**。而「这是小说还是工具书」这件事，要等他进了
全书分析页、在三种读法里挑一个，才第一次被表达出来。库里也确实没有这个字段。

### NULL 的含义与推断

`NULL` = 没人回答过。这时按证据推断，**推断结果不写库**——写了就分不清「用户说的」和「程序猜的」，
而这两者在界面上必须能分开：猜的要标「待确认」，让人点一下就定。

推断按证据强度排序（见 `app/narrative_core/material_kind.py`）：

1. 这本书已经跑过「读懂」→ 工具书。那条读法只做专著与工具书，跑过就是最硬的证据。
2. 解析时走了「章首目录 + 逐节定位」那条路 → 工具书。标记 `结构来自原书目录` 是后来才加的，
   更早导入的书要退回看解析规则里的「精确定位」。
3. 都没有 → 小说。绝大多数导入的是小说，而且猜错成小说的代价更小。

### 一条通用的规矩

**导入时定死、之后没法改的值，就是永远错的。** 书名当年就是这么错的——从文件名来，从没被验证过，
产品里也没有任何地方能改。所以 `material_kind` 和 `analysis_form` 一样：导入时问，之后随时能改，
改了不动任何已有的分析结果。
