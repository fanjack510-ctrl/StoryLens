"""Confirmed narrative entity/asset protection (WB-1.10)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisConflict,
    NarrativeAsset,
    NarrativeAssetVersion,
    NarrativeEntity,
    utc_now,
)
from app.narrative_core.asset_key import build_asset_key
from app.narrative_core.enums import ConflictStatus, ConflictType, OriginType, ReviewStatus
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)


def _entity_endpoint_asset_key(book_id: int, entity_id: int) -> str:
    return build_asset_key(
        book_id=book_id,
        asset_type="character_profile",
        stable_label=f"endpoint:{entity_id}",
    )


def _get_canonical_version(session: Session, asset_id: int) -> NarrativeAssetVersion | None:
    return session.scalar(
        select(NarrativeAssetVersion).where(
            NarrativeAssetVersion.asset_id == asset_id,
            NarrativeAssetVersion.is_canonical.is_(True),
        )
    )


def _confirmed_version(session: Session, asset_id: int) -> NarrativeAssetVersion | None:
    version = _get_canonical_version(session, asset_id)
    if version is None:
        return None
    if version.review_status == ReviewStatus.CONFIRMED.value:
        return version
    attrs = json.loads(version.attributes_json or "{}")
    if attrs.get("state") == "confirmed":
        return version
    return None


def confirm_narrative_entity_v1(session: Session, entity_id: int, *, user_id: str = "user") -> dict[str, Any]:
    entity = session.get(NarrativeEntity, entity_id)
    if entity is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND,
            f"entity not found: {entity_id}",
        )
    asset_key = _entity_endpoint_asset_key(entity.book_id, entity.id)
    asset = session.scalar(
        select(NarrativeAsset).where(
            NarrativeAsset.book_id == entity.book_id,
            NarrativeAsset.asset_key == asset_key,
        )
    )
    if asset is None:
        asset = NarrativeAsset(
            book_id=entity.book_id,
            asset_key=asset_key,
            lifecycle_status="active",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(asset)
        session.flush()
    now = utc_now()
    canonical = _get_canonical_version(session, asset.id)
    if canonical is not None:
        canonical.is_canonical = False
        session.flush()
    version = NarrativeAssetVersion(
        asset_id=asset.id,
        asset_type="character_profile",
        title=entity.canonical_name,
        summary=f"Confirmed entity profile for {entity.canonical_name}",
        attributes_json=json.dumps(
            {
                "entity_id": entity.id,
                "state": "confirmed",
                "user_confirmed_at": now.isoformat(),
                "created_by": "user",
            },
            ensure_ascii=False,
        ),
        confidence=1.0,
        origin_type=OriginType.USER.value,
        review_status=ReviewStatus.CONFIRMED.value,
        is_canonical=True,
        created_at=now,
    )
    session.add(version)
    entity.is_locked = True
    entity.updated_at = now
    session.flush()
    return {
        "entity_id": entity.id,
        "asset_id": asset.id,
        "asset_version_id": version.id,
        "state": "confirmed",
        "user_confirmed_at": now.isoformat(),
    }


def confirm_narrative_asset_v1(session: Session, asset_id: int, *, user_id: str = "user") -> dict[str, Any]:
    asset = session.get(NarrativeAsset, asset_id)
    if asset is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND,
            f"asset not found: {asset_id}",
        )
    canonical = _get_canonical_version(session, asset.id)
    if canonical is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND,
            f"asset {asset_id} has no canonical version",
        )
    now = utc_now()
    attrs = json.loads(canonical.attributes_json or "{}")
    attrs["state"] = "confirmed"
    attrs["user_confirmed_at"] = now.isoformat()
    attrs["created_by"] = "user"
    canonical.attributes_json = json.dumps(attrs, ensure_ascii=False)
    canonical.origin_type = OriginType.USER.value
    canonical.review_status = ReviewStatus.CONFIRMED.value
    asset.is_locked = True
    asset.updated_at = now
    session.flush()
    return {
        "asset_id": asset.id,
        "asset_version_id": canonical.id,
        "state": "confirmed",
        "user_confirmed_at": now.isoformat(),
    }


def _open_asset_conflict(
    session: Session,
    *,
    book_id: int,
    run_id: int,
    snapshot_id: int,
    asset_id: int,
    confirmed_version_id: int,
    proposed_version_id: int,
    summary_safe: str,
) -> AnalysisConflict | None:
    existing = session.scalar(
        select(AnalysisConflict).where(
            AnalysisConflict.book_id == book_id,
            AnalysisConflict.run_id == run_id,
            AnalysisConflict.left_ref_type == "asset",
            AnalysisConflict.left_ref_id == str(asset_id),
            AnalysisConflict.right_ref_type == "asset_version",
            AnalysisConflict.right_ref_id == str(proposed_version_id),
            AnalysisConflict.status == ConflictStatus.OPEN.value,
        )
    )
    if existing is not None:
        return existing
    conflict = AnalysisConflict(
        book_id=book_id,
        run_id=None,
        book_snapshot_id=snapshot_id if snapshot_id > 0 else None,
        conflict_type=ConflictType.LOCKED_ASSET_VS_NEW_RUN.value,
        left_ref_type="asset_version",
        left_ref_id=str(confirmed_version_id),
        right_ref_type="asset_version",
        right_ref_id=str(proposed_version_id),
        description=summary_safe[:500],
        severity="warning",
        status=ConflictStatus.OPEN.value,
        resolution_json=json.dumps({"target_asset_id": asset_id, "whole_book_run_id": run_id}),
        created_at=utc_now(),
    )
    session.add(conflict)
    session.flush()
    return conflict


def materialize_with_confirmed_protection_v1(
    session: Session,
    *,
    book_id: int,
    run_id: int,
    snapshot_id: int,
    asset_key: str,
    signature: str,
    candidate_payload: dict[str, Any],
    title: str,
    summary: str,
    asset_type: str,
    mapped_entities: list[int],
    window_id: int,
    core_locator: dict[str, Any],
) -> tuple[NarrativeAsset, NarrativeAssetVersion, bool, AnalysisConflict | None]:
    """Returns (asset, version, reused, conflict). Never overwrites confirmed canonical."""
    row = session.scalar(
        select(NarrativeAsset).where(NarrativeAsset.book_id == book_id, NarrativeAsset.asset_key == asset_key)
    )
    if row is None:
        row = NarrativeAsset(
            book_id=book_id,
            asset_key=asset_key,
            lifecycle_status="active",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(row)
        session.flush()

    confirmed = _confirmed_version(session, row.id)
    if confirmed is not None:
        confirmed_sig = json.loads(confirmed.attributes_json or "{}").get("signature")
        if confirmed_sig == signature:
            attrs = json.loads(confirmed.attributes_json or "{}")
            source_windows = list(attrs.get("source_window_ids") or [])
            if window_id not in source_windows:
                source_windows.append(window_id)
            attrs["source_window_ids"] = source_windows
            attrs.setdefault("provenance_runs", [])
            if run_id not in attrs["provenance_runs"]:
                attrs["provenance_runs"].append(run_id)
            confirmed.attributes_json = json.dumps(attrs, ensure_ascii=False)
            session.flush()
            return row, confirmed, True, None

        proposed = NarrativeAssetVersion(
            asset_id=row.id,
            book_snapshot_id=snapshot_id,
            asset_type=asset_type,
            title=title,
            summary=summary,
            attributes_json=json.dumps(
                {
                    **candidate_payload,
                    "signature": signature,
                    "subject_entity_ids": mapped_entities,
                    "source_window_ids": [window_id],
                    "whole_book_run_id": run_id,
                    "state": "candidate",
                },
                ensure_ascii=False,
            ),
            confidence=float(candidate_payload.get("confidence", 0.0)),
            origin_type=OriginType.MODEL.value,
            review_status=ReviewStatus.CANDIDATE.value,
            is_canonical=False,
            source_fingerprint=signature,
            created_at=utc_now(),
        )
        session.add(proposed)
        session.flush()
        conflict = _open_asset_conflict(
            session,
            book_id=book_id,
            run_id=run_id,
            snapshot_id=snapshot_id,
            asset_id=row.id,
            confirmed_version_id=confirmed.id,
            proposed_version_id=proposed.id,
            summary_safe=f"Confirmed asset {row.id} differs from new proposal",
        )
        return row, proposed, False, conflict

    version = NarrativeAssetVersion(
        asset_id=row.id,
        book_snapshot_id=snapshot_id,
        asset_type=asset_type,
        title=title,
        summary=summary,
        attributes_json=json.dumps(
            {
                **candidate_payload,
                "signature": signature,
                "subject_entity_ids": mapped_entities,
                "source_window_ids": [window_id],
                "whole_book_run_id": run_id,
            },
            ensure_ascii=False,
        ),
        confidence=float(candidate_payload.get("confidence", 0.0)),
        origin_type=OriginType.MODEL.value,
        review_status=ReviewStatus.CANDIDATE.value,
        is_canonical=True,
        source_fingerprint=signature,
        created_at=utc_now(),
    )
    session.add(version)
    session.flush()
    return row, version, False, None


def is_entity_confirmed(session: Session, entity_id: int) -> bool:
    entity = session.get(NarrativeEntity, entity_id)
    if entity is None:
        return False
    asset_key = _entity_endpoint_asset_key(entity.book_id, entity.id)
    asset = session.scalar(
        select(NarrativeAsset).where(
            NarrativeAsset.book_id == entity.book_id,
            NarrativeAsset.asset_key == asset_key,
        )
    )
    if asset is None:
        return False
    return _confirmed_version(session, asset.id) is not None
