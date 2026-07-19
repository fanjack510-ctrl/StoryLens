# Codex 第一轮执行指令：建立可运行项目骨架

你正在实施 `StoryLens / 叙镜` 项目。请严格遵守根目录 `AGENTS.md`。

## 一、先读取

依次读取：

1. `README.md`
2. `docs/00_project_overview.md`
3. `docs/01_architecture.md`
4. `docs/02_domain_model.md`
5. `docs/03_processing_pipeline.md`
6. `docs/04_model_gateway.md`
7. `docs/05_api_contract.md`
8. `docs/06_mvp_roadmap.md`
9. `docs/07_quality_and_evaluation.md`
10. `docs/08_codex_workflow.md`

## 二、本轮只完成 Phase 0 + Phase 1A

目标：让项目在 Windows 上可启动，并打通“文本导入 → 章节识别 → 段落编号 → 数据入库 → API 查询”闭环。

### 必须完成

1. 建立 Python 3.11 虚拟环境兼容配置。
2. 完善 `pyproject.toml`，使用 FastAPI、Uvicorn、SQLAlchemy、Pydantic v2、Alembic、python-docx、ebooklib、beautifulsoup4、httpx、tenacity、pytest。
3. 完成配置管理：
   - `.env`
   - SQLite 默认数据库
   - 本地 llama-server Provider 配置
4. 完成数据库模型：
   - Book
   - Chapter
   - Paragraph
   - AnalysisRun
5. 完成文本导入：
   - TXT
   - DOCX
   - EPUB
6. 完成章节标题识别与段落唯一编号。
7. 完成接口：
   - `GET /health`
   - `POST /api/v1/books/import`
   - `GET /api/v1/books`
   - `GET /api/v1/books/{book_id}`
   - `GET /api/v1/books/{book_id}/chapters`
   - `GET /api/v1/chapters/{chapter_id}/paragraphs`
8. 写测试，至少覆盖：
   - TXT 导入
   - 章节切分
   - 段落 ID 连续性
   - 非法文件类型
9. 更新 README 的实际启动命令。
10. 输出本轮完成报告，列出修改文件、测试结果、未完成项。

### 本轮禁止

- 不接入真实付费 API。
- 不实现桌面 UI。
- 不实现完整场景分析。
- 不引入 Redis、Celery、Neo4j。
- 不训练模型。

## 三、验收标准

执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap_windows.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_api.ps1
```

随后：

```powershell
python .\scripts\check_project.py
pytest
```

所有检查通过后，才算完成。
