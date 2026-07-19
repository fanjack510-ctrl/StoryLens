# 05｜第一版 API 约定

## 基础接口

### GET /health

返回应用、数据库和默认 Provider 状态。

### POST /api/v1/books/import

上传 TXT、DOCX 或 EPUB。

返回：

```json
{
  "book_id": "...",
  "status": "imported",
  "chapter_count": 12,
  "paragraph_count": 865
}
```

### GET /api/v1/books

列出书籍。

### GET /api/v1/books/{book_id}

返回书籍元数据与处理状态。

### GET /api/v1/books/{book_id}/chapters

返回章节列表。

### GET /api/v1/chapters/{chapter_id}/paragraphs

返回段落及稳定段落 ID。

## 分析接口（Phase 1B）

### POST /api/v1/chapters/{chapter_id}/analyze/scenes

### POST /api/v1/scenes/{scene_id}/analyze

### POST /api/v1/chapters/{chapter_id}/analyze/hooks

### POST /api/v1/analysis/{analysis_id}/review

## 统一错误结构

```json
{
  "error_code": "INVALID_FILE_TYPE",
  "message": "仅支持 TXT、DOCX、EPUB",
  "details": {}
}
```
