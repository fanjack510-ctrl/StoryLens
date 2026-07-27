# Reader Journey V2 通用规则规范

**Change:** CHG-20260721-012
**Contract / Formula / Prompt:** 2.0
**Status:** frozen baseline for general verification (VERSION 1.0.3)
**Principle:** Rules are work-agnostic. Named novels (e.g. external validation books) are instances only — never inputs to product branching.

---

## 0. Audit freeze (current product)

### 0.1 Confirmed clean (no instance branching)

Scanned for work-name / character-name / scene-ordinal / paragraph_id / Chinese-prose / per-book bonus branches in:

| Area | Location | Result |
|------|----------|--------|
| Formula config | `config/reader_journey_formulas_v2.json` | Clean |
| Role targets | `config/scene_role_targets.json` | Clean (role bands only) |
| Level mapping | `reader_journey_v2_mapping.py` | Clean |
| Derivation | `reader_journey_v2_derivation.py` | Clean |
| Diagnosis | `reader_journey_v2_diagnosis.py` | Clean |
| Lifecycle | `reader_journey_v2_question_lifecycle.py` | Clean |
| Scene/Beat heuristics | `scene_fragment_consolidation.py` | Pattern-generic (silence/reaction), not novel-titled |
| V2 prompts | `packages/prompts/reader_journey_scene/v2.0/*` | Clean |
| Lens binding | `apps/desktop/.../lensMetricBinding.ts` | Clean |

### 0.2 Known legacy risk (outside V2 score formulas)

`reader_journey_visual_calibration.CLUSTER_ANCHOR_TERMS` still seeds terms such as「陈伶」「戏鬼」for **question-cluster similarity** (legacy visualization path). It does **not** alter `mapped_score`, `plot_progress`, `reading_momentum`, or diagnosis thresholds. Tracked as legacy debt; must not be used as justification to retune V2 weights from a single novel.

### 0.3 Absolute bans (must never enter product rules)

- Book / series title branches
- Character or location name branches
- Hard-coded `scene_ordinal` / `scene_id` / `paragraph_id` branches
- Chinese source-sentence branches that award score
- Per-novel thresholds or ±bonus
- Chapter min–max rescaling of scores for display or derivation

---

## 1. 剧情推进 `plot_progress`

**Definition:** Degree to which the scene advances goals, conflict, world/character state, information, agency, and causal coherence.

**Inputs (mapped_score 0–100 from level 0–5):**
`goal_progress`, `conflict_change`, `state_change`, `information_gain`, `character_agency`, `causal_coherence`

**Formula:**

```
plot_progress = clamp_0_100(
  0.25*goal_progress + 0.20*conflict_change + 0.20*state_change
  + 0.15*information_gain + 0.10*character_agency + 0.10*causal_coherence
)
```

**Rounding:** 1 decimal (`ROUND_HALF_UP`).
**scene_role:** does **not** change this formula.

---

## 2. 阅读张力 `reading_tension`

**Definition:** Composite pull from curiosity, threat/stakes tension, and emotional investment.

**Formula:**

```
reading_tension = clamp_0_100(
  0.40*curiosity + 0.35*tension + 0.25*emotional_investment
)
```

**scene_role:** does not change this formula.

---

## 3. 好奇 `curiosity` (base level)

**Definition:** Strength of a concrete reader information gap or predictive question (not vague “interesting”).

**Mapping:** level → mapped_score (see §18). Used inside `reading_tension` and diagnosis (`weak_curiosity` if mapped &lt; 35).

---

## 4. 紧张 `tension` (base level)

**Definition:** Stakes / threat / deadline pressure felt by the reader for characters’ situation.

**Diagnosis:** `weak_tension` if mapped &lt; 35; `suspended_tension` / `tension_overload` with combined rules (§15).

---

## 5. 情绪投入 `emotional_investment` (base level)

**Definition:** Reader care for characters via concrete reactions, relationships, or costs — not abstract mood adjectives alone.

---

## 6. 情绪强度与情绪方向

| Concept | Fields | Notes |
|---------|--------|-------|
| 情绪强度 | `arousal_start`, `arousal_end` (levels) | UI often averages mapped/legacy arousal for the emotion lens |
| 情绪方向 | `emotional_valence_start`, `emotional_valence_end` | Presentation may show signed valence (−100…+100) for legacy curves; V2 levels still map 0–100 via §18 |

Valence/arousal **do not** enter `reading_momentum` weights in formula 2.0.

---

## 7. 节奏速度 `pacing_speed` (base level)

**Definition:** Perceived narrative speed / event density of the scene (actual speed), independent of “good/bad”.

---

## 8. 节奏适配 `pacing_fit`

**Definition:** How well `pacing_speed` fits the **scene_role target band**.

```
pacing_fit = fit_to_band(pacing_speed, role.pacing_speed_band)
fit_to_band: in-band → 90; else 90 − 2*|distance|; clamp 0–100
```

Role bands: `config/scene_role_targets.json` (e.g. setup [35,60], climax [70,95], aftermath [25,55]).

**Invariant:** Changing only `scene_role` must not change base mapped fields or `plot_progress` / `reading_tension`; it may change `pacing_fit` and `hook_payoff_fit` only.

---

## 9. 钩子 `hook` (base level)

**Definition:** Forward-driving open question, threat, or promise that makes the next scene desirable.

---

## 10. 回报 `payoff` (base level)

**Definition:** Satisfaction / answer / consequence that pays prior hooks or questions.

`hook_payoff_fit` = weighted fit of hook & payoff to role bands (`hook_weight` / `payoff_weight` per role).

---

## 11. 清晰度、认知负荷、冗余

| Field | Meaning |
|-------|---------|
| `clarity` | Referential clarity; low → expression diagnosis / momentum penalty |
| `cognitive_load` | Processing burden; high with high info → overload diagnosis / penalty |
| `redundancy` | Repeated explanation without new state |

**Momentum penalties** (`config/reader_journey_formulas_v2.json`):

- clarity &lt; 60 → `(60 − clarity) * 0.25`
- cognitive_load &gt; 60 → `(cognitive_load − 60) * 0.15`
- redundancy &gt; 50 → `(redundancy − 50) * 0.10`

---

## 12. 阅读动力 `reading_momentum`

```
reading_momentum = clamp_0_100(
  0.30*plot_progress + 0.25*reading_tension
  + 0.20*pacing_fit + 0.25*hook_payoff_fit
  − clarity_penalty − cognitive_load_penalty − redundancy_penalty
)
```

User copy: **阅读动力**. Storage field: `reading_momentum`.
`engagement` is legacy-adapter only.

---

## 13. 流失风险 `dropoff_risk`

```
base = 100 − reading_momentum
# then chapter adjustments:
+8  if two consecutive clear momentum declines ending at this scene
+15 if three consecutive scenes with reading_momentum < 45
+10 if hook > 75, current payoff < 40, and no payoff≥50 within next 3 scenes
```

Legacy `engagement<40` consecutive rule is **forbidden** on `v2_native` / contract 2.x presentation.

---

## 14. Scene 与 Beat

- Model / consolidation may mark `node_type=beat` for silence / reaction / environment / dialogue residue fragments.
- Beat: `include_in_main_curve=false`, `include_in_chapter_mean=false`.
- Missing evidence / tiny summary on beat → `data_quality_issue=scene_boundary_anomaly` (quality, not literary failure).
- Inserting a Beat must not change equal-weight main-curve vertices of surrounding Scenes’ derived scores beyond re-index artifacts.

---

## 15. 诊断组合规则 (metric-triggered)

| Code | Trigger (summary) |
|------|-------------------|
| empty_fast_pacing | plot_progress &lt; 35 and pacing_speed &gt; 70 |
| plot_stagnation | plot_progress &lt; 20 |
| weak_progress | 20 ≤ plot_progress &lt; 30 |
| pacing_too_slow | pacing_fit &lt; 50 and pacing_speed &lt; 40 |
| pacing_too_fast | pacing_fit &lt; 50 and pacing_speed &gt; 80 |
| information_overload | cognitive_load &gt; 75 and information_gain &gt; 70 |
| weak_curiosity / weak_tension / weak_emotional_investment | mapped &lt; 35 |
| suspended_tension | tension &gt; 80 and payoff &lt; 30 and hook &gt; 70 |
| tension_overload | tension &gt; 90 and clarity &lt; 50 |
| weak_hook | hook &lt; 30 and role ∈ {open_end, escalation, setup} |
| empty_hook | hook &gt; 75, no hook evidence, payoff &lt; 30 |
| delayed_payoff | prior hook &gt; 70, payoff &lt; 35, open lifecycle |
| abrupt_reveal | role=reveal and setup_consistency &lt; 40 |
| effective_payoff (positive) | payoff ≥ 70 and setup_consistency ≥ 50 |
| unclear_expression | clarity &lt; 45 |
| low_confidence | profile.confidence &lt; 0.45 |
| scene_boundary_anomaly | beat / boundary quality |

Primary/secondary: first non-anomaly code primary; anomaly demoted if others exist.
Diagnosis confidence: `clamp(0.2, 1.0, profile.confidence * (0.85 if primary else 1.0))`.

UI band must **not** map missing primary →「正常」; Beat →「辅助节拍」.

---

## 16. scene_role 影响边界

**Allowed:** target bands for `pacing_speed` / `hook` / `payoff`; weights inside `hook_payoff_fit`; diagnosis gates that explicitly mention role (e.g. weak_hook roles, abrupt_reveal).

**Forbidden:** changing meanings of base levels or `plot_progress` / `reading_tension` formulas by role or by book.

---

## 17. Rules that must never change for a single instance failure

Weights, level→score map, no-evidence cap, fit_to_band constants, dropoff bonuses/thresholds, diagnosis numeric gates — only via multi-sample general failures on development/regression sets, never holdout peeking or one-book score targets.

---

## 18. Level → mapped_score, clamp, rounding, confidence

| Level | Mapped |
|------|--------|
| 0 | 10 |
| 1 | 30 |
| 2 | 50 |
| 3 | 65 |
| 4 | 80 |
| 5 | 95 |

- No evidence IDs → `mapped_score = min(mapped, 40)`.
- Clamp all derived metrics to [0, 100].
- Round derived to 1 decimal.
- Model must not emit `mapped_score` / `reading_momentum` / `dropoff_risk` as authority; program overwrites mapping.

---

## 19. Fallback

| Case | Behavior |
|------|----------|
| Missing mapped_score | Recompute from level + evidence |
| Unknown scene_role band | Default band [0,100] for fit |
| Legacy contract 1.x | `legacy_uncalibrated`; engagement adapter only |
| Missing diagnosis | UI: 未发现明显异常 / 旧版数据 / 辅助节拍 — never「正常」 |

---

## 20. Instance validation boundary

External books may only record: expected **general** ordering, failure class (model / rule / split / UI), and whether the same failure repeats across independent samples.
Forbidden product edits: “Scene N must be peak”, “elder exposition must be lower”, named landmark score floors.

---

## 21. Test set splits

See `data/fixtures/reader_journey_v2_general/test_set_splits.json`:

- **development** — may inspect when designing tests
- **holdout** — do not tune against; optional `RUN_V2_HOLDOUT=1`
- **regression** — always run in local V2 general suite

---

## 22. Verification acceptance (this baseline)

1. V2 product modules + formula/prompt configs: no instance prose hardcoding (automated).
2. Identity mutations (names/ids/order metadata): 100% stable derived metrics.
3. Minimal contrast ordering: ≥90%.
4. Degradation direction: ≥90%.
5. Beat insert: main-curve membership stable.
6. Formulas deterministically recalculable.
7. Same base levels ⇒ same plot/tension across roles; role only moves fit metrics.
8. No chapter min–max normalization in derivation.
9. Single-instance novel scores are not grounds for weight edits.

---

## 23. Scene 证据映射与业务校验

**Config:** `config/scene_evidence_validation.json`
**Implementation:** `apps/api/app/services/scene_evidence_validation.py`
**Principle:** Work-agnostic. Full-scene evidence alone is **not** a failure condition. Never retune V2 score weights from a single novel.

### 23.1 Field classes

| Class | Meaning | Examples |
|-------|---------|----------|
| **local** | Prefer minimal sufficient paragraphs (often 1–3); sharing evidence across fields is allowed | `goal_progress`, `conflict_change`, `state_change`, `information_gain`, `character_agency`, `curiosity`, `tension`, `hook`, `payoff`, Scene Analysis `entry_state`/`goal`/`obstacle`/`key_actions`/`turning_point`/`unresolved_question` |
| **holistic** | May cite broad / full-scene range when rationale is field-targeted | `causal_coherence`, `pacing_speed`, `pacing_fit`, `clarity`, `cognitive_load`, `redundancy`, `scene_role`, `overall_emotional_arousal`, `scene_function`, Scene Analysis `outcome` |
| **hybrid** | Not failed solely for full-scene citation; judged with length + rationale + reuse pattern | `emotional_investment`, `valence`, `atmosphere`, `hook_payoff_fit` |

Shared evidence across fields is **not** an error by itself.

### 23.2 Scene length bands (named thresholds)

| Band | Paragraph count | Rule |
|------|-----------------|------|
| micro | 1–3 (`micro_max_paragraphs`) | Full-scene citation by many fields allowed; still require in-scene IDs + non-empty field-targeted rationale when required |
| short | 4–6 (`short_max_paragraphs`) | Shared / full-scene evidence allowed; do not fail on full-scene alone |
| medium_long | ≥7 (`medium_long_min_paragraphs`) | See overbroad rule below |

### 23.3 Rationale checks (deterministic, no extra model)

- Normalize whitespace / punctuation / case
- Exact duplicate detection
- Simple token / Jaccard similarity (`rationale_jaccard_duplicate`, default 0.92)
- Mechanical templates such as「本场全部内容体现…」
Rationale similarity alone does **not** fail; it only contributes when combined with medium_long full-scene local reuse.

### 23.4 Boundary before evidence

If generic boundary signals indicate multi-event scope (`SCENE_BOUNDARY_TOO_BROAD`), return that code **before** `EVIDENCE_OVERBROAD_REUSE`. Evidence remap must not mask a split problem.

### 23.5 `EVIDENCE_OVERBROAD_REUSE` (all required)

On medium_long scenes only:

1. ≥ `min_local_fields_full_scene` (5) **local** fields cite the **exact** full-scene paragraph set
2. Those fields are ≥ `min_local_full_scene_ratio` (0.70) of local fields that have evidence
3. Rationales are highly duplicated / empty / mechanical
4. Fields are not classified holistic
5. Scene is not already classified boundary-too-broad

Payload includes: `scene_id`, `scene_paragraph_count`, `affected_fields`, `shared_evidence`, `local_field_count`, `full_scene_reuse_ratio`, `duplicate_rationale_groups`, `repairable=true`, `suggested_action=evidence_remap_repair`.

### 23.6 Other structured codes

- `EVIDENCE_OUTSIDE_SCENE` / `EVIDENCE_MISSING` — repairable evidence legality failures
- `SCENE_BOUNDARY_TOO_BROAD` — `suggested_action=rerun_scene_boundary`
- Base rules: IDs exist, in-scene, deduped preserving order, evidence+rationale together when required

### 23.7 `evidence_remap_repair`

- Max attempts: `max_evidence_repair_attempts` = **1**
- May rewrite only affected fields’ `evidence_paragraph_ids` and short field-targeted rationale
- **Must not** change `level`, `mapped_score`, plot/tension/pacing/hook/payoff/momentum, diagnosis, or question lifecycle
- Completed scenes are not re-analyzed; same `repair_request_id` is idempotent
- After one failed repair: pause, keep completed work, no infinite retry

### 23.8 Absolute ban

Do not add book title / character / scene-ordinal / source-sentence special cases to these thresholds.
