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

import asyncio
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
_JOURNEY_FAKE_MODE_ENV = "STORYLENS_JOURNEY_FAKE_MODE"
_VALID_JOURNEY_FAKE_MODES = {
    "success",
    "initial_truncation_then_success",
    "repair_success",
    "repair_failure",
}
_logger = logging.getLogger(__name__)
_rejection_logged = False


def _env_truthy(name: str) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def journey_smoke_fake_mode() -> str:
    """Manual-gate Journey Fake mode. Default: success."""
    raw = (os.environ.get(_JOURNEY_FAKE_MODE_ENV) or "success").strip().lower()
    if raw not in _VALID_JOURNEY_FAKE_MODES:
        return "success"
    return raw


def is_chapter_analysis_smoke_fake_requested() -> bool:
    """Raw env request — does not apply production safety."""
    return _env_truthy(_SMOKE_FAKE_ENV)


def is_chapter_analysis_smoke_fake_fail_enabled() -> bool:
    return _env_truthy(_SMOKE_FAIL_ENV)


def is_chapter_analysis_smoke_fake_rematerialize_stub_enabled() -> bool:
    """When Fake is on, rematerialize may attach stub scene_analysis artifacts.

    CHG-015 wait-gate MG sets ``STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE_SKIP_REMATERIALIZE_STUBS=1``
    so edited spans remain incomplete and exercise post-confirm analyze → journey.
    """
    if not is_chapter_analysis_smoke_fake_enabled():
        return False
    if _env_truthy("STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE_SKIP_REMATERIALIZE_STUBS"):
        return False
    return True


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
    # Journey profiles_target style: {"id":"B0001-C0001-P0001","text":"..."}
    for match in re.finditer(
        r'"id"\s*:\s*"(B\d+-C\d+-P\d+)"\s*,\s*"text"\s*:\s*"((?:\\.|[^"\\])*)"',
        text,
        flags=re.S,
    ):
        mapping.setdefault(
            match.group(1), bytes(match.group(2), "utf-8").decode("unicode_escape")
        )
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


def _scene_targets_from_prompt(text: str) -> list[dict[str, Any]]:
    """Extract scene_id/ordinal/paragraph_ids from journey prompt JSON."""
    targets: list[dict[str, Any]] = []
    for match in re.finditer(
        r'\{\s*"scene_id"\s*:\s*(\d+)\s*,\s*"scene_ordinal"\s*:\s*(\d+)[^\}]*?"paragraphs"\s*:\s*\[(.*?)\]',
        text,
        flags=re.S,
    ):
        sid = int(match.group(1))
        ordinal = int(match.group(2))
        pids = _paragraph_ids_from_text(match.group(3))
        targets.append({"scene_id": sid, "scene_ordinal": ordinal, "paragraph_ids": pids})
    if targets:
        seen: set[int] = set()
        ordered: list[dict[str, Any]] = []
        for item in targets:
            ordinal = int(item["scene_ordinal"])
            if ordinal in seen:
                continue
            seen.add(ordinal)
            ordered.append(item)
        return ordered

    pairs = re.findall(
        r'"scene_id"\s*:\s*(\d+)[^}]{0,160}?"scene_ordinal"\s*:\s*(\d+)',
        text,
        flags=re.S,
    )
    if not pairs:
        pairs = re.findall(
            r'"scene_ordinal"\s*:\s*(\d+)[^}]{0,160}?"scene_id"\s*:\s*(\d+)',
            text,
            flags=re.S,
        )
        pairs = [(sid, ord_) for ord_, sid in pairs]
    out: list[dict[str, Any]] = []
    seen_ord: set[int] = set()
    for sid_s, ord_s in pairs:
        ordinal = int(ord_s)
        if ordinal in seen_ord:
            continue
        seen_ord.add(ordinal)
        out.append({"scene_id": int(sid_s), "scene_ordinal": ordinal, "paragraph_ids": []})
    return out


def _expected_scene_ids_from_prompt(text: str, fallback_ids: list[int]) -> list[int]:
    match = re.search(r"expected scenes\s*\[([^\]]*)\]", text, flags=re.I)
    if match:
        ids = [int(x) for x in re.findall(r"\d+", match.group(1))]
        if ids:
            return ids
    for pattern in (
        r'"owned_scene_ids(?:_json)?"\s*:\s*"?\[([^\]]*)\]"?',
        r"owned_scene_ids_json[^\[]*\[([^\]]*)\]",
    ):
        match = re.search(pattern, text)
        if match:
            ids = [int(x) for x in re.findall(r"\d+", match.group(1))]
            if ids:
                return ids
    missing = [int(x) for x in re.findall(r"missing scene_id\s+(\d+)", text, flags=re.I)]
    if missing:
        preferred = [sid for sid in fallback_ids if sid in set(missing)]
        return preferred or missing
    return fallback_ids


def _evidence_for_scene(paragraph_ids: list[str], global_paragraphs: list[str]) -> list[str]:
    if paragraph_ids:
        return [paragraph_ids[0]]
    if global_paragraphs:
        return [global_paragraphs[0]]
    # Never invent a fixed chapter paragraph id — callers must supply real ids.
    return []


def _build_journey_profiles(
    combined: str,
    paragraph_ids: list[str],
    texts: dict[str, str],
) -> list[dict[str, Any]]:
    mode = journey_smoke_fake_mode()
    targets = _scene_targets_from_prompt(combined)
    fallback_ids = [int(t["scene_id"]) for t in targets]
    expected_ids = _expected_scene_ids_from_prompt(combined, fallback_ids)
    is_repair = (
        "structural_repair" in combined
        or "expected scenes" in combined.lower()
        or "missing scene_id" in combined.lower()
    )
    if mode == "repair_failure" and is_repair and expected_ids:
        expected_ids = expected_ids[:1]

    by_id = {int(t["scene_id"]): t for t in targets}
    profiles: list[dict[str, Any]] = []
    seen: set[int] = set()
    # Success Fake must emit exactly the requested/owned scene ids — never a fixed [1].
    emit_ids = list(expected_ids or fallback_ids)
    if not emit_ids:
        return profiles
    for index, sid in enumerate(emit_ids):
        if sid in seen:
            continue
        seen.add(sid)
        target = by_id.get(sid)
        ordinal = int(target["scene_ordinal"]) if target else (index + 1)
        scene_paras = list(target["paragraph_ids"]) if target else []
        evidence = _evidence_for_scene(scene_paras, paragraph_ids if not scene_paras else scene_paras)
        if not evidence and scene_paras:
            evidence = [scene_paras[0]]
        profiles.append(_scene_profile_item(int(sid), ordinal, evidence, texts))
    return profiles


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


_FAKE_SCENE_SPECS: list[dict[str, Any]] = [
    {
        "scene_role": "setup",
        "summary": "开篇交代人物处境与章节初始疑问，为后续冲突埋线。",
        "levels": {
            "curiosity": 2,
            "tension": 1,
            "emotional_investment": 2,
            "pacing_speed": 2,
            "hook": 3,
            "payoff": 1,
            "information_gain": 2,
        },
        "insights": {
            "overall_reading": "综合阅读贡献偏稳；读者主要在建立章节初始认知，继续阅读动力一般。",
            "plot_progression": "剧情推进偏弱；事件变化有限，更多是在交代背景与人物处境。",
            "reading_tension": "阅读张力偏弱；悬念与不确定性尚未充分建立。",
            "emotional_intensity": "情绪强度偏弱；读者尚未被强烈情感牵动。",
            "hook_payoff": "钩子刚提出而回报不足，问题链处于开启阶段。",
            "pacing_speed": "节奏速度偏慢；叙述偏缓，符合铺垫场景的信息铺设需要。",
        },
    },
    {
        "scene_role": "transition",
        "summary": "场景切换与信息过渡，为下一段冲突积蓄势能。",
        "levels": {
            "curiosity": 2,
            "tension": 2,
            "emotional_investment": 2,
            "pacing_speed": 4,
            "hook": 2,
            "payoff": 1,
            "information_gain": 1,
        },
        "insights": {
            "overall_reading": "综合阅读贡献有限；过渡段推进快但剧情增量不大，整体拉动一般。",
            "plot_progression": "剧情推进偏弱；场景切换完成但实质事件变化不多。",
            "reading_tension": "阅读张力中等；危险感尚未明显抬升。",
            "emotional_intensity": "情绪强度偏弱；读者更多在跟随场景位移。",
            "hook_payoff": "钩子延续有限，回报几乎未落地，问题仍待后续回应。",
            "pacing_speed": "节奏速度偏快；叙事推进快于信息增量，存在空转风险。",
        },
    },
    {
        "scene_role": "escalation",
        "summary": "冲突抬升，人物做出关键反应，情绪投入明显增强。",
        "levels": {
            "curiosity": 3,
            "tension": 2,
            "emotional_investment": 4,
            "pacing_speed": 3,
            "hook": 3,
            "payoff": 2,
            "information_gain": 3,
        },
        "insights": {
            "overall_reading": "综合阅读贡献中等偏上；情绪投入增强，但悬念压力尚未同步抬升。",
            "plot_progression": "剧情推进中等；冲突有抬升，目标与状态出现可见变化。",
            "reading_tension": "阅读张力偏弱；尽管冲突升级，等待感与不确定性仍不高。",
            "emotional_intensity": "情绪强度偏强；读者对人物处境产生较明显的情感反应。",
            "hook_payoff": "钩子持续存在，回报有限，问题链仍在推进中。",
            "pacing_speed": "节奏速度中等；推进与情绪渲染大致平衡。",
        },
    },
    {
        "scene_role": "reveal",
        "summary": "关键信息揭露，部分前文疑问得到回应但仍留余波。",
        "levels": {
            "curiosity": 3,
            "tension": 3,
            "emotional_investment": 3,
            "pacing_speed": 3,
            "hook": 3,
            "payoff": 3,
            "information_gain": 4,
        },
        "insights": {
            "overall_reading": "综合阅读贡献较好；信息揭露带来阶段性满足，同时引出新的阅读期待。",
            "plot_progression": "剧情推进偏强；关键信息落地，故事状态发生实质变化。",
            "reading_tension": "阅读张力中等；真相揭晓后悬念压力有所释放。",
            "emotional_intensity": "情绪强度中等；揭晓带来冲击但尚未达到情绪峰值。",
            "hook_payoff": "钩子与回报部分呼应，问题链处于部分兑现阶段。",
            "pacing_speed": "节奏速度中等；信息披露与场景反应节奏匹配。",
        },
    },
    {
        "scene_role": "climax",
        "summary": "章节冲突高点，悬念与回报同时抬升，阅读动力达到峰值。",
        "levels": {
            "curiosity": 4,
            "tension": 5,
            "emotional_investment": 4,
            "pacing_speed": 4,
            "hook": 4,
            "payoff": 4,
            "information_gain": 4,
        },
        "insights": {
            "overall_reading": "综合阅读贡献偏强；多维度同步抬升，读者继续阅读动力达到峰值。",
            "plot_progression": "剧情推进偏强；核心冲突集中爆发，故事状态剧烈变化。",
            "reading_tension": "阅读张力偏强；等待、危险与不确定性同时拉满。",
            "emotional_intensity": "情绪强度偏强；高潮段情绪反应强烈且持续。",
            "hook_payoff": "钩子与回报同步抬升，问题链在高潮段得到有效回应。",
            "pacing_speed": "节奏速度偏快；动作与信息密集，符合高潮场景预期。",
        },
    },
    {
        "scene_role": "aftermath",
        "summary": "高潮余波消化，读者情绪回落并承接下一章悬念。",
        "levels": {
            "curiosity": 2,
            "tension": 2,
            "emotional_investment": 3,
            "pacing_speed": 2,
            "hook": 2,
            "payoff": 3,
            "information_gain": 2,
        },
        "insights": {
            "overall_reading": "综合阅读贡献回落；高潮后进入消化段，整体拉动趋于平稳。",
            "plot_progression": "剧情推进偏弱；主要在处理高潮后果，增量事件有限。",
            "reading_tension": "阅读张力偏弱；紧张感释放，读者处于阶段性安全区。",
            "emotional_intensity": "情绪强度中等；余波仍有余温但不再持续加压。",
            "hook_payoff": "部分钩子已回应，仍有问题留给后续章节。",
            "pacing_speed": "节奏速度偏慢；停顿与观察增多，帮助读者消化高潮。",
        },
    },
]


def _fake_scene_spec(scene_ordinal: int) -> dict[str, Any]:
    index = (max(1, scene_ordinal) - 1) % len(_FAKE_SCENE_SPECS)
    return _FAKE_SCENE_SPECS[index]


def _scene_profile_item(
    scene_id: int,
    scene_ordinal: int,
    paragraph_ids: list[str],
    texts: dict[str, str],
) -> dict[str, Any]:
    """Build SceneReaderJourneyProfileItemV2-compatible payload (contract 2.0)."""
    spec = _fake_scene_spec(scene_ordinal)
    scene_role = str(spec["scene_role"])
    level_overrides = dict(spec.get("levels") or {})
    evidence_ids = list(dict.fromkeys(paragraph_ids))[:16]
    fields = {
        key: _scored_level(
            level_overrides.get(key, 2 if key not in {"cognitive_load", "redundancy"} else 1),
            evidence_ids,
            rationale=f"smoke-fake {key} for scene {scene_ordinal}",
        )
        for key in _LEVEL_KEYS
    }
    first = paragraph_ids[0] if paragraph_ids else ""
    summary_seed = _quote_for(first, texts) if first else f"场景{scene_ordinal}"
    summary = str(spec.get("summary") or summary_seed)[:160]
    return {
        "scene_id": int(scene_id),
        "scene_ordinal": int(scene_ordinal),
        "node_type": "scene",
        "scene_role": scene_role,
        "scene_value_summary": summary,
        "confidence": 0.8,
        "evidence_paragraph_ids": evidence_ids,
        "dimension_insights": dict(spec.get("insights") or {}),
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
        profiles = _build_journey_profiles(combined, paragraph_ids, texts)
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


def chapter_smoke_fake_delay_seconds() -> float:
    """Optional per-call delay for Manual Gate wait-gate observation (CHG-015)."""
    raw = (os.environ.get("STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE_DELAY_SECONDS") or "0").strip()
    try:
        value = float(raw)
    except ValueError:
        return 0.0
    return max(0.0, min(value, 30.0))


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
    delay = chapter_smoke_fake_delay_seconds()
    if delay > 0:
        await asyncio.sleep(delay)
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


def validate_manual_gate_journey_fixture_v1(
    *,
    scene_specs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Preflight for Manual Gate Journey Fake (success mode).

    Raises ``RuntimeError`` with code ``MANUAL_GATE_FAKE_FIXTURE_INVALID`` on failure.
    """
    if not is_chapter_analysis_smoke_fake_enabled():
        raise RuntimeError("MANUAL_GATE_FAKE_FIXTURE_INVALID: smoke fake not enabled")
    if is_chapter_analysis_smoke_fake_fail_enabled():
        raise RuntimeError("MANUAL_GATE_FAKE_FIXTURE_INVALID: fail-inject enabled")
    mode = journey_smoke_fake_mode()
    if mode == "repair_failure":
        raise RuntimeError(
            "MANUAL_GATE_FAKE_FIXTURE_INVALID: default mode must not be repair_failure"
        )

    specs = scene_specs or [
        {
            "scene_id": index,
            "scene_ordinal": index,
            "paragraph_ids": [f"B0001-C0001-P{index * 5 - 4:04d}", f"B0001-C0001-P{index * 5:04d}"],
        }
        for index in range(1, 5)
    ]
    profiles_target = []
    for spec in specs:
        pids = list(spec["paragraph_ids"])
        profiles_target.append(
            {
                "scene_id": int(spec["scene_id"]),
                "scene_ordinal": int(spec["scene_ordinal"]),
                "paragraphs": [{"id": pid, "text": f"text-{pid}"} for pid in pids],
            }
        )
    owned = [int(s["scene_id"]) for s in specs]
    batch_prompt = (
        "读者阅读旅程 scene_profiles contract_version 2.0\n"
        + json.dumps(
            {
                "profiles_target": profiles_target,
                "owned_scene_ids_json": json.dumps(owned),
            },
            ensure_ascii=False,
        )
    )
    repair_prompt = (
        batch_prompt
        + f"\nstructural_repair expected scenes {owned}\n"
        + "\n".join(f"missing scene_id {sid}" for sid in owned)
    )
    batch_req = ModelRequest(messages=[{"role": "user", "content": batch_prompt}], model="qwen-plus")
    repair_req = ModelRequest(messages=[{"role": "user", "content": repair_prompt}], model="qwen-plus")
    batch = json.loads(synthesize_chapter_smoke_fake_text(batch_req))
    repair = json.loads(synthesize_chapter_smoke_fake_text(repair_req))
    batch_profiles = batch.get("profiles") or []
    repair_profiles = repair.get("profiles") or []
    batch_ids = [int(p["scene_id"]) for p in batch_profiles]
    repair_ids = [int(p["scene_id"]) for p in repair_profiles]
    if sorted(batch_ids) != sorted(owned):
        raise RuntimeError(
            f"MANUAL_GATE_FAKE_FIXTURE_INVALID: batch ids {batch_ids} != {owned}"
        )
    if sorted(repair_ids) != sorted(owned):
        raise RuntimeError(
            f"MANUAL_GATE_FAKE_FIXTURE_INVALID: repair ids {repair_ids} != {owned}"
        )
    by_spec = {int(s["scene_id"]): set(s["paragraph_ids"]) for s in specs}
    for profile in batch_profiles + repair_profiles:
        sid = int(profile["scene_id"])
        evidence = list(profile.get("evidence_paragraph_ids") or [])
        if not evidence:
            raise RuntimeError(f"MANUAL_GATE_FAKE_FIXTURE_INVALID: empty evidence scene={sid}")
        allowed = by_spec.get(sid) or set()
        for pid in evidence:
            if allowed and pid not in allowed:
                raise RuntimeError(
                    f"MANUAL_GATE_FAKE_FIXTURE_INVALID: evidence {pid} out of scene {sid}"
                )
    return {
        "ok": True,
        "mode": mode,
        "scene_ids": owned,
        "batch_ids": batch_ids,
        "repair_ids": repair_ids,
        "provider_mode": "fake",
    }


__all__ = [
    "chapter_smoke_fake_generate",
    "chapter_smoke_fake_readiness_override",
    "is_chapter_analysis_smoke_fake_enabled",
    "is_chapter_analysis_smoke_fake_fail_enabled",
    "is_chapter_analysis_smoke_fake_requested",
    "journey_smoke_fake_mode",
    "synthesize_chapter_smoke_fake_text",
    "validate_manual_gate_journey_fixture_v1",
]
