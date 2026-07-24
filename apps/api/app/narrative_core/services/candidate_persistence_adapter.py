"""Candidate Persistence Adapter (Phase 2B-R / CHG-043).

Protocol + Recording sink (tests) + Phase 1B service sink (ORM candidate writes).
No auto confirm/lock/canonical. No new Migration — provenance rides existing
version columns + attributes_json / artifact payload_json.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from sqlalchemy.orm import Session

from app.narrative_core.contracts.whole_book_artifact import (
    WHOLE_BOOK_STAGE_ARTIFACT_TYPE,
    build_whole_book_stage_artifact_envelope,
)
from app.narrative_core.enums import ConflictType, OriginType
from app.narrative_core.private_engine_contract.candidate import (
    CandidatePersistenceContract,
    assert_no_forbidden_auto_actions,
)
from app.narrative_core.services.asset_service import NarrativeAssetService
from app.narrative_core.services.conflict_service import ConflictCreateRequest
from app.narrative_core.services.relation_service import NarrativeRelationServiceImpl
from app.narrative_core.services.whole_book_candidate_builder import (
    AssetCandidateCommand,
    ConflictCandidateCommand,
    EvidenceCandidateCommand,
    ModuleCandidateBuildResult,
    RelationCandidateCommand,
    StageArtifactPayload,
)
from app.narrative_core.services.whole_book_engine_adapters import (
    AnalysisConflictSinkAdapter,
    ArtifactWriterAdapter,
    NarrativeAssetWriterAdapter,
    NarrativeRelationWriterAdapter,
    mock_source_fingerprint,
)


@runtime_checkable
class CandidatePersistenceAdapter(Protocol):
    """Persistence boundary — candidates only; never auto-promote."""

    def persist_commands(self, built: ModuleCandidateBuildResult) -> Mapping[str, Any]: ...


@dataclass
class RecordingCandidatePersistenceSink:
    """Test/integration sink: records calls without writing formal database rows."""

    calls: list[ModuleCandidateBuildResult] = field(default_factory=list)
    allow_production_write: bool = False

    def persist_commands(self, built: ModuleCandidateBuildResult) -> Mapping[str, Any]:
        if self.allow_production_write:
            raise RuntimeError("production candidate writes are forbidden in Phase 2B")
        if built.orm_written:
            raise RuntimeError("orm_written must remain false")
        if built.auto_confirm or built.auto_lock or built.canonical_overwrite:
            raise RuntimeError("auto confirm/lock/canonical forbidden")
        # mock=false must not be used by Fake Runtime paths.
        for cmd in (
            *built.asset_commands,
            *built.relation_commands,
            *built.evidence_commands,
            *built.conflict_commands,
        ):
            if getattr(cmd.contract, "mock", True) is False and built.synthetic:
                raise RuntimeError("Fake Runtime must not emit mock=false contracts")
        if built.stage_artifact is not None:
            if built.stage_artifact.contract.mock is False and built.synthetic:
                raise RuntimeError("Fake Runtime stage artifact must stay mock/synthetic")
        self.calls.append(built)
        return {
            "recorded": True,
            "orm_written": False,
            "auto_confirm": False,
            "auto_lock": False,
            "canonical_overwrite": False,
            "synthetic": built.synthetic,
            "rejected": built.rejected,
            "asset_count": len(built.asset_commands),
            "relation_count": len(built.relation_commands),
            "evidence_count": len(built.evidence_commands),
            "conflict_count": len(built.conflict_commands),
            "has_stage_artifact": built.stage_artifact is not None,
        }

    def reset(self) -> None:
        self.calls.clear()


@dataclass(frozen=True, slots=True)
class CandidateCommandBatch:
    asset_commands: tuple[AssetCandidateCommand, ...] = ()
    relation_commands: tuple[RelationCandidateCommand, ...] = ()
    evidence_commands: tuple[EvidenceCandidateCommand, ...] = ()
    conflict_commands: tuple[ConflictCandidateCommand, ...] = ()
    stage_artifact: StageArtifactPayload | None = None


def summarize_commands(built: ModuleCandidateBuildResult) -> dict[str, Any]:
    return {
        "rejected": built.rejected,
        "output_fingerprint": built.output_fingerprint,
        "orm_written": built.orm_written,
        "auto_confirm": built.auto_confirm,
        "auto_lock": built.auto_lock,
        "canonical_overwrite": built.canonical_overwrite,
        "synthetic": built.synthetic,
        "asset_commands": len(built.asset_commands),
        "relation_commands": len(built.relation_commands),
        "evidence_commands": len(built.evidence_commands),
        "conflict_commands": len(built.conflict_commands),
        "stage_artifact": built.stage_artifact is not None,
    }


def provenance_attributes(contract: CandidatePersistenceContract) -> dict[str, Any]:
    """Map contract provenance into attributes_json-compatible dict (no new columns)."""

    return {
        "run_id": contract.run_id,
        "run_stage_id": contract.run_stage_id,
        "book_snapshot_id": contract.book_snapshot_id,
        "engine_id": contract.engine_id,
        "engine_version": contract.engine_version,
        "module_key": contract.module_key,
        "module_version": contract.module_version,
        "prompt_pack_id": contract.prompt_pack_id,
        "prompt_pack_version": contract.prompt_pack_version,
        "configuration_fingerprint": contract.configuration_fingerprint,
        "output_fingerprint": contract.output_fingerprint,
        "evidence_refs": list(contract.evidence_refs),
        "mock": contract.mock,
        "private_engine": contract.private_engine,
        "write_kind": contract.write_kind,
        "review_status": "candidate",
        "auto_confirm": False,
        "auto_lock": False,
        "canonical_overwrite": False,
    }


@dataclass
class Phase1BCandidatePersistenceSink:
    """ORM candidate sink via Phase 1B services / existing adapters.

    Rules:
    - candidate-only; never confirm/lock/canonical overwrite
    - rejected validation or budget deny → no write
    - one nested transaction per validated batch
    - provenance bound via version columns + attributes_json / artifact payload
    """

    session: Session
    book_id: int
    asset_writer: NarrativeAssetWriterAdapter | None = None
    relation_writer: NarrativeRelationWriterAdapter | None = None
    artifact_writer: ArtifactWriterAdapter | None = None
    conflict_sink: AnalysisConflictSinkAdapter | None = None
    asset_service: NarrativeAssetService | None = None
    relation_service: NarrativeRelationServiceImpl | None = None
    budget_remaining: bool = True
    analysis_mode: str = "native"
    calls: list[ModuleCandidateBuildResult] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.asset_writer is None:
            self.asset_writer = NarrativeAssetWriterAdapter(
                self.session, asset_service=self.asset_service
            )
        if self.relation_writer is None:
            self.relation_writer = NarrativeRelationWriterAdapter(
                self.session, relation_service=self.relation_service
            )
        if self.artifact_writer is None:
            self.artifact_writer = ArtifactWriterAdapter(self.session)
        if self.conflict_sink is None:
            self.conflict_sink = AnalysisConflictSinkAdapter(self.session)
        if self.asset_service is None:
            self.asset_service = NarrativeAssetService(self.session)
        if self.relation_service is None:
            self.relation_service = NarrativeRelationServiceImpl(self.session)

    # ----- Explicit Lab-facing methods (Phase 2B-R1 Agent V) -----

    def persist_entities(self, built: ModuleCandidateBuildResult) -> Mapping[str, Any]:
        """Entity candidates are not first-class in Phase1B sink — no-op summary."""

        return {
            "orm_written": False,
            "entity_count": 0,
            "note": "entity persistence deferred to NarrativeEntityService when commands present",
            "auto_confirm": False,
            "auto_lock": False,
            "canonical_overwrite": False,
        }

    def persist_assets(self, commands: Sequence[AssetCandidateCommand]) -> list[int]:
        ids: list[int] = []
        with self.session.begin_nested():
            for cmd in commands:
                version_id, _ = self._write_asset(cmd)
                ids.append(version_id)
        self.session.flush()
        return ids

    def persist_relations(self, commands: Sequence[RelationCandidateCommand]) -> list[int]:
        ids: list[int] = []
        with self.session.begin_nested():
            for cmd in commands:
                ids.append(self._write_relation(cmd))
        self.session.flush()
        return ids

    def persist_asset_evidence(
        self,
        commands: Sequence[EvidenceCandidateCommand],
        *,
        asset_version_ids: Sequence[int],
        output_ref_to_asset_version: Mapping[str, int] | None = None,
    ) -> list[int]:
        ids: list[int] = []
        mapping = dict(output_ref_to_asset_version or {})
        with self.session.begin_nested():
            for cmd in commands:
                eid = self._write_evidence(
                    cmd,
                    asset_version_ids=asset_version_ids,
                    relation_version_ids=(),
                    output_ref_to_asset_version=mapping,
                )
                if eid is not None:
                    ids.append(eid)
        self.session.flush()
        return ids

    def persist_relation_evidence(
        self,
        commands: Sequence[EvidenceCandidateCommand],
        *,
        relation_version_ids: Sequence[int],
    ) -> list[int]:
        ids: list[int] = []
        with self.session.begin_nested():
            for cmd in commands:
                eid = self._write_evidence(
                    cmd,
                    asset_version_ids=(),
                    relation_version_ids=relation_version_ids,
                    output_ref_to_asset_version={},
                )
                if eid is not None:
                    ids.append(eid)
        self.session.flush()
        return ids

    def persist_conflicts(self, commands: Sequence[ConflictCandidateCommand]) -> list[int]:
        ids: list[int] = []
        with self.session.begin_nested():
            for cmd in commands:
                ids.append(self._write_conflict(cmd))
        self.session.flush()
        return ids

    def persist_stage_artifact(
        self,
        artifact: StageArtifactPayload,
        *,
        asset_version_ids: Sequence[int] = (),
        relation_version_ids: Sequence[int] = (),
        conflict_ids: Sequence[int] = (),
    ) -> int:
        with self.session.begin_nested():
            artifact_id = self._write_stage_artifact(
                artifact,
                asset_version_ids=asset_version_ids,
                relation_version_ids=relation_version_ids,
                conflict_ids=conflict_ids,
            )
        self.session.flush()
        return int(artifact_id)

    def persist_commands(self, built: ModuleCandidateBuildResult) -> Mapping[str, Any]:
        self.calls.append(built)
        if built.auto_confirm or built.auto_lock or built.canonical_overwrite:
            raise RuntimeError("auto confirm/lock/canonical forbidden")
        assert_no_forbidden_auto_actions(
            {
                "auto_confirm": built.auto_confirm,
                "auto_lock": built.auto_lock,
                "canonical_overwrite": built.canonical_overwrite,
            }
        )
        if built.rejected:
            return self._denied_summary(built, reason="rejected_validation")
        if not self.budget_remaining:
            return self._denied_summary(built, reason="budget_denied")

        # Idempotent duplicate: same output fingerprint already persisted this sink session.
        for prev in self.calls[:-1]:
            if (
                prev.output_fingerprint
                and prev.output_fingerprint == built.output_fingerprint
                and not prev.rejected
            ):
                return {
                    "recorded": True,
                    "orm_written": False,
                    "duplicate": True,
                    "auto_confirm": False,
                    "auto_lock": False,
                    "canonical_overwrite": False,
                    "synthetic": built.synthetic,
                    "rejected": False,
                    "asset_count": 0,
                    "relation_count": 0,
                    "evidence_count": 0,
                    "conflict_count": 0,
                    "has_stage_artifact": False,
                    "output_fingerprint": built.output_fingerprint,
                }

        asset_version_ids: list[int] = []
        relation_version_ids: list[int] = []
        evidence_ids: list[int] = []
        conflict_ids: list[int] = []
        artifact_id: int | None = None
        output_ref_to_asset_version: dict[str, int] = {}

        # Nested transaction: rollback batch on any failure; no partial candidate batch.
        with self.session.begin_nested():
            for cmd in built.asset_commands:
                version_id, output_ref = self._write_asset(cmd)
                asset_version_ids.append(version_id)
                if output_ref:
                    output_ref_to_asset_version[output_ref] = version_id

            for cmd in built.relation_commands:
                relation_version_ids.append(self._write_relation(cmd))

            for cmd in built.evidence_commands:
                eid = self._write_evidence(
                    cmd,
                    asset_version_ids=asset_version_ids,
                    relation_version_ids=relation_version_ids,
                    output_ref_to_asset_version=output_ref_to_asset_version,
                )
                if eid is not None:
                    evidence_ids.append(eid)

            for cmd in built.conflict_commands:
                conflict_ids.append(self._write_conflict(cmd))

            if built.stage_artifact is not None:
                artifact_id = self._write_stage_artifact(
                    built.stage_artifact,
                    asset_version_ids=asset_version_ids,
                    relation_version_ids=relation_version_ids,
                    conflict_ids=conflict_ids,
                )

        self.session.flush()
        candidate_written = len(asset_version_ids) > 0 or len(relation_version_ids) > 0
        asset_version_written = len(asset_version_ids) > 0
        evidence_written = len(evidence_ids) > 0
        artifact_written = artifact_id is not None
        # orm_written = formal candidate objects written (never artifact-only).
        orm_written = candidate_written
        # Complete business persistence: provider-backed non-synthetic candidates +
        # evidence + artifact. Artifact-only never counts as complete.
        persistence_complete = bool(
            orm_written
            and candidate_written
            and asset_version_written
            and evidence_written
            and artifact_written
            and not built.rejected
            and not built.synthetic
        )
        return {
            "recorded": True,
            "orm_written": orm_written,
            "persistence_complete": persistence_complete,
            "candidate_written": candidate_written,
            "asset_version_written": asset_version_written,
            "evidence_written": evidence_written,
            "artifact_written": artifact_written,
            "relation_written": len(relation_version_ids) > 0,
            "orm_transaction_committed": True,
            "fallback_used": False,
            "provider_backed": bool(
                (built.stage_artifact.payload if built.stage_artifact else {}).get(
                    "provider_backed"
                )
            )
            if built.stage_artifact is not None
            else False,
            "auto_confirm": False,
            "auto_lock": False,
            "canonical_overwrite": False,
            "synthetic": built.synthetic,
            "rejected": False,
            "asset_count": len(asset_version_ids),
            "relation_count": len(relation_version_ids),
            "evidence_count": len(evidence_ids),
            "conflict_count": len(conflict_ids),
            "has_stage_artifact": artifact_written,
            "asset_version_ids": asset_version_ids,
            "relation_version_ids": relation_version_ids,
            "evidence_ids": evidence_ids,
            "conflict_ids": conflict_ids,
            "artifact_id": artifact_id,
            "output_fingerprint": built.output_fingerprint,
        }

    def _denied_summary(self, built: ModuleCandidateBuildResult, *, reason: str) -> dict[str, Any]:
        return {
            "recorded": True,
            "orm_written": False,
            "persistence_complete": False,
            "candidate_written": False,
            "evidence_written": False,
            "artifact_written": False,
            "relation_written": False,
            "orm_transaction_committed": False,
            "fallback_used": False,
            "auto_confirm": False,
            "auto_lock": False,
            "canonical_overwrite": False,
            "synthetic": built.synthetic,
            "rejected": True,
            "deny_reason": reason,
            "asset_count": 0,
            "relation_count": 0,
            "evidence_count": 0,
            "conflict_count": 0,
            "has_stage_artifact": False,
        }

    def _write_asset(self, cmd: AssetCandidateCommand) -> tuple[int, str | None]:
        contract = cmd.contract
        payload = dict(cmd.payload)
        if str(payload.get("review_status", "candidate")) != "candidate":
            raise RuntimeError("only candidate asset writes allowed")
        for banned in ("confirm", "lock", "canonical", "is_canonical"):
            if payload.get(banned) is True:
                raise RuntimeError(f"forbidden asset flag: {banned}")

        attrs = provenance_attributes(contract)
        attrs.update({k: v for k, v in payload.items() if k.startswith("attr_")})
        existing_attrs = payload.get("attributes_json")
        if isinstance(existing_attrs, str) and existing_attrs.strip():
            try:
                parsed = json.loads(existing_attrs)
                if isinstance(parsed, dict):
                    attrs = {**parsed, **attrs}
            except json.JSONDecodeError:
                pass
        elif isinstance(existing_attrs, Mapping):
            attrs = {**dict(existing_attrs), **attrs}

        asset_type = str(payload.get("asset_type") or "event")
        title = str(payload.get("title") or f"candidate:{contract.module_key}")
        summary = str(payload.get("summary") or "")
        output_ref = payload.get("output_ref") or payload.get("stable_label")
        fingerprint = str(
            payload.get("source_fingerprint")
            or contract.output_fingerprint[:64]
            or mock_source_fingerprint("candidate", contract.module_key, title)
        )

        assert self.asset_writer is not None
        version_id = self.asset_writer.write_asset_candidate(
            {
                "book_id": int(payload.get("book_id") or self.book_id),
                "run_id": contract.run_id,
                "book_snapshot_id": contract.book_snapshot_id,
                "asset_type": asset_type,
                "title": title,
                "summary": summary,
                "origin_type": str(payload.get("origin_type") or OriginType.MODEL.value),
                "source_fingerprint": fingerprint,
                "identity_fingerprint": str(
                    payload.get("identity_fingerprint")
                    or mock_source_fingerprint(
                        "identity",
                        contract.module_key,
                        contract.output_fingerprint[:16],
                        title,
                    )
                ),
                "independent": bool(payload.get("independent", True)),
                "confidence": float(payload.get("confidence", 0.0) or 0.0),
                "importance": float(payload.get("importance", 0.0) or 0.0),
                "attributes_json": json.dumps(attrs, ensure_ascii=False),
            }
        )
        return int(version_id), str(output_ref) if output_ref else None

    def _write_relation(self, cmd: RelationCandidateCommand) -> int:
        contract = cmd.contract
        payload = dict(cmd.payload)
        if str(payload.get("review_status", "candidate")) != "candidate":
            raise RuntimeError("only candidate relation writes allowed")
        attrs = provenance_attributes(contract)
        existing_attrs = payload.get("attributes_json")
        if isinstance(existing_attrs, Mapping):
            attrs = {**dict(existing_attrs), **attrs}
        elif isinstance(existing_attrs, str) and existing_attrs.strip():
            try:
                parsed = json.loads(existing_attrs)
                if isinstance(parsed, dict):
                    attrs = {**parsed, **attrs}
            except json.JSONDecodeError:
                pass

        assert self.relation_writer is not None
        return int(
            self.relation_writer.write_relation_candidate(
                {
                    "book_id": int(payload.get("book_id") or self.book_id),
                    "run_id": contract.run_id,
                    "book_snapshot_id": contract.book_snapshot_id,
                    "source_asset_id": int(payload["source_asset_id"]),
                    "target_asset_id": int(payload["target_asset_id"]),
                    "relation_type": str(payload.get("relation_type") or "belongs_to"),
                    "summary": str(payload.get("summary") or ""),
                    "origin_type": str(payload.get("origin_type") or OriginType.MODEL.value),
                    "source_fingerprint": str(
                        payload.get("source_fingerprint")
                        or contract.output_fingerprint[:64]
                    ),
                    "identity_fingerprint": str(
                        payload.get("identity_fingerprint")
                        or mock_source_fingerprint(
                            "rel",
                            payload.get("source_asset_id"),
                            payload.get("target_asset_id"),
                            contract.output_fingerprint[:12],
                        )
                    ),
                    "confidence": float(payload.get("confidence", 0.0) or 0.0),
                    "importance": float(payload.get("importance", 0.0) or 0.0),
                    "attributes_json": json.dumps(attrs, ensure_ascii=False),
                }
            )
        )

    def _write_evidence(
        self,
        cmd: EvidenceCandidateCommand,
        *,
        asset_version_ids: Sequence[int],
        relation_version_ids: Sequence[int],
        output_ref_to_asset_version: Mapping[str, int],
    ) -> int | None:
        """Attach evidence after Asset/Relation version ids exist.

        Evidence tables have no run_id column — provenance is bound via parent version.
        Missing required snapshot offsets → skip (do not invent bindings).
        """

        contract = cmd.contract
        payload = dict(cmd.payload)
        book_snapshot_id = int(payload.get("book_snapshot_id") or contract.book_snapshot_id)
        chapter_id = payload.get("snapshot_chapter_id")
        paragraph_id = payload.get("snapshot_paragraph_id")
        content_hash = payload.get("paragraph_content_hash")
        start_offset = payload.get("start_offset")
        end_offset = payload.get("end_offset")
        if (
            chapter_id is None
            or paragraph_id is None
            or not content_hash
            or start_offset is None
            or end_offset is None
        ):
            return None

        target_version_id = payload.get("asset_version_id") or payload.get("target_asset_version_id")
        if target_version_id is None:
            ref = str(payload.get("target_output_ref") or "")
            if ref and ref in output_ref_to_asset_version:
                target_version_id = output_ref_to_asset_version[ref]
            elif asset_version_ids:
                target_version_id = asset_version_ids[0]
            elif relation_version_ids:
                # Relation evidence path
                assert self.relation_service is not None
                evidence = self.relation_service.attach_relation_evidence(
                    int(relation_version_ids[0]),
                    book_snapshot_id=book_snapshot_id,
                    snapshot_chapter_id=int(chapter_id),
                    snapshot_paragraph_id=int(paragraph_id),
                    paragraph_content_hash=str(content_hash),
                    start_offset=int(start_offset),
                    end_offset=int(end_offset),
                    evidence_role=str(payload.get("evidence_role") or "support"),
                    evidence_label=str(payload.get("evidence_label") or payload.get("candidate_id") or ""),
                )
                return int(evidence.id)
            else:
                return None

        assert self.asset_service is not None
        evidence = self.asset_service.attach_asset_evidence(
            int(target_version_id),
            book_snapshot_id=book_snapshot_id,
            snapshot_chapter_id=int(chapter_id),
            snapshot_paragraph_id=int(paragraph_id),
            paragraph_content_hash=str(content_hash),
            start_offset=int(start_offset),
            end_offset=int(end_offset),
            evidence_role=str(payload.get("evidence_role") or "support"),
            evidence_label=str(payload.get("evidence_label") or payload.get("candidate_id") or ""),
        )
        return int(evidence.id)

    def _write_conflict(self, cmd: ConflictCandidateCommand) -> int:
        contract = cmd.contract
        payload = dict(cmd.payload)
        assert self.conflict_sink is not None
        return int(
            self.conflict_sink.record_conflict(
                ConflictCreateRequest(
                    book_id=int(payload.get("book_id") or self.book_id),
                    conflict_type=str(
                        payload.get("conflict_type") or ConflictType.CANDIDATE_CONTRADICTION.value
                    ),
                    left_ref_type=str(payload.get("left_ref_type") or "asset_version"),
                    left_ref_id=str(payload.get("left_ref_id") or "0"),
                    right_ref_type=str(payload.get("right_ref_type") or "asset_version"),
                    right_ref_id=str(payload.get("right_ref_id") or "0"),
                    description=str(payload.get("description") or "candidate conflict")[:500],
                    severity=str(payload.get("severity") or "warning"),
                    run_id=contract.run_id,
                    book_snapshot_id=contract.book_snapshot_id,
                )
            )
        )

    def _write_stage_artifact(
        self,
        artifact: StageArtifactPayload,
        *,
        asset_version_ids: Sequence[int],
        relation_version_ids: Sequence[int],
        conflict_ids: Sequence[int],
    ) -> int:
        contract = artifact.contract
        payload = dict(artifact.payload)
        for banned in ("raw_response", "prompt_body", "system_prompt", "full_text", "novel_body"):
            if banned in payload:
                raise RuntimeError(f"artifact must not include {banned}")

        envelope = build_whole_book_stage_artifact_envelope(
            run_id=contract.run_id,
            run_stage_id=contract.run_stage_id,
            stage_key=str(payload.get("stage_key") or contract.module_key),
            engine_id=contract.engine_id,
            engine_version=contract.engine_version,
            book_id=self.book_id,
            book_snapshot_id=contract.book_snapshot_id,
            analysis_mode=self.analysis_mode,
            status=str(payload.get("status") or "completed"),
            mock=bool(contract.mock),
            synthetic=bool(payload.get("synthetic", True)),
            non_production=bool(payload.get("non_production", True)),
            output_refs=tuple(str(x) for x in contract.evidence_refs),
            created_asset_version_ids=tuple(asset_version_ids),
            created_relation_version_ids=tuple(relation_version_ids),
            conflict_ids=tuple(conflict_ids),
            checkpoint_summary={
                "output_fingerprint": contract.output_fingerprint,
                "configuration_fingerprint": contract.configuration_fingerprint,
                "module_key": contract.module_key,
                "module_version": contract.module_version,
                "prompt_pack_id": contract.prompt_pack_id,
                "prompt_pack_version": contract.prompt_pack_version,
            },
            warnings=tuple(str(x) for x in payload.get("warnings", ()) or ()),
            metrics={
                "module_key": contract.module_key,
                "private_engine": contract.private_engine,
                **{
                    k: payload[k]
                    for k in (
                        "engine_kind",
                        "transport_kind",
                        "provider_request_id",
                    )
                    if payload.get(k) is not None
                },
            },
        )
        artifact_status = str(payload.get("status") or "completed")
        if bool(payload.get("diagnostic")) and artifact_status == "completed":
            artifact_status = "diagnostic_failed"
        marked = envelope.to_payload()
        marked["status"] = artifact_status
        marked["prompt_version"] = contract.prompt_pack_version
        marked["module_version"] = contract.module_version
        marked["subject_id"] = str(contract.run_stage_id or contract.module_key)
        assert self.artifact_writer is not None
        return int(
            self.artifact_writer.write_artifact(
                contract.run_id,
                WHOLE_BOOK_STAGE_ARTIFACT_TYPE,
                marked,
            )
        )


__all__ = [
    "CandidateCommandBatch",
    "CandidatePersistenceAdapter",
    "Phase1BCandidatePersistenceSink",
    "RecordingCandidatePersistenceSink",
    "provenance_attributes",
    "summarize_commands",
]
