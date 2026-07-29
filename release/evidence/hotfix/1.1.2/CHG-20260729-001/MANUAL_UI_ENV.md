# MANUAL UI ENV — CHG-20260729-001

## Status

Ready for MG-CHG-20260729-001 MANUAL UI ACCEPTANCE

## Runtime

| Item | Value |
|------|-------|
| PUBLIC HEAD | 4dd49a0ee437d87144335f9382152c9919bc5122 |
| DATABASE | %TEMP%\storylens-mg-chg001-insights\database\storylens-mg-chg001-insights.db |
| API | http://127.0.0.1:18042 |
| FRONTEND | http://127.0.0.1:1421 |
| JOURNEY | http://127.0.0.1:1421/books/1?chapterId=1&journeyRun=1 |
| Fake Provider | ON |
| Real Provider | OFF / calls = 0 |
| Formal DB writes | 0 |

## Seed

- 6 Fake Journey scenes succeeded
- dimension_insights generated (6 distinct per scene)
- overall_reading_score != reading_tension on sample node (63.8 vs 43.0)
- UTF-8 Chinese paragraphs verified (雨打青瓦)

## Accept focus

1. Six dimension names unchanged
2. Composite curve / phase cards show 综合阅读 (not 阅读张力 / 阅读动力)
3. Same scene → six different insights when switching tabs
4. No old five detail tabs / no technical fields in normal mode
5. Developer mode → 技术详情 collapsed by default
