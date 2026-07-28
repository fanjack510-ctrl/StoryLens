"""Public-side Sample S fixture for window analysis (CI independent of Private engine)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.narrative_core.contracts.whole_book_contract_v1 import (
    WHOLE_BOOK_CONTRACT_VERSION,
    AnalysisProvenanceV1,
    CandidateAssetV1,
    CandidateEntityAliasV1,
    CandidateEntityV1,
    CandidateEvidenceV1,
    CandidateNarrativeRefV1,
    CandidateRelationV1,
    EntityType,
    NarrativeRefKind,
    ResultOrigin,
    SnapshotEvidenceLocatorV1,
    WholeBookMode,
    WholeBookWindowAnalysisResponseV1,
    WholeBookWindowAnalysisRequestV1,
)
from app.narrative_core.contracts.whole_book_contract_v1.common import sha256_hex
from app.narrative_core.services.whole_book_minimal_helpers_v1 import (
    FIXTURE_ENGINE_ID,
    FIXTURE_ENGINE_VERSION,
    FIXTURE_PROMPT_VERSION,
)

SAMPLE_S_PARAGRAPH_TEXTS: tuple[str, ...] = (
    "林川在清晨收到一封没有署名的异常通知，信封上只有一行字：请勿独自调查。",
    "这座城市的档案系统存在一套从未写入公开手册的核心规则，普通人无法查阅。",
    "谁能在规则被改写之前找到源头？这个问题在林川心里挥之不去。",
    "林先生——邻居们仍这样称呼他——决定不再等待官方答复，开始整理线索。",
    "他在旧桥边见到苏岚，两人同意合作追踪通知来源，并交换了各自掌握的信息。",
    "苏岚说她的目标是查清通知背后的操控者，这个调查必须尽快推进。",
    "调查员周衡介入后，指出双方正在逼近同一套被隐藏的档案规则。",
    "主要冲突迅速升级：公开渠道被封锁，而核心规则即将被彻底改写。",
    "在最后一章的听证会上，核心问题得到初步回答，林川与苏岚暂时稳住局面。",
)


def _find_paragraph(request: WholeBookWindowAnalysisRequestV1, global_index: int):
    for paragraph in request.paragraphs:
        if paragraph.global_paragraph_index == global_index:
            return paragraph
    raise ValueError(f"paragraph global_index={global_index} not in window")


def _locator(request: WholeBookWindowAnalysisRequestV1, global_index: int, quote: str) -> SnapshotEvidenceLocatorV1:
    paragraph = _find_paragraph(request, global_index)
    start = paragraph.text.index(quote)
    end = start + len(quote)
    return SnapshotEvidenceLocatorV1(
        snapshot_id=request.snapshot.snapshot_id,
        snapshot_chapter_id=paragraph.snapshot_chapter_id,
        snapshot_paragraph_id=paragraph.snapshot_paragraph_id,
        chapter_id=paragraph.chapter_id,
        chapter_index=paragraph.chapter_index,
        paragraph_index=paragraph.paragraph_index,
        global_paragraph_index=paragraph.global_paragraph_index,
        start_offset=start,
        end_offset=end,
        quote_text=quote,
        quote_hash=sha256_hex(quote),
        paragraph_text_hash=paragraph.text_hash,
    )


def _provenance(request: WholeBookWindowAnalysisRequestV1) -> AnalysisProvenanceV1:
    return AnalysisProvenanceV1(
        run_id=request.run.run_id,
        snapshot_id=request.snapshot.snapshot_id,
        window_ids=[request.window.window_id],
        engine_id=FIXTURE_ENGINE_ID,
        engine_version=FIXTURE_ENGINE_VERSION,
        prompt_version=FIXTURE_PROMPT_VERSION,
        provider_id="counting-fake",
        model_name="counting-fake",
        result_origin=ResultOrigin.fixture,
        source_mode=WholeBookMode.whole_book_native,
        deterministic=True,
        config_hashes={"fixture": sha256_hex("sample-s")},
        generated_at=datetime.now(timezone.utc),
    )


def _evidence(key: str, locator: SnapshotEvidenceLocatorV1, confidence: float = 0.92) -> CandidateEvidenceV1:
    return CandidateEvidenceV1(evidence_key=key, locator=locator, confidence=confidence)


def build_fixture_window_analysis_response_v1(
    request: WholeBookWindowAnalysisRequestV1,
) -> WholeBookWindowAnalysisResponseV1:
    """Return deterministic Sample S payload for window_index 0..2."""
    idx = request.window.window_index
    prov = _provenance(request)
    entities: list[CandidateEntityV1] = []
    assets: list[CandidateAssetV1] = []
    evidences: list[CandidateEvidenceV1] = []
    relations: list[CandidateRelationV1] = []
    warnings: list[str] = []

    if idx == 0:
        ev1 = _evidence("ev-lc-notice", _locator(request, 0, "林川"))
        ev2 = _evidence("ev-setting-rule", _locator(request, 1, "核心规则"))
        ev3 = _evidence("ev-question-source", _locator(request, 2, "找到源头"))
        evidences.extend([ev1, ev2, ev3])
        entities.append(
            CandidateEntityV1(
                candidate_key="ent-linchuan",
                entity_type=EntityType.character,
                canonical_name="林川",
                confidence=0.95,
                evidence_keys=["ev-lc-notice"],
            )
        )
        assets.extend(
            [
                CandidateAssetV1(
                    candidate_key="asset-ev-notice",
                    asset_type="event",
                    title="林川收到异常通知",
                    summary="林川收到没有署名的异常通知。",
                    confidence=0.93,
                    subject_entity_keys=["ent-linchuan"],
                    evidence_keys=["ev-lc-notice"],
                    payload={
                        "event_type": "revelation",
                        "summary": "林川收到异常通知",
                        "participants": ["ent-linchuan"],
                        "cause_candidate_keys": [],
                        "prior_event_candidate_keys": [],
                        "chapter_start_index": 0,
                        "chapter_end_index": 0,
                        "core_evidence_key": "ev-lc-notice",
                    },
                ),
                CandidateAssetV1(
                    candidate_key="asset-setting-rule",
                    asset_type="setting_fact",
                    title="档案核心规则",
                    summary="档案系统存在未公开的核心规则。",
                    confidence=0.9,
                    evidence_keys=["ev-setting-rule"],
                    payload={"fact_text": "档案系统存在核心规则", "scope": "rule"},
                ),
                CandidateAssetV1(
                    candidate_key="asset-question-source",
                    asset_type="question",
                    title="规则源头悬念",
                    summary="谁能在规则被改写前找到源头？",
                    confidence=0.88,
                    evidence_keys=["ev-question-source"],
                    payload={"question_text": "谁能在规则被改写之前找到源头", "status": "open"},
                ),
                CandidateAssetV1(
                    candidate_key="asset-profile-lc",
                    asset_type="character_profile",
                    title="林川角色定位",
                    summary="收到异常通知并卷入调查。",
                    confidence=0.9,
                    subject_entity_keys=["ent-linchuan"],
                    evidence_keys=["ev-lc-notice"],
                    payload={
                        "role_in_window": "收到异常通知的调查者",
                        "explicit_traits": ["收到异常通知"],
                        "current_goal_candidate_keys": [],
                        "related_event_candidate_keys": ["asset-ev-notice"],
                    },
                ),
            ]
        )
    elif idx == 1:
        ev1 = _evidence("ev-lxs-alias", _locator(request, 3, "林先生"))
        ev2 = _evidence("ev-sulan-meet", _locator(request, 4, "苏岚"))
        ev3 = _evidence("ev-goal-sulan", _locator(request, 5, "查清通知背后的操控者"))
        evidences.extend([ev1, ev2, ev3])
        entities.extend(
            [
                CandidateEntityV1(
                    candidate_key="ent-linchuan",
                    entity_type=EntityType.character,
                    canonical_name="林川",
                    confidence=0.94,
                    evidence_keys=["ev-lxs-alias"],
                ),
                CandidateEntityV1(
                    candidate_key="ent-mrlin",
                    entity_type=EntityType.character,
                    canonical_name="林先生",
                    aliases=[
                        CandidateEntityAliasV1(
                            name="林先生",
                            confidence=0.94,
                            evidence_keys=["ev-lxs-alias"],
                        )
                    ],
                    confidence=0.94,
                    evidence_keys=["ev-lxs-alias"],
                ),
                CandidateEntityV1(
                    candidate_key="ent-sulan",
                    entity_type=EntityType.character,
                    canonical_name="苏岚",
                    confidence=0.93,
                    evidence_keys=["ev-sulan-meet"],
                ),
            ]
        )
        assets.extend(
            [
                CandidateAssetV1(
                    candidate_key="asset-decide-investigate",
                    asset_type="event",
                    title="林川决定调查",
                    summary="林川决定不再等待并开始整理线索。",
                    confidence=0.91,
                    subject_entity_keys=["ent-linchuan"],
                    evidence_keys=["ev-lxs-alias"],
                    payload={
                        "event_type": "decision",
                        "summary": "林川决定调查",
                        "participants": ["ent-linchuan"],
                        "cause_candidate_keys": [],
                        "prior_event_candidate_keys": ["asset-ev-notice"],
                        "chapter_start_index": 1,
                        "chapter_end_index": 1,
                        "core_evidence_key": "ev-lxs-alias",
                    },
                ),
                CandidateAssetV1(
                    candidate_key="asset-coop-sulan",
                    asset_type="event",
                    title="林川与苏岚合作",
                    summary="林川与苏岚在旧桥边达成合作。",
                    confidence=0.92,
                    subject_entity_keys=["ent-linchuan", "ent-sulan"],
                    evidence_keys=["ev-sulan-meet"],
                    payload={
                        "event_type": "action",
                        "summary": "林川与苏岚合作",
                        "participants": ["ent-linchuan", "ent-sulan"],
                        "cause_candidate_keys": [],
                        "prior_event_candidate_keys": ["asset-decide-investigate"],
                        "chapter_start_index": 1,
                        "chapter_end_index": 1,
                        "core_evidence_key": "ev-sulan-meet",
                    },
                ),
                CandidateAssetV1(
                    candidate_key="asset-goal-sulan",
                    asset_type="goal",
                    title="苏岚的调查目标",
                    summary="查清通知背后的操控者。",
                    confidence=0.9,
                    subject_entity_keys=["ent-sulan"],
                    evidence_keys=["ev-goal-sulan"],
                    payload={
                        "holder_candidate_key": "ent-sulan",
                        "goal_text": "查清通知背后的操控者",
                        "status": "active",
                    },
                ),
                CandidateAssetV1(
                    candidate_key="asset-profile-sulan",
                    asset_type="character_profile",
                    title="苏岚角色定位",
                    summary="与林川合作调查的合作者。",
                    confidence=0.89,
                    subject_entity_keys=["ent-sulan"],
                    evidence_keys=["ev-sulan-meet"],
                    payload={
                        "role_in_window": "合作调查者",
                        "explicit_traits": ["同意合作"],
                        "current_goal_candidate_keys": ["asset-goal-sulan"],
                        "related_event_candidate_keys": ["asset-coop-sulan"],
                    },
                ),
            ]
        )
        relations.append(
            CandidateRelationV1(
                candidate_key="rel-alias-lc",
                relation_type="alias_of",
                subject=CandidateNarrativeRefV1(kind=NarrativeRefKind.entity, candidate_key="ent-mrlin"),
                object=CandidateNarrativeRefV1(kind=NarrativeRefKind.entity, candidate_key="ent-linchuan"),
                confidence=0.94,
                evidence_keys=["ev-lxs-alias"],
                attributes={"alias_name": "林先生"},
            )
        )
        relations.append(
            CandidateRelationV1(
                candidate_key="rel-part-decide",
                relation_type="participates_in",
                subject=CandidateNarrativeRefV1(kind=NarrativeRefKind.entity, candidate_key="ent-linchuan"),
                object=CandidateNarrativeRefV1(kind=NarrativeRefKind.asset, candidate_key="asset-decide-investigate"),
                confidence=0.9,
                evidence_keys=["ev-lxs-alias"],
            )
        )
        relations.append(
            CandidateRelationV1(
                candidate_key="rel-part-coop",
                relation_type="participates_in",
                subject=CandidateNarrativeRefV1(kind=NarrativeRefKind.entity, candidate_key="ent-sulan"),
                object=CandidateNarrativeRefV1(kind=NarrativeRefKind.asset, candidate_key="asset-coop-sulan"),
                confidence=0.9,
                evidence_keys=["ev-sulan-meet"],
            )
        )
    else:
        ev1 = _evidence("ev-zhouheng", _locator(request, 6, "调查员周衡"))
        ev2 = _evidence("ev-conflict", _locator(request, 7, "主要冲突迅速升级"))
        ev3 = _evidence("ev-resolution", _locator(request, 8, "核心问题得到初步回答"))
        ev4 = _evidence("ev-setting2", _locator(request, 7, "核心规则"))
        evidences.extend([ev1, ev2, ev3, ev4])
        entities.extend(
            [
                CandidateEntityV1(
                    candidate_key="ent-linchuan",
                    entity_type=EntityType.character,
                    canonical_name="林川",
                    confidence=0.9,
                    evidence_keys=["ev-zhouheng"],
                ),
                CandidateEntityV1(
                    candidate_key="ent-sulan",
                    entity_type=EntityType.character,
                    canonical_name="苏岚",
                    confidence=0.88,
                    evidence_keys=["ev-conflict"],
                ),
                CandidateEntityV1(
                    candidate_key="ent-zhouheng",
                    entity_type=EntityType.character,
                    canonical_name="调查员周衡",
                    confidence=0.9,
                    evidence_keys=["ev-zhouheng"],
                ),
            ]
        )
        assets.extend(
            [
                CandidateAssetV1(
                    candidate_key="asset-zhouheng-join",
                    asset_type="event",
                    title="调查员周衡介入",
                    summary="调查员周衡介入调查并指出隐藏规则。",
                    confidence=0.9,
                    subject_entity_keys=["ent-zhouheng"],
                    evidence_keys=["ev-zhouheng"],
                    payload={
                        "event_type": "arrival",
                        "summary": "调查员周衡介入",
                        "participants": ["ent-zhouheng", "ent-linchuan", "ent-sulan"],
                        "cause_candidate_keys": [],
                        "prior_event_candidate_keys": ["asset-coop-sulan"],
                        "chapter_start_index": 2,
                        "chapter_end_index": 2,
                        "core_evidence_key": "ev-zhouheng",
                    },
                ),
                CandidateAssetV1(
                    candidate_key="asset-discover-rule",
                    asset_type="event",
                    title="发现核心规则",
                    summary="双方逼近被隐藏的档案规则。",
                    confidence=0.91,
                    subject_entity_keys=["ent-linchuan", "ent-sulan"],
                    evidence_keys=["ev-zhouheng"],
                    payload={
                        "event_type": "revelation",
                        "summary": "发现核心规则",
                        "participants": ["ent-linchuan", "ent-sulan", "ent-zhouheng"],
                        "cause_candidate_keys": [],
                        "prior_event_candidate_keys": ["asset-zhouheng-join"],
                        "chapter_start_index": 2,
                        "chapter_end_index": 2,
                        "core_evidence_key": "ev-zhouheng",
                    },
                ),
                CandidateAssetV1(
                    candidate_key="asset-conflict-escalate",
                    asset_type="conflict",
                    title="主要冲突升级",
                    summary="公开渠道被封锁，核心规则即将被改写。",
                    confidence=0.92,
                    subject_entity_keys=["ent-linchuan"],
                    evidence_keys=["ev-conflict"],
                    payload={
                        "side_a_candidate_keys": ["ent-linchuan", "ent-sulan"],
                        "side_b_candidate_keys": [],
                        "conflict_text": "公开渠道被封锁与规则改写",
                        "status": "escalated",
                    },
                ),
                CandidateAssetV1(
                    candidate_key="asset-event-conflict",
                    asset_type="event",
                    title="冲突升级事件",
                    summary="主要冲突迅速升级。",
                    confidence=0.9,
                    subject_entity_keys=["ent-linchuan"],
                    evidence_keys=["ev-conflict"],
                    payload={
                        "event_type": "conflict",
                        "summary": "冲突升级",
                        "participants": ["ent-linchuan", "ent-sulan"],
                        "cause_candidate_keys": [],
                        "prior_event_candidate_keys": ["asset-discover-rule"],
                        "chapter_start_index": 2,
                        "chapter_end_index": 2,
                        "core_evidence_key": "ev-conflict",
                    },
                ),
                CandidateAssetV1(
                    candidate_key="asset-final-resolution",
                    asset_type="event",
                    title="核心问题初步解决",
                    summary="听证会上核心问题得到初步回答。",
                    confidence=0.93,
                    subject_entity_keys=["ent-linchuan", "ent-sulan"],
                    evidence_keys=["ev-resolution"],
                    payload={
                        "event_type": "state_change",
                        "summary": "核心问题初步解决",
                        "participants": ["ent-linchuan", "ent-sulan"],
                        "cause_candidate_keys": [],
                        "prior_event_candidate_keys": ["asset-event-conflict"],
                        "chapter_start_index": 2,
                        "chapter_end_index": 2,
                        "core_evidence_key": "ev-resolution",
                    },
                ),
                CandidateAssetV1(
                    candidate_key="asset-setting-archive",
                    asset_type="setting_fact",
                    title="档案规则将被改写",
                    summary="核心规则面临被彻底改写。",
                    confidence=0.88,
                    evidence_keys=["ev-setting2"],
                    payload={"fact_text": "核心规则即将被彻底改写", "scope": "rule"},
                ),
                CandidateAssetV1(
                    candidate_key="asset-profile-zhou",
                    asset_type="character_profile",
                    title="调查员周衡角色定位",
                    summary="介入并指出隐藏规则的调查员。",
                    confidence=0.87,
                    subject_entity_keys=["ent-zhouheng"],
                    evidence_keys=["ev-zhouheng"],
                    payload={
                        "role_in_window": "官方调查员",
                        "explicit_traits": ["介入调查"],
                        "current_goal_candidate_keys": [],
                        "related_event_candidate_keys": ["asset-zhouheng-join"],
                    },
                ),
            ]
        )

    return WholeBookWindowAnalysisResponseV1(
        contract_version=WHOLE_BOOK_CONTRACT_VERSION,
        run_id=request.run.run_id,
        snapshot_id=request.snapshot.snapshot_id,
        window_id=request.window.window_id,
        entities=entities,
        assets=assets,
        evidences=evidences,
        relations=relations,
        warnings=warnings,
        provenance=prov,
    )


def build_fixture_window_payload_from_request_dict(payload: dict[str, Any]) -> dict[str, Any]:
    request = WholeBookWindowAnalysisRequestV1.model_validate(payload)
    response = build_fixture_window_analysis_response_v1(request)
    return response.model_dump(mode="json")
