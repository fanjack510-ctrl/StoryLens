# LONG_SCALING_COMPARISON — CHG-20260807-056

DATE：2026-08-07

## L3-B baseline

| | |
|---|---|
| Chapters | 42 |
| Characters | 129457 |
| Estimated Units | 22 |
| Actual Units / Calls | 17 / 17 |
| Estimated Cost | 0.45832–0.674 CNY |

## Long book

| | |
|---|---|
| Chapters | 1299 |
| Characters | 2672342 |
| Estimated Units | 490 |

## Factors

| Factor | Value |
|---|---|
| CHAPTER SCALE FACTOR | 1299/42 ≈ **30.93×** |
| CHARACTER SCALE FACTOR | 2672342/129457 ≈ **20.64×** |
| ESTIMATED UNIT SCALE FACTOR | 490/22 ≈ **22.27×** |

Unit scale 落在 chapter/character scale 之间；Repair reserve（163）造成 call-count 膨胀但非平方/指数。
NORMAL units（327）/ L3-B normal（16）≈ **20.4×**，贴近字数 scale。

SCALING：**REASONABLE**
