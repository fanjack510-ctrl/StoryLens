"""Development-only Smoke Fake for chapter analysis Provider HTTP.

Enabled only when ``STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE=1`` (or true/yes/on)
**and** the process is not a packaged production runtime.

Replaces ``OpenAICompatibleProvider`` HTTP only. Does not fake Create Run,
Orchestrator, Parser, Materializer, Result API, or Task Center.

Failure injection (optional):
``STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE_FAIL=1`` → raise ProviderRequestError
on every generate (transport failure path).
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from app.core.paths import is_frozen, is_production_runtime
from app.model_gateway.base import ModelRequest, ModelResponse, ProviderRequestError
from app.model_gateway.provider_errors import TRANSPORT_REMOTE_DISCONNECT

_SMOKE_FAKE_ENV = "STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE"
_SMOKE_FAIL_ENV = "STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE_FAIL"
_logger = logging.getLogger(__name__)
_rejection_logged = False


def _env_truthy(name: str) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def is_chapter_analysis_smoke_fake_requested() -> bool:
    """Raw env request — does not apply production safety."""
    return _env_truthy(_SMOKE_FAKE_ENV)


def is_chapter_analysis_smoke_fake_fail_enabled() -> bool:
    return _env_truthy(_SMOKE_FAIL_ENV)


def is_chapter_analysis_smoke_fake_enabled() -> bool:
    """True only when explicitly requested and safe for non-packaged runtimes.

    Packaged / production installs never enable Fake, even if the env is set.
    Missing env never silently enables Fake.
    """
    global _rejection_logged
    if not is_chapter_analysis_smoke_fake_requested():
        return False
    # Frozen packaged Sidecar + production APP_ENV → hard reject.
    if is_frozen() or is_production_runtime():
        if not _rejection_logged:
            _logger.warning(
                "STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE requested but rejected: "
                "packaged/production runtime must use real Provider transport "
                "(frozen=%s production=%s)",
                is_frozen(),
                is_production_runtime(),
            )
            _rejection_logged = True
        return False
    return True


def chapter_smoke_fake_readiness_override() -> bool:
    """When Fake is active, treat Provider HTTP readiness as satisfied.

    Does not flip cloud master switch or invent ProviderConfiguration rows;
    only removes credential/health/disconnect blockers that require live HTTP.
    """
    return is_chapter_analysis_smoke_fake_enabled()


def _paragraph_ids_from_text(text: str) -> list[str]:
    found = re.findall(r"B\d+-C\d+-P\d+", text)
    # Preserve order, unique
    out: list[str] = []
    seen: set[str] = set()
    for item in found:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _scene_ids_from_text(text: str) -> list[str]:
    found = re.findall(r"B\d+-C\d+-S\d+", text)
    out: list[str] = []
    seen: set[str] = set()
    for item in found:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _paragraph_texts_from_prompt(text: str) -> dict[str, str]:
    """Best-effort map paragraph_id → quoteable body text from the prompt."""
    mapping: dict[str, str] = {}
    # Common snapshot style: {"paragraph_id":"B0001-C0001-P0001","text":"..."}
    for match in re.finditer(
        r'"paragraph_id"\s*:\s*"(B\d+-C\d+-P\d+)"[^}]{0,400}?"text"\s*:\s*"((?:\\.|[^"\\])*)"',
        text,
        flags=re.S,
    ):
        mapping[match.group(1)] = bytes(match.group(2), "utf-8").decode("unicode_escape")
    if mapping:
        return mapping
    # Line style: B0001-C0001-P0001: some text
    for match in re.finditer(r"(B\d+-C\d+-P\d+)\s*[:：]\s*(.+)", text):
        mapping.setdefault(match.group(1), match.group(2).strip()[:80])
    return mapping


def _quote_for(pid: str, texts: dict[str, str], fallback: str = "推进") -> str:
    body = (texts.get(pid) or "").strip()
    if body:
        return body[: min(24, len(body))]
    return fallback


_LEVEL_KEYS = (
    "goal_progress",
    "conflict_change",
    "state_change",
    "information_gain",
    "character_agency",
    "causal_coherence",
    "curiosity",
    "tension",
    "emotional_investment",
    "pacing_speed",
    "hook",
    "payoff",
    "setup_consistency",
    "question_lifecycle",
    "emotional_valence_start",
    "emotional_valence_end",
    "arousal_start",
    "arousal_end",
    "clarity",
    "cognitive_load",
    "redundancy",
)


def _scored_level(
    level: int,
    paragraph_ids: list[str],
    *,
    rationale: str,
) -> dict[str, Any]:
    evidence = paragraph_ids[:2] if paragraph_ids else []
    return {
        "level": max(0, min(5, level)),
        "evidence_paragraph_ids": evidence,
        "rationale": rationale[:200],
        "confidence": 0.8,
    }


def _scene_profile_item(
    scene_id: int,
    scene_ordinal: int,
    paragraph_ids: list[str],
    texts: dict[str, str],
) -> dict[str, Any]:
    """Build SceneReaderJourneyProfileItemV2-compatible payload (contract 2.0)."""
    first = paragraph_ids[0] if paragraph_ids else "B0001-C0001-P0001"
    roles = (
        "setup",
        "escalation",
        "investigation",
        "reveal",
        "climax",
        "aftermath",
        "transition",
        "open_end",
        "closed_end",
    )
    scene_role = roles[(max(1, scene_ordinal) - 1) % len(roles)]
    base_level = 2 + (scene_ordinal % 3)
    fields = {
        key: _scored_level(
            base_level if key not in {"cognitive_load", "redundancy"} else 1,
            paragraph_ids,
            rationale=f"smoke-fake {key} for scene {scene_ordinal}",
        )
        for key in _LEVEL_KEYS
    }
    # Emphasize journey-facing metrics for gate visibility.
    fields["hook"] = _scored_level(3, paragraph_ids, rationale="smoke-fake hook")
    fields["payoff"] = _scored_level(2, paragraph_ids, rationale="smoke-fake payoff")
    fields["curiosity"] = _scored_level(3, paragraph_ids, rationale="smoke-fake curiosity")
    fields["tension"] = _scored_level(3, paragraph_ids, rationale="smoke-fake tension")
    fields["pacing_speed"] = _scored_level(3, paragraph_ids, rationale="smoke-fake pacing")
    summary_seed = _quote_for(first, texts)
    return {
        "scene_id": int(scene_id),
        "scene_ordinal": int(scene_ordinal),
        "node_type": "scene",
        "scene_role": scene_role,
        "scene_value_summary": f"Scene{scene_ordinal}推进：{summary_seed}"[:160],
        "confidence": 0.8,
        "evidence_paragraph_ids": list(dict.fromkeys(paragraph_ids))[:16],
        **fields,
    }


def synthesize_chapter_smoke_fake_text(request: ModelRequest) -> str:
    """Deterministic JSON text satisfying chapter Parser contracts."""
    combined = "\n".join(str(m.get("content") or "") for m in request.messages)
    paragraph_ids = _paragraph_ids_from_text(combined)
    scene_ids = _scene_ids_from_text(combined)
    texts = _paragraph_texts_from_prompt(combined)
    if not paragraph_ids:
        paragraph_ids = ["B0001-C0001-P0001", "B0001-C0001-P0002"]

    journeyish = (
        "reader_journey" in combined
        or "读者阅读旅程" in combined
        or "JOURNEY_SCENE" in combined
        or "scene_profiles" in combined
        or "SceneReaderJourney" in combined
        or "scene_value_summary" in combined
        or ("contract_version" in combined and "2.0" in combined and "profiles" in combined.lower())
    )
    # v3.5 assisted boundary: CompactTransitionClassificationResultV35
    if (
        '"contract_version": "3.5"' in combined
        or "contract_version\": \"3.5\"" in combined
        or "CompactTransition" in combined
        or "owned_transition_ids" in combined
        or "boundary_candidate" in combined
        or "transition_id" in combined
    ) and (
        "场景边界" in combined
        or "boundary" in combined.lower()
        or "transition" in combined.lower()
        or "owned_transition_ids" in combined
    ):
        transition_ids = re.findall(r'"transition_id"\s*:\s*"([^"]+)"', combined)
        if not transition_ids:
            transition_ids = re.findall(
                r'"owned_transition_ids"\s*:\s*\[(.*?)\]', combined, flags=re.S
            )
            if transition_ids:
                transition_ids = re.findall(r'"([^"]+)"', transition_ids[0])
        if not transition_ids:
            # Fallback: invent one transition between first two paragraphs.
            if len(paragraph_ids) >= 2:
                transition_ids = [f"{paragraph_ids[0]}__{paragraph_ids[1]}"]
            else:
                transition_ids = ["T0001"]
        # Unique preserve order
        seen: set[str] = set()
        ordered: list[str] = []
        for tid in transition_ids:
            if tid not in seen:
                seen.add(tid)
                ordered.append(tid)
        decisions = []
        for tid in ordered:
            decisions.append(
                {
                    "transition_id": tid,
                    "boundary_candidate": False,
                    "goal_relation": "same",
                    "action_chain_relation": "continuous",
                    "temporal_relation": "continuous",
                    "location_relation": "same",
                    "viewpoint_relation": "same",
                    "trigger_type": "none",
                    "confidence": 0.85,
                }
            )
        payload = {"contract_version": "3.5", "decisions": decisions}
    elif (
        "reader_journey_chapter" in combined
        or "章节阅读旅程合成" in combined
        or "ChapterReaderJourneySynthesis" in combined
        or "one_sentence_diagnosis" in combined
        or "chapter_reader_question_chain" in combined
    ):
        ordinals = sorted(
            {int(item) for item in re.findall(r'"scene_ordinal"\s*:\s*(\d+)', combined)}
        ) or [1]
        payload = {
            "contract_version": "2.0",
            "chapter_reader_question_chain": [
                "本章异常细节将如何影响后续行动？"
            ],
            "question_lifecycle": [
                {
                    "question_id": "Q1",
                    "question_text": "本章异常细节将如何影响后续行动？",
                    "setup_scene": ordinals[0],
                    "development_scenes": [],
                    "payoff_scene": None,
                    "status": "open",
                    "strength": 55,
                }
            ],
            "scene_diagnoses": [
                {
                    "scene_ordinal": ordinal,
                    "primary_diagnosis": "weak_curiosity",
                    "secondary_diagnoses": [],
                    "positive_mechanism": None,
                    "severity": "info",
                    "diagnostic_evidence": {
                        "scene_ordinals": [ordinal],
                        "metric_keys": ["curiosity"],
                        "notes": "smoke-fake diagnosis",
                    },
                    "confidence": 0.7,
                    "data_quality_issue": None,
                }
                for ordinal in ordinals
            ],
            "pacing_diagnosis": ["节奏平稳，技术链路可复现"],
            "chapter_strengths": ["场景目标清晰"],
            "chapter_risks": ["钩子尚未回收"],
            "one_sentence_diagnosis": "本章完成技术闭环验证，阅读动力可继续追踪。",
            "average_reading_momentum": 0.6,
        }
    elif journeyish:
        # Prefer explicit (scene_id, scene_ordinal) pairs from the prompt snapshot.
        pairs = re.findall(
            r'"scene_id"\s*:\s*(\d+)[^}]{0,120}?"scene_ordinal"\s*:\s*(\d+)',
            combined,
            flags=re.S,
        )
        if not pairs:
            pairs = re.findall(
                r'"scene_ordinal"\s*:\s*(\d+)[^}]{0,120}?"scene_id"\s*:\s*(\d+)',
                combined,
                flags=re.S,
            )
            pairs = [(sid, ord_) for ord_, sid in pairs]
        if not pairs:
            numeric_ids = [
                int(item) for item in re.findall(r'"scene_id"\s*:\s*(\d+)', combined)
            ]
            # Preserve order, unique.
            ordered_ids: list[int] = []
            seen_ids: set[int] = set()
            for sid in numeric_ids:
                if sid not in seen_ids:
                    seen_ids.add(sid)
                    ordered_ids.append(sid)
            ordinals = [
                int(item) for item in re.findall(r'"scene_ordinal"\s*:\s*(\d+)', combined)
            ]
            ordered_ords: list[int] = []
            seen_ords: set[int] = set()
            for ordinal in ordinals:
                if ordinal not in seen_ords:
                    seen_ords.add(ordinal)
                    ordered_ords.append(ordinal)
            if ordered_ids and ordered_ords and len(ordered_ids) == len(ordered_ords):
                pairs = [(str(sid), str(ord_)) for sid, ord_ in zip(ordered_ids, ordered_ords)]
            elif ordered_ids:
                pairs = [(str(sid), str(index + 1)) for index, sid in enumerate(ordered_ids)]
        profiles = []
        chunk = paragraph_ids[:2] if len(paragraph_ids) >= 2 else paragraph_ids
        if pairs:
            seen_ord: set[int] = set()
            for sid_s, ord_s in pairs:
                ordinal = int(ord_s)
                if ordinal in seen_ord:
                    continue
                seen_ord.add(ordinal)
                profiles.append(_scene_profile_item(int(sid_s), ordinal, chunk, texts))
        else:
            ordinals = sorted(
                {int(item) for item in re.findall(r'"scene_ordinal"\s*:\s*(\d+)', combined)}
            )
            if not ordinals:
                ordinals = [1]
            for ordinal in ordinals:
                profiles.append(_scene_profile_item(ordinal, ordinal, chunk, texts))
        payload = {"contract_version": "2.0", "profiles": profiles}
    elif "场景边界识别器" in combined or ("boundary_candidate" in combined and "contract_version" not in combined):
        chapter_key = paragraph_ids[0].rsplit("-P", 1)[0]
        payload = {
            "chapter_id": chapter_key,
            "boundaries": [],
            "overall_confidence": 0.9,
        }
        if len(paragraph_ids) >= 4:
            mid = paragraph_ids[len(paragraph_ids) // 2 - 1]
            payload["boundaries"] = [
                {
                    "after_paragraph_id": mid,
                    "reasons": ["地点或目标发生变化"],
                    "confidence": 0.9,
                }
            ]
    else:
        first, last = paragraph_ids[0], paragraph_ids[-1]

        def field(summary: str, ids: list[str]) -> dict[str, Any]:
            return {"summary": summary, "evidence_paragraph_ids": ids}

        scene_id_matches = re.findall(r'"scene_id"\s*:\s*"([^"]+)"', combined)
        expected_scene = scene_id_matches[0] if scene_id_matches else (
            scene_ids[0] if scene_ids else f"{paragraph_ids[0].rsplit('-P', 1)[0]}-S0001"
        )
        payload = {
            "scene_id": expected_scene,
            "entry_state": field("进入场景", [first]),
            "goal": field("完成当前行动", [first]),
            "obstacle": field("", []),
            "key_actions": [{"summary": "推进情节", "evidence_paragraph_ids": [first]}],
            "turning_point": field("", []),
            "outcome": field("状态发生变化", [last]),
            "unresolved_question": field("", []),
            "function_tags": ["事件推进"],
            "confidence": 0.8,
        }
    return json.dumps(payload, ensure_ascii=False)


async def chapter_smoke_fake_generate(
    request: ModelRequest,
    *,
    provider_name: str,
    default_model: str,
) -> ModelResponse:
    if is_chapter_analysis_smoke_fake_fail_enabled():
        raise ProviderRequestError(
            "Chapter analysis smoke fake injected transport failure",
            http_status_code=0,
            http_request_sent=False,
            error_code="PROVIDER_TRANSPORT_ERROR",
            exception_type="SmokeFakeInjectedFailure",
            provider=provider_name,
            model=request.model or default_model,
            phase="provider_request",
            retryable=True,
            transport_kind=TRANSPORT_REMOTE_DISCONNECT,
            user_action_hint="这是开发 Smoke Fake 注入的可控传输失败，可重新分析。",
        )
    text = synthesize_chapter_smoke_fake_text(request)
    model = request.model or default_model
    # Stable zero-cost usage for smoke accounting.
    return ModelResponse(
        text=text,
        model=model,
        http_status_code=200,
        input_tokens=32,
        output_tokens=64,
        total_tokens=96,
        request_id=f"smoke-fake-{provider_name}",
        finish_reason="stop",
    )


__all__ = [
    "chapter_smoke_fake_generate",
    "chapter_smoke_fake_readiness_override",
    "is_chapter_analysis_smoke_fake_enabled",
    "is_chapter_analysis_smoke_fake_fail_enabled",
    "is_chapter_analysis_smoke_fake_requested",
    "synthesize_chapter_smoke_fake_text",
]
