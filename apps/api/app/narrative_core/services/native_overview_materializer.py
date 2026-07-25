"""Native Overview materializer (STEP 2.3-A3).

Hardened Entity merge / Asset dedupe / Evidence validation / retry-idempotent writes.
One window result → Entity + Asset + Evidence + StateVersion in a nested transaction.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisRun,
    BookSnapshotParagraph,
    NarrativeAssetVersion,
    NarrativeEntity,
    WholeBookRunStateVersion,
    WholeBookRunWindow,
    utc_now,
)
from app.narrative_core.contracts.pro_native_overview_flags import (
    FIXTURE_ENGINE_ID,
    FIXTURE_ENGINE_VERSION,
)
from app.narrative_core.contracts.whole_book_overview_errors import WholeBookOverviewErrorCode
from app.narrative_core.contracts.whole_book_overview_v1 import (
    PriorStateV1,
    StateDeltaV1,
    WholeBookOverviewWindowResultV1,
)
from app.narrative_core.enums import OriginType, OverviewProductionStageKey
from app.narrative_core.services.asset_evidence_service import NarrativeAssetEvidenceService
from app.narrative_core.services.asset_service import NarrativeAssetService
from app.narrative_core.services.entity_service import NarrativeEntityServiceImpl
from app.narrative_core.services.native_overview_errors import NativeOverviewError
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl

_PRIOR_BUCKETS = (
    "characters",
    "aliases",
    "protagonist_candidates",
    "goal_candidates",
    "conflict_candidates",
    "central_question_candidates",
    "major_event_candidates",
    "climax_candidates",
    "ending_state_candidates",
)


def _candidate_key(item: dict[str, Any]) -> str:
    for field in ("candidate_id", "id", "name", "alias", "summary"):
        value = item.get(field)
        if value is not None and str(value).strip():
            return f"{field}:{value}"
    return json.dumps(item, sort_keys=True, ensure_ascii=False)


def merge_prior_with_delta(prior: PriorStateV1, delta: StateDeltaV1) -> PriorStateV1:
    """Apply state_delta onto prior_state (in-memory; Public-owned)."""

    payload: dict[str, Any] = {"state_version": int(prior.state_version) + 1}
    for bucket in _PRIOR_BUCKETS:
        merged: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for item in list(getattr(prior, bucket) or []) + list(getattr(delta, bucket) or []):
            if not isinstance(item, dict):
                continue
            key = _candidate_key(item)
            if key not in merged:
                order.append(key)
                merged[key] = dict(item)
            else:
                merged[key].update({k: v for k, v in item.items() if v not in (None, "", [])})
        payload[bucket] = [merged[k] for k in order]
    return PriorStateV1.model_validate(payload)


def normalize_quote(text: str) -> str:
    return " ".join(str(text or "").split())


class NativeOverviewMaterializer:
    """Persist one window result with merge / dedupe / evidence gates."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._entities = NarrativeEntityServiceImpl(session)
        self._assets = NarrativeAssetService(session)
        self._evidence = NarrativeAssetEvidenceService(session)
        self._snapshots = BookSnapshotServiceImpl(session)

    def materialize_window(
        self,
        run: AnalysisRun,
        window: WholeBookRunWindow,
        window_result: WholeBookOverviewWindowResultV1,
        *,
        prior_state: PriorStateV1 | None = None,
    ) -> dict[str, Any]:
        assert run.book_id is not None and run.book_snapshot_id is not None
        snapshot_id = int(run.book_snapshot_id)
        book_id = int(run.book_id)
        prior = prior_state or PriorStateV1(state_version=int(window.state_version_before or 0))

        para_by_stable = self._paragraph_index(snapshot_id)
        evidence_by_id = {e.evidence_id: e for e in window_result.candidate_evidence}
        entity_map: dict[str, int] = {}
        asset_version_map: dict[str, int] = {}
        evidence_rows: list[dict[str, Any]] = []
        created_entities = 0
        reused_entities = 0
        created_assets = 0
        reused_assets = 0
        created_evidence = 0
        reused_evidence = 0

        with self._session.begin_nested():
            for ent in window_result.candidate_entities:
                entity, reused = self._upsert_entity(book_id, run, snapshot_id, ent)
                entity_map[ent.candidate_id] = int(entity.id)
                if reused:
                    reused_entities += 1
                else:
                    created_entities += 1
                for alias in ent.aliases:
                    self._entities.add_alias_candidate(
                        entity.id,
                        alias_text=alias,
                        source_run_id=run.id,
                        source_snapshot_id=snapshot_id,
                    )

            for asset in window_result.candidate_assets:
                version, reused = self._upsert_asset(book_id, run, snapshot_id, asset)
                asset_version_map[asset.candidate_id] = int(version.id)
                if reused:
                    reused_assets += 1
                else:
                    created_assets += 1

                for ev_id in asset.evidence_refs:
                    cand_ev = evidence_by_id.get(ev_id)
                    if cand_ev is None:
                        continue
                    snap_para = para_by_stable.get(cand_ev.paragraph_id)
                    if snap_para is None:
                        raise NativeOverviewError(
                            WholeBookOverviewErrorCode.EVIDENCE_INVALID.value,
                            f"evidence paragraph not in snapshot: {cand_ev.paragraph_id}",
                            run_id=str(run.id),
                            window_index=window.window_index,
                        )
                    text = self._snapshots.get_snapshot_paragraph_text(snap_para.id)
                    quote, start, end = self._locate_quote(text, cand_ev.quote)
                    row, ev_reused = self._upsert_evidence(
                        version.id,
                        snapshot_id=snapshot_id,
                        snap_para=snap_para,
                        start=start,
                        end=end,
                        evidence_role=cand_ev.evidence_role or "support",
                        evidence_label=cand_ev.evidence_id,
                    )
                    if ev_reused:
                        reused_evidence += 1
                    else:
                        created_evidence += 1
                    evidence_rows.append(
                        {
                            "evidence_id": cand_ev.evidence_id,
                            "db_id": row.id,
                            "paragraph_id": cand_ev.paragraph_id,
                            "chapter_id": cand_ev.chapter_id,
                            "quote": quote,
                            "confidence": cand_ev.confidence,
                            "snapshot_paragraph_id": snap_para.id,
                            "source_paragraph_id": snap_para.source_paragraph_id,
                            "stable_paragraph_id": snap_para.stable_paragraph_id,
                            "content_hash": snap_para.content_hash,
                            "chapter_index": None,
                            "paragraph_index": snap_para.paragraph_order,
                            "asset_candidate_id": asset.candidate_id,
                            "reused": ev_reused,
                        }
                    )

            next_state = merge_prior_with_delta(prior, window_result.state_delta)
            version_number = int(next_state.state_version)
            existing_state = self._session.scalar(
                select(WholeBookRunStateVersion).where(
                    WholeBookRunStateVersion.run_id == run.id,
                    WholeBookRunStateVersion.version_number == version_number,
                )
            )
            state_payload = {
                "entities": entity_map,
                "assets": asset_version_map,
                "prior_state": next_state.model_dump(mode="json"),
                "state_delta": window_result.state_delta.model_dump(mode="json"),
                "window_index": window.window_index,
            }
            state_hash = hashlib.sha256(
                json.dumps(state_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()
            if existing_state is None:
                self._session.add(
                    WholeBookRunStateVersion(
                        run_id=run.id,
                        version_number=version_number,
                        after_window_index=int(window.window_index),
                        state_json=json.dumps(state_payload, ensure_ascii=False),
                        state_hash=state_hash,
                        source_stage_key=OverviewProductionStageKey.MATERIALIZE_ASSETS.value,
                    )
                )
            else:
                existing_state.after_window_index = int(window.window_index)
                existing_state.state_json = json.dumps(state_payload, ensure_ascii=False)
                existing_state.state_hash = state_hash

            window.state_version_after = version_number

        self._session.flush()
        return {
            "window_result": window_result,
            "evidence_rows": evidence_rows,
            "entity_map": entity_map,
            "asset_version_map": asset_version_map,
            "prior_state": next_state,
            "stats": {
                "created_entities": created_entities,
                "reused_entities": reused_entities,
                "created_assets": created_assets,
                "reused_assets": reused_assets,
                "created_evidence": created_evidence,
                "reused_evidence": reused_evidence,
            },
        }

    def load_prior_state(self, run_id: int) -> PriorStateV1:
        row = self._session.scalar(
            select(WholeBookRunStateVersion)
            .where(WholeBookRunStateVersion.run_id == int(run_id))
            .order_by(WholeBookRunStateVersion.version_number.desc())
        )
        if row is None:
            return PriorStateV1(state_version=0)
        payload = json.loads(row.state_json or "{}")
        prior_raw = payload.get("prior_state")
        if isinstance(prior_raw, dict):
            return PriorStateV1.model_validate(prior_raw)
        return PriorStateV1(state_version=int(row.version_number or 0))

    def _paragraph_index(self, snapshot_id: int) -> dict[str, BookSnapshotParagraph]:
        paras = list(
            self._session.scalars(
                select(BookSnapshotParagraph).where(
                    BookSnapshotParagraph.snapshot_id == snapshot_id
                )
            )
        )
        index: dict[str, BookSnapshotParagraph] = {}
        for p in paras:
            for key in (
                p.stable_paragraph_id,
                p.source_paragraph_id,
                str(p.id),
            ):
                if key:
                    index[str(key)] = p
        return index

    def _upsert_entity(
        self,
        book_id: int,
        run: AnalysisRun,
        snapshot_id: int,
        ent: Any,
    ) -> tuple[NarrativeEntity, bool]:
        from app.narrative_core.services.entity_repository import normalize_alias_text

        normalized = normalize_alias_text(ent.canonical_name)
        matches = self._entities._repo.find_entities_by_normalized_name(book_id, normalized)
        same_type = [m for m in matches if m.entity_type == ent.entity_type]
        if same_type:
            return same_type[0], True
        entity = self._entities.create_entity(
            book_id,
            entity_type=ent.entity_type,
            canonical_name=ent.canonical_name,
            created_by=FIXTURE_ENGINE_ID,
        )
        return entity, False

    def _upsert_asset(
        self,
        book_id: int,
        run: AnalysisRun,
        snapshot_id: int,
        asset: Any,
    ) -> tuple[NarrativeAssetVersion, bool]:
        fingerprint = asset.deduplication_key or asset.candidate_id
        existing = self._session.scalar(
            select(NarrativeAssetVersion)
            .where(
                NarrativeAssetVersion.run_id == run.id,
                NarrativeAssetVersion.source_fingerprint == fingerprint,
            )
            .order_by(NarrativeAssetVersion.id.asc())
        )
        if existing is not None:
            return existing, True

        result = self._assets.create_candidate_asset(
            book_id,
            asset_type=asset.asset_type,
            title=asset.title or asset.candidate_id,
            summary=asset.summary,
            run_id=run.id,
            book_snapshot_id=snapshot_id,
            identity_fingerprint=fingerprint,
            confidence=asset.confidence,
            origin_type=OriginType.SYSTEM,
            attributes_json=json.dumps(
                {
                    "candidate_id": asset.candidate_id,
                    "engine_id": FIXTURE_ENGINE_ID,
                    "engine_version": FIXTURE_ENGINE_VERSION,
                    "window_materialized_at": utc_now().isoformat(),
                },
                ensure_ascii=False,
            ),
            source_fingerprint=fingerprint,
            reuse_existing_key=True,
        )
        return result.version, False

    def _upsert_evidence(
        self,
        asset_version_id: int,
        *,
        snapshot_id: int,
        snap_para: BookSnapshotParagraph,
        start: int,
        end: int,
        evidence_role: str,
        evidence_label: str,
    ) -> tuple[Any, bool]:
        existing_rows = self._evidence.list_asset_version_evidence(asset_version_id)
        for row in existing_rows:
            if (
                int(row.snapshot_paragraph_id) == int(snap_para.id)
                and str(row.evidence_role or "") == evidence_role
                and str(row.evidence_label or "") == evidence_label
            ):
                return row, True
        row = self._evidence.attach_asset_evidence(
            asset_version_id,
            book_snapshot_id=snapshot_id,
            snapshot_chapter_id=int(snap_para.snapshot_chapter_id),
            snapshot_paragraph_id=int(snap_para.id),
            paragraph_content_hash=snap_para.content_hash,
            start_offset=start,
            end_offset=end,
            evidence_role=evidence_role,
            evidence_label=evidence_label,
            actor="model",
        )
        return row, False

    @staticmethod
    def _locate_quote(text: str, quote: str) -> tuple[str, int, int]:
        raw = str(quote or "")
        if not raw:
            raise NativeOverviewError(
                WholeBookOverviewErrorCode.EVIDENCE_INVALID.value,
                "evidence quote is empty",
            )
        start = text.find(raw)
        if start >= 0:
            return raw, start, start + len(raw)
        # Allow whitespace-normalized match only when the normalized quote is a
        # contiguous substring of the normalized paragraph — still refuse forge.
        norm_text = normalize_quote(text)
        norm_quote = normalize_quote(raw)
        if norm_quote and norm_quote in norm_text:
            # Prefer exact contiguous raw match after collapsing internal spaces
            # by scanning for the first significant token.
            token = raw.strip().split()[0] if raw.strip().split() else raw.strip()
            approx = text.find(token) if token else -1
            if approx >= 0:
                # Reconstruct end by consuming the same number of non-space chars.
                needed = len(norm_quote.replace(" ", ""))
                seen = 0
                end = approx
                while end < len(text) and seen < needed:
                    if not text[end].isspace():
                        seen += 1
                    end += 1
                return text[approx:end], approx, end
        raise NativeOverviewError(
            WholeBookOverviewErrorCode.EVIDENCE_INVALID.value,
            "evidence quote not found in paragraph text",
            details={"quote_preview": raw[:80]},
        )


__all__ = [
    "NativeOverviewMaterializer",
    "merge_prior_with_delta",
    "normalize_quote",
]
