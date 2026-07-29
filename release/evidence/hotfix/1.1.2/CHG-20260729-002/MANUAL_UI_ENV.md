# MANUAL UI ENV — CHG-20260729-002

## Status

Ready for MG-CHG-20260729-002 MANUAL UI ACCEPTANCE

## Runtime

| Item | Value |
|------|-------|
| PUBLIC BASE HEAD | `017d9cc26d5dd510aff8f251ddb22d083af382f3` |
| DATABASE | `%TEMP%\storylens-mg-chg002-stage-colors\database\storylens-mg-chg002-stage-colors.db` |
| API | http://127.0.0.1:18042 |
| FRONTEND | http://127.0.0.1:1421 |
| JOURNEY | http://127.0.0.1:1421/books/1?chapter=1&journeyRun=1 |
| Fake Provider | ON |
| Real Provider | OFF / 0 |

## Fixture phases (isolated DB presentation ranges)

- Scene01—02：开端 `#e8ede9`
- Scene03—05：发展 `#f0ebe3`
- Scene06：收束 `#e6ebf0`

## Accept focus

1. Phase cards and chart bands share tokens
2. Midpoint band edges (not equal thirds)
3. Six lenses keep same stage bands
4. Left scene stage bar + 开端/发展/收束 label
5. No algorithm / score / insight changes
