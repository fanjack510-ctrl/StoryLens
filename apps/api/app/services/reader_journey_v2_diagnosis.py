"""Deterministic diagnosis engine for Reader Journey v2.0."""

from __future__ import annotations

from app.schemas.reader_journey_v2 import (
    DiagnosisCode,
    DiagnosisSeverity,
    DiagnosticEvidence,
    QuestionLifecycleRecord,
    SceneDiagnosisV2,
    SceneReaderJourneyProfileItemV2,
)
from app.services.reader_journey_v2_mapping import mapped_or_zero


def _sev(codes: list[DiagnosisCode]) -> DiagnosisSeverity:
    critical = {"tension_overload", "information_overload", "plot_stagnation"}
    high = {"empty_fast_pacing", "delayed_payoff", "empty_hook", "scene_boundary_anomaly"}
    medium = {
        "weak_progress",
        "pacing_too_slow",
        "pacing_too_fast",
        "weak_curiosity",
        "weak_tension",
        "weak_emotional_investment",
        "suspended_tension",
        "weak_hook",
        "abrupt_reveal",
        "unclear_expression",
    }
    if any(code in critical for code in codes):
        return "critical"
    if any(code in high for code in codes):
        return "high"
    if any(code in medium for code in codes):
        return "medium"
    if codes:
        return "low"
    return "info"


def diagnose_scene(
    profile: SceneReaderJourneyProfileItemV2,
    *,
    previous: SceneReaderJourneyProfileItemV2 | None = None,
    lifecycle: list[QuestionLifecycleRecord] | None = None,
) -> SceneDiagnosisV2:
    codes: list[DiagnosisCode] = []
    positive: DiagnosisCode | None = None
    metrics: list[str] = []
    notes: list[str] = []
    data_quality = profile.data_quality_issue

    plot = float(profile.plot_progress or 0.0)
    tension = float(profile.reading_tension or 0.0)
    pacing = mapped_or_zero(profile.pacing_speed)
    pacing_fit = float(profile.pacing_fit or 0.0)
    momentum = float(profile.reading_momentum or 0.0)
    hook = mapped_or_zero(profile.hook)
    payoff = mapped_or_zero(profile.payoff)
    curiosity = mapped_or_zero(profile.curiosity)
    tension_score = mapped_or_zero(profile.tension)
    emotion = mapped_or_zero(profile.emotional_investment)
    clarity = mapped_or_zero(profile.clarity)
    cognitive = mapped_or_zero(profile.cognitive_load)
    info = mapped_or_zero(profile.information_gain)

    if profile.node_type == "beat" or data_quality == "scene_boundary_anomaly":
        codes.append("scene_boundary_anomaly")
        metrics.append("node_type")
        notes.append("Scene/Beat boundary anomaly marked as data quality, not literary defect")
        data_quality = data_quality or "scene_boundary_anomaly"

    if plot < 35 and pacing > 70:
        codes.append("empty_fast_pacing")
        metrics.extend(["plot_progress", "pacing_speed"])
    if plot < 30:
        codes.append("plot_stagnation" if plot < 20 else "weak_progress")
        metrics.append("plot_progress")
    if pacing_fit < 50 and pacing < 40:
        codes.append("pacing_too_slow")
        metrics.append("pacing_speed")
    if pacing_fit < 50 and pacing > 80:
        codes.append("pacing_too_fast")
        metrics.append("pacing_speed")
    if cognitive > 75 and info > 70:
        codes.append("information_overload")
        metrics.extend(["cognitive_load", "information_gain"])
    if curiosity < 35:
        codes.append("weak_curiosity")
        metrics.append("curiosity")
    if tension_score < 35:
        codes.append("weak_tension")
        metrics.append("tension")
    if emotion < 35:
        codes.append("weak_emotional_investment")
        metrics.append("emotional_investment")
    if tension_score > 80 and payoff < 30 and hook > 70:
        codes.append("suspended_tension")
        metrics.extend(["tension", "hook", "payoff"])
    if tension_score > 90 and clarity < 50:
        codes.append("tension_overload")
        metrics.extend(["tension", "clarity"])
    if hook < 30 and profile.scene_role in {"open_end", "escalation", "setup"}:
        codes.append("weak_hook")
        metrics.append("hook")
    if hook > 75 and (not profile.hook.evidence_paragraph_ids) and payoff < 30:
        codes.append("empty_hook")
        metrics.append("hook")
    if previous is not None and mapped_or_zero(previous.hook) > 70 and payoff < 35:
        # Delayed relative to prior hook.
        related = [
            item
            for item in (lifecycle or [])
            if item.setup_scene <= previous.scene_ordinal
            and item.status in {"open", "progressing", "overdue"}
        ]
        if related:
            codes.append("delayed_payoff")
            metrics.append("payoff")
    if profile.scene_role == "reveal" and mapped_or_zero(profile.setup_consistency) < 40:
        codes.append("abrupt_reveal")
        metrics.append("setup_consistency")
    if payoff >= 70 and mapped_or_zero(profile.setup_consistency) >= 50:
        positive = "effective_payoff"
        metrics.append("payoff")
    if clarity < 45:
        codes.append("unclear_expression")
        metrics.append("clarity")
    if float(profile.confidence) < 0.45:
        codes.append("low_confidence")
        notes.append("model confidence below 0.45")

    # Deduplicate while preserving order; scene_boundary_anomaly stays secondary unless alone.
    unique: list[DiagnosisCode] = []
    for code in codes:
        if code not in unique:
            unique.append(code)

    primary: DiagnosisCode | None = None
    secondary: list[DiagnosisCode] = []
    for code in unique:
        if code == "scene_boundary_anomaly" and len(unique) > 1:
            secondary.append(code)
            continue
        if primary is None:
            primary = code
        else:
            secondary.append(code)
    secondary = secondary[:4]

    confidence = min(1.0, max(0.2, float(profile.confidence) * (0.85 if primary else 1.0)))
    return SceneDiagnosisV2(
        scene_ordinal=profile.scene_ordinal,
        primary_diagnosis=primary,
        secondary_diagnoses=secondary,
        positive_mechanism=positive,
        severity=_sev(([primary] if primary else []) + secondary),
        diagnostic_evidence=DiagnosticEvidence(
            scene_ordinals=[profile.scene_ordinal],
            metric_keys=sorted(set(metrics)),
            notes="; ".join(notes)[:240],
        ),
        confidence=confidence,
        data_quality_issue=data_quality,
    )


def diagnose_chapter(
    profiles: list[SceneReaderJourneyProfileItemV2],
    *,
    lifecycle: list[QuestionLifecycleRecord] | None = None,
) -> list[SceneDiagnosisV2]:
    ordered = sorted(profiles, key=lambda item: item.scene_ordinal)
    out: list[SceneDiagnosisV2] = []
    previous = None
    for profile in ordered:
        out.append(diagnose_scene(profile, previous=previous, lifecycle=lifecycle))
        previous = profile
    return out
