"""Public-side Sample S overview synthesis fixture."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.narrative_core.contracts.whole_book_contract_v1 import (
    BOOK_OVERVIEW_CLAIM_KEYS_V1,
    BOOK_OVERVIEW_RESULT_VERSION,
    WHOLE_BOOK_CONTRACT_VERSION,
    AnalysisProvenanceV1,
    BookOverviewClaimV1,
    BookOverviewResultV1,
    OverviewClaimAvailability,
    ResultOrigin,
    WholeBookMode,
    WholeBookSynthesisRequestV1,
    WholeBookSynthesisResponseV1,
)
from app.narrative_core.contracts.whole_book_contract_v1.common import sha256_hex
from app.narrative_core.services.whole_book_minimal_helpers_v1 import (
    OVERVIEW_ENGINE_ID,
    OVERVIEW_PROMPT_VERSION,
)


def build_fixture_overview_response_v1(
    request: WholeBookSynthesisRequestV1,
    *,
    entity_name_to_id: dict[str, int],
    asset_title_to_id: dict[str, int],
    evidence_ids: list[int],
    key_event_asset_ids: list[int],
    important_entity_ids: list[int],
) -> WholeBookSynthesisResponseV1:
    protagonist_id = entity_name_to_id.get("林川") or (important_entity_ids[0] if important_entity_ids else None)
    setting_asset = asset_title_to_id.get("档案核心规则") or next(iter(asset_title_to_id.values()), None)
    event_asset = asset_title_to_id.get("林川收到异常通知") or key_event_asset_ids[0] if key_event_asset_ids else None
    goal_asset = asset_title_to_id.get("苏岚的调查目标")
    conflict_asset = asset_title_to_id.get("主要冲突升级")
    question_asset = asset_title_to_id.get("规则源头悬念")
    final_event = asset_title_to_id.get("核心问题初步解决")
    ev_sample = evidence_ids[:3] if evidence_ids else [1]

    def claim(
        key: str,
        summary: str,
        *,
        availability: OverviewClaimAvailability = OverviewClaimAvailability.available,
        asset_ids: list[int] | None = None,
        confidence: float | None = 0.85,
    ) -> BookOverviewClaimV1:
        aids = [aid for aid in (asset_ids or []) if aid]
        eids = [eid for eid in ev_sample if eid]
        if availability == OverviewClaimAvailability.available and (not aids or not eids):
            availability = OverviewClaimAvailability.insufficient_evidence
            summary = summary if aids or eids else "当前证据不足以形成确定结论。"
            confidence = None
        return BookOverviewClaimV1(
            claim_key=key,  # type: ignore[arg-type]
            availability=availability,
            summary=summary,
            confidence=confidence,
            evidence_ids=eids,
            supporting_asset_ids=aids,
        )

    claims = [
        claim(
            "genre_and_narrative_features",
            "合成样本呈现调查悬疑叙事，围绕隐藏规则与多方合作推进。",
            asset_ids=[aid for aid in [setting_asset, event_asset, question_asset] if aid],
        ),
        claim(
            "core_setting",
            "故事依赖一套未公开的档案核心规则。",
            asset_ids=[aid for aid in [setting_asset] if aid],
        ),
        claim(
            "protagonist",
            "林川是贯穿窗口调查与合作推进的中心人物。",
            asset_ids=[aid for aid in [event_asset] if aid],
        ),
        claim(
            "protagonist_core_goal",
            "主角与同伴目标指向查清通知与规则源头。",
            asset_ids=[aid for aid in [goal_asset, event_asset] if aid],
        ),
        claim(
            "main_conflict",
            "公开渠道封锁与规则改写构成主要矛盾。",
            asset_ids=[aid for aid in [conflict_asset, event_asset] if aid],
        ),
        claim(
            "core_question",
            "作品核心悬念是谁能在规则被改写前找到源头。",
            asset_ids=[aid for aid in [question_asset] if aid],
        ),
        claim(
            "final_resolution",
            "末尾听证会上核心问题得到初步回答，局面暂时稳住。",
            asset_ids=[aid for aid in [final_event] if aid],
        ),
        claim(
            "important_characters",
            "重要人物包括林川、苏岚与调查员周衡，分别承担调查、合作与官方介入。",
            asset_ids=[aid for aid in list(asset_title_to_id.values())[:3] if aid],
        ),
        claim(
            "key_events",
            "关键事件链从异常通知、决定调查、合作、规则发现、冲突升级到初步解决。",
            asset_ids=key_event_asset_ids[:6],
        ),
    ]
    assert len(claims) == len(BOOK_OVERVIEW_CLAIM_KEYS_V1)

    provenance = AnalysisProvenanceV1(
        run_id=request.run.run_id,
        snapshot_id=request.snapshot.snapshot_id,
        window_ids=[],
        engine_id=OVERVIEW_ENGINE_ID,
        engine_version="1.0.0",
        prompt_version=OVERVIEW_PROMPT_VERSION,
        provider_id="counting-fake",
        model_name="counting-fake",
        result_origin=ResultOrigin.fixture,
        source_mode=WholeBookMode.whole_book_native,
        deterministic=True,
        config_hashes={"fixture": sha256_hex("sample-s-overview")},
        generated_at=datetime.now(timezone.utc),
    )

    result = BookOverviewResultV1(
        run_id=request.run.run_id,
        book_id=request.run.book_id,
        snapshot_id=request.snapshot.snapshot_id,
        mode=WholeBookMode.whole_book_native,
        result_origin=ResultOrigin.fixture,
        status="completed",
        claims=claims,
        important_entity_ids=important_entity_ids[:12],
        key_event_asset_ids=sorted(key_event_asset_ids)[:20],
        coverage=request.coverage,
        input_usage=request.run.input_usage,
        warnings=[],
        provenance=provenance,
        created_at=datetime.now(timezone.utc),
    )
    return WholeBookSynthesisResponseV1(result=result)


def build_fixture_overview_payload_from_request_dict(
    payload: dict[str, Any],
    *,
    entity_name_to_id: dict[str, int],
    asset_title_to_id: dict[str, int],
    evidence_ids: list[int],
    key_event_asset_ids: list[int],
    important_entity_ids: list[int],
) -> dict[str, Any]:
    request = WholeBookSynthesisRequestV1.model_validate(payload)
    response = build_fixture_overview_response_v1(
        request,
        entity_name_to_id=entity_name_to_id,
        asset_title_to_id=asset_title_to_id,
        evidence_ids=evidence_ids,
        key_event_asset_ids=key_event_asset_ids,
        important_entity_ids=important_entity_ids,
    )
    return response.model_dump(mode="json")
