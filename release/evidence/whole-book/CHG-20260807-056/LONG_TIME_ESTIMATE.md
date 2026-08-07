# LONG_TIME_ESTIMATE — CHG-20260807-056

DATE：2026-08-07

基于 L3-B `MEDIUM_PROVIDER_UNITS.json` 真实 17 次调用起止时间：

| Field | Value |
|---|---|
| SAMPLE SIZE | 17 |
| MEDIAN REAL CALL DURATION | **18.01 s** |
| P95 CALL DURATION | **21.74 s** |
| PIPELINE | 当前 Free 路径按串行 Provider Unit 假设 |
| NORMAL LONG RUN WALL CLOCK | 约 **78–178 分钟**（粗估；含 repair/p95 上界） |

非精确 SLA。Pause/Resume 会拉长墙钟时间。

LONG RUN TIME ESTIMATE：约 **1.3–3.0 小时**（粗范围）
