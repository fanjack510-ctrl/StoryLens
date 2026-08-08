# CHG-20260808-061 Evidence

## Targeted tests

See `TARGETED_TESTS.txt` — 10 passed (`test_whole_book_provider_selection_chg061.py`).

## Typecheck

See `TYPECHECK.txt` — desktop `tsc --noEmit` PASS.

## Real provider calls

0 (Prepare / Estimate / pin / routing tests only; no DeepSeek/Aliyun chat invocations).

## Manual retest (user)

Reopen 《我不是戏神》→ 全书分析 → Prepare / Cost Estimate only (do not Start).

Expect:

- Provider / 模型：`deepseek` / `deepseek-v4-flash`
- `run_creation_enabled` / provider available after consent enables Start
- Cost uses DeepSeek pricing (not Aliyun ¥8–¥12 band)
- REAL PROVIDER CALLS：0
