# HOOK_CONSISTENCY_AUDIT — CHG-20260729-005 Manual Gate

**Change:** CHG-20260729-005  
**Manual gate:** MG-CHG-20260729-005 FAILED  
**Public start HEAD:** `d0024432a55d9fd4e257d5b92581715c735e0ce1`  
**Live sample:** `GET http://127.0.0.1:18044/api/v1/reader-journey-runs/1` (Fake 6-scene MG DB)

## Observed contradiction

| Surface | Observed |
|---------|----------|
| Chapter overview / verdict | `当前仅识别到较弱的阅读期待，暂无可靠钩子结论。` |
| Bottom Scene index (S05) | `明确回应` |
| Right panel insight | `本场景暂无可靠的钩子洞察。` |

## Trace answers

| # | Question | Answer |
|---|----------|--------|
| 1 | Chapter “暂无可靠钩子结论” source | `buildChapterHookSimplificationModel` → `empty_kind=low_confidence` when loops exist but `readerQuestionOf` rejects all (`smoke-fake…` via `isInternalNoise`). Title: `CHAPTER_HOOK_LOW_CONFIDENCE_TITLE`. |
| 2 | S05 “明确回应” source | `JourneyDiagnosisBand` → `primaryBandLabelForHookPayoffLens(diag)` → `positive_mechanism === "effective_payoff"` / `mapDiagnosisCodeToBandLabel` → **明确回应**. Independent of chapter simplification model. |
| 3 | Score-only? | Live S05: `scores.payoff=80`, `scores.hook=80`, `positive_mechanism=effective_payoff`; `payoffs[]` empty on node. Band label is diagnosis/score-driven, not entity Response. |
| 4 | Linked Hook→Response fact? | Narrative loops present but questions are smoke-fake noise; `primary_relation.grade` often `unsupported` / `score_inferred` payoff_ref; **no reliable linked entity Response** for ordinary UI. |
| 5 | Valid evidence for Response? | Loop evidence may cite paragraph IDs, but Response entity+link gate fails; chapter model correctly treats hooks as non-readable. |
| 6 | Scene label bypasses chapter gate? | **YES.** Diagnosis band never reads `chapter_hook_mode` / `empty_kind`. |
| 7 | Right insight unavailable? | `deriveChapterHookSceneInsightV1` uses readable loops / node labels; with no reliable judgment → unavailable copy. |
| 8 | Three independent inferences? | **YES.** (A) `chapterHookSimplification` chapter empty gate; (B) `hookPayoffLensModel.primaryBandLabelForHookPayoffLens` diagnosis band; (C) right insight derive. |
| 9 | Old generic copy on Hook page? | Diagnosis band can emit `明确回应` / historically `未发现明显异常` / `表现有效` via shared diagnosis mapping on hook lens. |
| 10 | Legacy journeys? | Any journey with high payoff / `effective_payoff` but no readable hooks can reproduce the same split. |

## Confirmed root cause

**Primary:** `E. MULTIPLE_UI_FACT_SOURCES`  
**Contributing:** `B. CHAPTER_GATE_NOT_PROPAGATED` + `A. SCORE_ONLY_RESPONSE_INFERENCE` (diagnosis/`effective_payoff` / payoff score path treated as “明确回应” without reliable linked Hook Response).

Chapter simplification correctly gates Fake/smoke-fake as uncertain; bottom Scene index still uses the old hook-payoff diagnosis band labels and therefore shows “明确回应”.

## Fix direction

1. Single `ChapterHookPresentationV1` (`buildChapterHookSimplificationModel`) as the only ordinary Hook fact source.  
2. Propagate `chapter_hook_mode` to diagnosis band / scene actions / overview / ending pull / right insight.  
3. Hard-gate `给出回应` on reliable hook + linked non-score_inferred Response + valid evidence.  
4. none/uncertain: overview zeros; scene actions none; no “明确回应”.
