# LONG_WINDOW_PLAN — CHG-20260807-056

DATE：2026-08-07

Estimate `estimated_window_count` 来自 token 粗算；物理窗口计划用 snapshot 上 `whole_book_windowing_v1` **只读规划**（无 Formal Create、无 Provider）。

| Field | Value |
|---|---|
| WINDOW COUNT（estimate） | 162 |
| WINDOW COUNT（physical plan） | 188 |
| ESTIMATED CHARACTERS EVENTS UNITS | 162 |
| AVG CHAPTERS PER WINDOW | 8.42 |
| AVG CHARACTERS PER WINDOW | 15327.1 |
| MAX WINDOW CHARACTERS | 16183 |
| MIN WINDOW CHARACTERS | 4569 |
| SINGLE-CHAPTER WINDOWS | 0 |
| EMPTY WINDOWS | 0 |
| DUPLICATE PROVIDER UNIT KEYS | 0 |
| Overlap paragraph hits（allowed overlap） | 6149 |

相对 L3-B OBS-L3B-002（8→9，~+12.5%）：长书 162→188，~+16.0%。属同方向低估偏差被规模放大，**非** window≈chapter 爆炸。

OBS-L3B-002：SUSPICIOUS（非 ABNORMAL unit 爆炸）
