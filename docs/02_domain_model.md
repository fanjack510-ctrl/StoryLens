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
