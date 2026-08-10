"""V2 materialization in WholeBook checkpoints (+ optional Narrative Asset catalog)."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import NarrativeAsset, NarrativeAssetVersion, WholeBookCheckpoint, WholeBookRun
from app.narrative_core.services.asset_service import NarrativeAssetService
from .contracts import M, ProgressV2, WholeBookAnalysisV2
from .pipeline import TopicIntermediate, WindowExtractionAsset

ASSET_TYPE = "whole_book_analysis_v2"
RESULT_STAGE = "v2_result"
UNIT_STAGE = "v2_synthesis_unit"
INTERMEDIATE_STAGE = "v2_intermediate_asset"


class WholeBookV2Repository:
    def __init__(self, session: Session, *, on_persist: Any | None = None):
        self.session = session
        self._on_persist = on_persist

    def _after_persist(self) -> None:
        if self._on_persist is not None:
            self._on_persist()

    def _stable_label(self, run_id: int) -> str:
        return f"whole-book-v2:{int(run_id)}"

    def save_result(self, result: WholeBookAnalysisV2) -> int:
        """Persist V2 result keyed by WholeBookRun id (not AnalysisRun FK)."""
        run_id = int(result.analysis_metadata.run_id)
        payload = result.model_dump_json()
        row = self.session.scalars(
            select(WholeBookCheckpoint).where(
                WholeBookCheckpoint.run_id == run_id,
                WholeBookCheckpoint.stage_code == RESULT_STAGE,
                WholeBookCheckpoint.checkpoint_key == "latest",
            )
        ).first()
        if row is None:
            row = WholeBookCheckpoint(
                run_id=run_id,
                stage_code=RESULT_STAGE,
                checkpoint_key="latest",
                sequence_no=1,
                completed_unit_count=1,
                payload_hash="",
                checkpoint_payload_json=payload,
            )
            self.session.add(row)
        else:
            if row.checkpoint_payload_json != payload:
                raise ValueError("successful V2 result already materialized for run")
            self.session.flush()
            return int(row.id)
        self.session.flush()

        # Catalog copy: asset_key via stable_label; run_id=None (WholeBookRun ≠ AnalysisRun FK).
        NarrativeAssetService(self.session).create_candidate_asset(
            result.book_metadata.book_id,
            asset_type=ASSET_TYPE,
            title=f"Whole-Book V2: {result.book_metadata.title}",
            summary=result.overview.one_sentence_story,
            run_id=None,
            book_snapshot_id=result.book_metadata.snapshot_id,
            stable_label=self._stable_label(run_id),
            attributes_json=payload,
            source_fingerprint=result.book_metadata.revision_hash,
            origin_type="model",
        )
        self.session.flush()
        return int(row.id)

    def load_result(self, run_id: int) -> WholeBookAnalysisV2 | None:
        row = self.session.scalars(
            select(WholeBookCheckpoint).where(
                WholeBookCheckpoint.run_id == int(run_id),
                WholeBookCheckpoint.stage_code == RESULT_STAGE,
                WholeBookCheckpoint.checkpoint_key == "latest",
            )
        ).first()
        if row is not None:
            return WholeBookAnalysisV2.model_validate_json(row.checkpoint_payload_json)

        label = self._stable_label(int(run_id))
        # Resolve via asset_key builder used at save time.
        key = NarrativeAssetService.resolve_asset_key(
            book_id=0,  # unused when we scan by label-derived keys — fall through versions
            asset_type=ASSET_TYPE,
            stable_label=label,
        )
        # Prefer any asset version matching this run's stable label fingerprint in attributes.
        versions = self.session.scalars(
            select(NarrativeAssetVersion)
            .where(NarrativeAssetVersion.asset_type == ASSET_TYPE)
            .order_by(NarrativeAssetVersion.id.desc())
        ).all()
        for ver in versions:
            try:
                parsed = WholeBookAnalysisV2.model_validate_json(ver.attributes_json)
            except Exception:  # noqa: BLE001
                continue
            if int(parsed.analysis_metadata.run_id) == int(run_id):
                return parsed

        # Legacy: AnalysisRun-bound versions (early V2 experiments).
        ver = self.session.scalars(
            select(NarrativeAssetVersion)
            .where(
                NarrativeAssetVersion.run_id == int(run_id),
                NarrativeAssetVersion.asset_type == ASSET_TYPE,
            )
            .order_by(NarrativeAssetVersion.id.desc())
        ).first()
        if ver is not None:
            return WholeBookAnalysisV2.model_validate_json(ver.attributes_json)

        # Silence unused key warning in type checkers
        _ = key
        _ = NarrativeAsset
        return None

    def save_progress(self, run_id: int, progress: ProgressV2) -> None:
        row = self.session.scalars(
            select(WholeBookCheckpoint).where(
                WholeBookCheckpoint.run_id == run_id,
                WholeBookCheckpoint.stage_code == "v2_progress",
                WholeBookCheckpoint.checkpoint_key == "latest",
            )
        ).first()
        payload = progress.model_dump_json()
        if row is None:
            row = WholeBookCheckpoint(
                run_id=run_id,
                stage_code="v2_progress",
                checkpoint_key="latest",
                sequence_no=1,
                completed_unit_count=progress.provider_calls_completed,
                payload_hash="",
                checkpoint_payload_json=payload,
            )
            self.session.add(row)
        else:
            row.sequence_no += 1
            row.completed_unit_count = progress.provider_calls_completed
            row.checkpoint_payload_json = payload
        self.session.flush()
        self._after_persist()

    def load_progress(self, run_id: int) -> ProgressV2 | None:
        row = self.session.scalars(
            select(WholeBookCheckpoint).where(
                WholeBookCheckpoint.run_id == run_id,
                WholeBookCheckpoint.stage_code == "v2_progress",
                WholeBookCheckpoint.checkpoint_key == "latest",
            )
        ).first()
        return None if row is None else ProgressV2.model_validate_json(row.checkpoint_payload_json)

    def load_unit(self, run_id: int, key: str, schema: type[M]) -> M | None:
        row = self.session.scalars(
            select(WholeBookCheckpoint).where(
                WholeBookCheckpoint.run_id == run_id,
                WholeBookCheckpoint.stage_code == UNIT_STAGE,
                WholeBookCheckpoint.checkpoint_key == key,
            )
        ).first()
        return None if row is None else schema.model_validate_json(row.checkpoint_payload_json)

    def save_unit(self, run_id: int, key: str, value: M) -> None:
        row = self.session.scalars(
            select(WholeBookCheckpoint).where(
                WholeBookCheckpoint.run_id == run_id,
                WholeBookCheckpoint.stage_code == UNIT_STAGE,
                WholeBookCheckpoint.checkpoint_key == key,
            )
        ).first()
        payload = value.model_dump_json()
        if row is not None:
            if row.checkpoint_payload_json != payload:
                raise ValueError(f"successful synthesis unit already persisted: {key}")
            return
        self.session.add(
            WholeBookCheckpoint(
                run_id=run_id,
                stage_code=UNIT_STAGE,
                checkpoint_key=key,
                sequence_no=1,
                completed_unit_count=1,
                payload_hash="",
                checkpoint_payload_json=payload,
            )
        )
        self.session.flush()
        self._after_persist()

    def load_intermediate(self, run_id: int, key: str) -> Any | None:
        row = self.session.scalars(
            select(WholeBookCheckpoint).where(
                WholeBookCheckpoint.run_id == run_id,
                WholeBookCheckpoint.stage_code == INTERMEDIATE_STAGE,
                WholeBookCheckpoint.checkpoint_key == key,
            )
        ).first()
        if row is None:
            return None
        data = json.loads(row.checkpoint_payload_json)
        if key.startswith("window:"):
            return WindowExtractionAsset.model_validate(data)
        if key.startswith("topic:"):
            return TopicIntermediate.model_validate(data)
        return data

    def save_intermediate(self, run_id: int, key: str, value: Any) -> None:
        if hasattr(value, "model_dump_json"):
            payload = value.model_dump_json()
        else:
            payload = json.dumps(value, ensure_ascii=False)
        row = self.session.scalars(
            select(WholeBookCheckpoint).where(
                WholeBookCheckpoint.run_id == run_id,
                WholeBookCheckpoint.stage_code == INTERMEDIATE_STAGE,
                WholeBookCheckpoint.checkpoint_key == key,
            )
        ).first()
        if row is not None:
            if row.checkpoint_payload_json != payload:
                raise ValueError(f"successful intermediate already persisted: {key}")
            return
        self.session.add(
            WholeBookCheckpoint(
                run_id=run_id,
                stage_code=INTERMEDIATE_STAGE,
                checkpoint_key=key,
                sequence_no=1,
                completed_unit_count=1,
                payload_hash="",
                checkpoint_payload_json=payload,
            )
        )
        self.session.flush()
        self._after_persist()

    def has_result(self, run_id: int) -> bool:
        return self.load_result(int(run_id)) is not None

    def copy_intermediates(self, *, source_run_id: int, target_run_id: int) -> int:
        """Copy intermediate + synthesis-unit checkpoints for safe reanalysis reuse.

        Never copies the final v2_result row — a new formal result version is always required.
        """
        if int(source_run_id) == int(target_run_id):
            return 0
        rows = self.session.scalars(
            select(WholeBookCheckpoint).where(
                WholeBookCheckpoint.run_id == int(source_run_id),
                WholeBookCheckpoint.stage_code.in_((INTERMEDIATE_STAGE, UNIT_STAGE)),
            )
        ).all()
        copied = 0
        for row in rows:
            exists = self.session.scalars(
                select(WholeBookCheckpoint).where(
                    WholeBookCheckpoint.run_id == int(target_run_id),
                    WholeBookCheckpoint.stage_code == row.stage_code,
                    WholeBookCheckpoint.checkpoint_key == row.checkpoint_key,
                )
            ).first()
            if exists is not None:
                continue
            self.session.add(
                WholeBookCheckpoint(
                    run_id=int(target_run_id),
                    stage_code=row.stage_code,
                    checkpoint_key=row.checkpoint_key,
                    sequence_no=1,
                    completed_unit_count=row.completed_unit_count,
                    payload_hash=row.payload_hash,
                    checkpoint_payload_json=row.checkpoint_payload_json,
                )
            )
            copied += 1
        if copied:
            self.session.flush()
        return copied


def pinned_provider(session: Session, run_id: int) -> tuple[str, str]:
    run = session.get(WholeBookRun, run_id)
    if run is None:
        raise LookupError("whole-book run not found")
    if not run.provider_name or not run.model_name:
        raise ValueError("run provider/model pin required")
    return str(run.provider_name), str(run.model_name)
