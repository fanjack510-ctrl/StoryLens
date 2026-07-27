"""Phase 1D Agent L — Review Action Adapter.

Dispatches NarrativeReviewActionRequest to Phase 1B Asset/Relation/Conflict services.
Does not open production edit routes. Frontend must not set is_canonical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import (
    NarrativeAsset,
    NarrativeAssetVersion,
    NarrativeRelation,
    NarrativeRelationVersion,
)
from app.narrative_core.enums import EvidenceRole, ReviewStatus
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.product_contract.enums import (
    NarrativeReviewAction,
    ReviewTargetType,
)
from app.narrative_core.product_contract.review import (
    NarrativeReviewActionRequest,
    NarrativeReviewAuditContract,
)
from app.narrative_core.services.asset_service import NarrativeAssetService
from app.narrative_core.services.conflict_service import AnalysisConflictServiceImpl
from app.narrative_core.services.relation_service import NarrativeRelationServiceImpl


class ReviewActionAdapterError(Exception):
    """Adapter-local error (does not extend NarrativeCoreErrorCode freeze)."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(message or code)


REVIEW_EXPECTED_VERSION_MISMATCH = "REVIEW_EXPECTED_VERSION_MISMATCH"
REVIEW_IDEMPOTENT_REPLAY = "REVIEW_IDEMPOTENT_REPLAY"
REVIEW_CONFIRM_REQUIRES_EVIDENCE = "REVIEW_CONFIRM_REQUIRES_EVIDENCE"
REVIEW_UNSUPPORTED_ACTION = "REVIEW_UNSUPPORTED_ACTION"
REVIEW_TARGET_MISMATCH = "REVIEW_TARGET_MISMATCH"


@dataclass(frozen=True, slots=True)
class ReviewActionResult:
    ok: bool
    action: NarrativeReviewAction
    target_type: ReviewTargetType
    target_id: str
    new_version_id: int | None = None
    review_status: str | None = None
    is_locked: bool | None = None
    is_canonical: bool | None = None
    conflict_id: int | None = None
    conflict_status: str | None = None
    canonical_switched: bool | None = None
    audit: NarrativeReviewAuditContract | None = None
    message: str = ""
    # Never includes full paragraph body.
    details: dict[str, Any] = field(default_factory=dict)


def build_review_action_request(
    *,
    action: NarrativeReviewAction | str,
    target_type: ReviewTargetType | str,
    target_id: str | int,
    expected_version: int | str,
    actor: str,
    idempotency_key: str,
    correction_payload: dict[str, Any] | None = None,
    evidence_changes: list[dict[str, Any]] | None = None,
    resolution_payload: dict[str, Any] | None = None,
    reason: str | None = None,
) -> NarrativeReviewActionRequest:
    return NarrativeReviewActionRequest(
        action=NarrativeReviewAction(action),
        target_type=ReviewTargetType(target_type),
        target_id=str(target_id),
        expected_version=expected_version,
        actor=str(actor),
        correction_payload=dict(correction_payload or {}),
        evidence_changes=tuple(evidence_changes or ()),
        resolution_payload=dict(resolution_payload or {}),
        reason=reason,
        idempotency_key=str(idempotency_key),
    )


def validate_review_action(request: NarrativeReviewActionRequest) -> None:
    """Validate contract rules before dispatch. Raises ValueError / ReviewActionAdapterError."""
    # Dataclass __post_init__ already enforces core rules; re-check adapter gates.
    if not request.idempotency_key:
        raise ReviewActionAdapterError(
            "REVIEW_IDEMPOTENCY_REQUIRED",
            "idempotency_key is required",
        )
    if not request.actor:
        raise ReviewActionAdapterError(
            "REVIEW_ACTOR_REQUIRED",
            "actor is required",
        )
    if "is_canonical" in (request.correction_payload or {}):
        raise ReviewActionAdapterError(
            "REVIEW_IS_CANONICAL_FORBIDDEN",
            "frontend must not set is_canonical directly",
        )
    if request.action == NarrativeReviewAction.CORRECT and not request.correction_payload:
        raise ReviewActionAdapterError(
            "REVIEW_CORRECTION_REQUIRED",
            "correct requires correction_payload",
        )
    if request.action == NarrativeReviewAction.RESOLVE_CONFLICT:
        payload = request.resolution_payload or {}
        if "schema" not in payload or "version" not in payload:
            raise ReviewActionAdapterError(
                "REVIEW_RESOLUTION_SCHEMA_REQUIRED",
                "resolve_conflict requires resolution_payload.schema/version",
            )


class NarrativeReviewActionAdapter:
    """Isolated adapter — callable from tests / future routes; no production router."""

    def __init__(
        self,
        session: Session,
        *,
        asset_service: NarrativeAssetService | None = None,
        relation_service: NarrativeRelationServiceImpl | None = None,
        conflict_service: AnalysisConflictServiceImpl | None = None,
    ) -> None:
        self._session = session
        self._assets = asset_service or NarrativeAssetService(session)
        self._relations = relation_service or NarrativeRelationServiceImpl(session)
        self._conflicts = conflict_service or AnalysisConflictServiceImpl(session)
        self._idempotency: dict[str, ReviewActionResult] = {}

    def submit_review_action(
        self, request: NarrativeReviewActionRequest
    ) -> ReviewActionResult:
        validate_review_action(request)
        cached = self._idempotency.get(request.idempotency_key)
        if cached is not None:
            return ReviewActionResult(
                ok=cached.ok,
                action=cached.action,
                target_type=cached.target_type,
                target_id=cached.target_id,
                new_version_id=cached.new_version_id,
                review_status=cached.review_status,
                is_locked=cached.is_locked,
                is_canonical=cached.is_canonical,
                conflict_id=cached.conflict_id,
                conflict_status=cached.conflict_status,
                canonical_switched=cached.canonical_switched,
                audit=cached.audit,
                message=f"idempotent replay: {cached.message}",
                details={**cached.details, "idempotent": True},
            )

        try:
            result = self._dispatch(request)
        except NarrativeCoreError as exc:
            raise ReviewActionAdapterError(exc.code.value, str(exc)) from exc

        audit = NarrativeReviewAuditContract(
            action=request.action,
            target_type=request.target_type,
            target_id=request.target_id,
            actor=request.actor,
            idempotency_key=request.idempotency_key,
            reason=request.reason,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        # Strip any accidental body fields from details.
        safe_details = {
            k: v
            for k, v in result.details.items()
            if k not in {"full_text", "paragraph_text", "body", "content"}
        }
        final = ReviewActionResult(
            ok=result.ok,
            action=result.action,
            target_type=result.target_type,
            target_id=result.target_id,
            new_version_id=result.new_version_id,
            review_status=result.review_status,
            is_locked=result.is_locked,
            is_canonical=result.is_canonical,
            conflict_id=result.conflict_id,
            conflict_status=result.conflict_status,
            canonical_switched=result.canonical_switched,
            audit=audit,
            message=result.message,
            details=safe_details,
        )
        self._idempotency[request.idempotency_key] = final
        return final

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, request: NarrativeReviewActionRequest) -> ReviewActionResult:
        action = request.action
        if action in {
            NarrativeReviewAction.RESOLVE_CONFLICT,
            NarrativeReviewAction.DISMISS_CONFLICT,
        }:
            return self._handle_conflict(request)

        if request.target_type in {
            ReviewTargetType.ASSET,
            ReviewTargetType.ASSET_VERSION,
        }:
            return self._handle_asset(request)
        if request.target_type in {
            ReviewTargetType.RELATION,
            ReviewTargetType.RELATION_VERSION,
        }:
            return self._handle_relation(request)

        raise ReviewActionAdapterError(
            REVIEW_UNSUPPORTED_ACTION,
            f"unsupported target_type={request.target_type}",
        )

    def _handle_asset(self, request: NarrativeReviewActionRequest) -> ReviewActionResult:
        asset, version = self._resolve_asset_target(request)
        self._assert_expected_version(
            expected=request.expected_version,
            actual=self._asset_concurrency_token(asset, version),
        )

        action = request.action
        if action == NarrativeReviewAction.CONFIRM:
            self._assert_support_evidence_asset(version)
            mutation = self._assets.confirm_asset_version(
                version.id, make_canonical=True, actor=request.actor
            )
            return self._asset_result(request, mutation.asset, mutation.version, mutation)

        if action == NarrativeReviewAction.CORRECT:
            payload = dict(request.correction_payload)
            title = str(payload.pop("title", version.title))
            summary = str(payload.pop("summary", version.summary or ""))
            # Never honor is_canonical from payload (already validated).
            payload.pop("is_canonical", None)
            copy_evidence = bool(payload.pop("copy_evidence_from_base", True))
            mutation = self._assets.correct_asset(
                asset.id,
                based_on_version_id=version.id,
                title=title,
                summary=summary,
                make_canonical=False,
                actor=request.actor,
                **payload,
            )
            if copy_evidence:
                self._copy_asset_evidence(version.id, mutation.version.id)
            # Promote only when support evidence is present on the new version.
            try:
                self._assert_support_evidence_asset(mutation.version)
                mutation = self._assets.confirm_asset_version(
                    mutation.version.id, make_canonical=True, actor=request.actor
                )
            except ReviewActionAdapterError:
                # Corrected version retained; canonical switch deferred until evidence exists.
                pass
            return self._asset_result(request, mutation.asset, mutation.version, mutation)

        if action == NarrativeReviewAction.REJECT:
            rejected = self._assets.reject_asset_version(version.id)
            asset = self._assets.get_asset(rejected.asset_id)
            return ReviewActionResult(
                ok=True,
                action=action,
                target_type=request.target_type,
                target_id=request.target_id,
                new_version_id=int(rejected.id),
                review_status=str(rejected.review_status),
                is_locked=bool(asset.is_locked),
                is_canonical=bool(rejected.is_canonical),
                message="rejected (soft; row retained)",
            )

        if action == NarrativeReviewAction.LOCK:
            locked = self._assets.lock_asset(asset.id)
            return ReviewActionResult(
                ok=True,
                action=action,
                target_type=request.target_type,
                target_id=request.target_id,
                new_version_id=int(version.id),
                review_status=str(version.review_status),
                is_locked=bool(locked.is_locked),
                is_canonical=bool(version.is_canonical),
                message="asset locked",
            )

        if action == NarrativeReviewAction.UNLOCK:
            unlocked = self._assets.unlock_asset(asset.id)
            return ReviewActionResult(
                ok=True,
                action=action,
                target_type=request.target_type,
                target_id=request.target_id,
                new_version_id=int(version.id),
                review_status=str(version.review_status),
                is_locked=bool(unlocked.is_locked),
                is_canonical=bool(version.is_canonical),
                message="asset unlocked",
            )

        if action == NarrativeReviewAction.MARK_STALE:
            stale = self._assets.mark_asset_stale(
                asset.id, reason=str(request.reason or "user_mark_stale")
            )
            return ReviewActionResult(
                ok=True,
                action=action,
                target_type=request.target_type,
                target_id=request.target_id,
                new_version_id=int(version.id),
                review_status=str(version.review_status),
                is_locked=bool(stale.is_locked),
                is_canonical=bool(version.is_canonical),
                message="asset marked stale",
                details={"lifecycle_status": str(stale.lifecycle_status)},
            )

        raise ReviewActionAdapterError(
            REVIEW_UNSUPPORTED_ACTION,
            f"unsupported asset action={action}",
        )

    def _handle_relation(
        self, request: NarrativeReviewActionRequest
    ) -> ReviewActionResult:
        relation, version = self._resolve_relation_target(request)
        self._assert_expected_version(
            expected=request.expected_version,
            actual=self._relation_concurrency_token(relation, version),
        )

        action = request.action
        if action == NarrativeReviewAction.CONFIRM:
            self._assert_support_evidence_relation(version)
            confirmed = self._relations.confirm_relation_version(
                version.id, make_canonical=True, actor=request.actor
            )
            relation = self._relations.get_relation(confirmed.relation_id)
            return self._relation_result(request, relation, confirmed)

        if action == NarrativeReviewAction.CORRECT:
            payload = dict(request.correction_payload)
            payload.pop("is_canonical", None)
            summary = str(payload.pop("summary", version.summary or ""))
            copy_evidence = bool(payload.pop("copy_evidence_from_base", True))
            corrected = self._relations.correct_relation(
                relation.id,
                based_on_version_id=version.id,
                summary=summary,
                make_canonical=False,
                actor=request.actor,
                **payload,
            )
            if copy_evidence:
                self._copy_relation_evidence(version.id, corrected.id)
            try:
                self._assert_support_evidence_relation(corrected)
                corrected = self._relations.confirm_relation_version(
                    corrected.id, make_canonical=True, actor=request.actor
                )
            except ReviewActionAdapterError:
                pass
            relation = self._relations.get_relation(corrected.relation_id)
            return self._relation_result(request, relation, corrected)

        if action == NarrativeReviewAction.REJECT:
            rejected = self._relations.reject_relation_version(version.id)
            relation = self._relations.get_relation(rejected.relation_id)
            return ReviewActionResult(
                ok=True,
                action=action,
                target_type=request.target_type,
                target_id=request.target_id,
                new_version_id=int(rejected.id),
                review_status=str(rejected.review_status),
                is_locked=bool(relation.is_locked),
                is_canonical=bool(rejected.is_canonical),
                message="relation rejected (soft)",
            )

        if action == NarrativeReviewAction.LOCK:
            locked = self._relations.lock_relation(relation.id)
            return ReviewActionResult(
                ok=True,
                action=action,
                target_type=request.target_type,
                target_id=request.target_id,
                new_version_id=int(version.id),
                review_status=str(version.review_status),
                is_locked=bool(locked.is_locked),
                is_canonical=bool(version.is_canonical),
                message="relation locked",
            )

        if action == NarrativeReviewAction.UNLOCK:
            unlocked = self._relations.unlock_relation(relation.id)
            return ReviewActionResult(
                ok=True,
                action=action,
                target_type=request.target_type,
                target_id=request.target_id,
                new_version_id=int(version.id),
                review_status=str(version.review_status),
                is_locked=bool(unlocked.is_locked),
                is_canonical=bool(version.is_canonical),
                message="relation unlocked",
            )

        if action == NarrativeReviewAction.MARK_STALE:
            stale = self._relations.mark_relation_stale(
                relation.id, reason=str(request.reason or "user_mark_stale")
            )
            return ReviewActionResult(
                ok=True,
                action=action,
                target_type=request.target_type,
                target_id=request.target_id,
                new_version_id=int(version.id),
                review_status=str(version.review_status),
                is_locked=bool(stale.is_locked),
                is_canonical=bool(version.is_canonical),
                message="relation marked stale",
            )

        raise ReviewActionAdapterError(
            REVIEW_UNSUPPORTED_ACTION,
            f"unsupported relation action={action}",
        )

    def _handle_conflict(
        self, request: NarrativeReviewActionRequest
    ) -> ReviewActionResult:
        if request.target_type != ReviewTargetType.CONFLICT:
            raise ReviewActionAdapterError(
                REVIEW_TARGET_MISMATCH,
                "conflict actions require target_type=conflict",
            )
        conflict_id = int(request.target_id)
        conflict = self._conflicts.get_analysis_conflict(conflict_id)
        # expected_version for conflicts: use id or status token
        self._assert_expected_version(
            expected=request.expected_version,
            actual=str(conflict.id),
        )

        if request.action == NarrativeReviewAction.RESOLVE_CONFLICT:
            # Blocking still requires explicit call — never auto.
            payload = dict(request.resolution_payload)
            payload["schema"] = "analysis_conflict_resolution"
            payload.setdefault("version", "1")
            closed = self._conflicts.resolve_analysis_conflict(
                conflict_id,
                resolved_by=request.actor,
                resolution_json=payload,
            )
            return ReviewActionResult(
                ok=True,
                action=request.action,
                target_type=request.target_type,
                target_id=request.target_id,
                conflict_id=int(closed.id),
                conflict_status=str(closed.status),
                message="conflict resolved",
                details={
                    "resolution_schema": request.resolution_payload.get("schema"),
                    "resolution_version": request.resolution_payload.get("version"),
                },
            )

        if request.action == NarrativeReviewAction.DISMISS_CONFLICT:
            closed = self._conflicts.dismiss_analysis_conflict(
                conflict_id,
                resolved_by=request.actor,
                resolution_json=dict(
                    request.resolution_payload
                    or {
                        "schema": "analysis_conflict_resolution",
                        "version": "1",
                        "action": "dismiss",
                    }
                ),
            )
            return ReviewActionResult(
                ok=True,
                action=request.action,
                target_type=request.target_type,
                target_id=request.target_id,
                conflict_id=int(closed.id),
                conflict_status=str(closed.status),
                message="conflict dismissed",
            )

        raise ReviewActionAdapterError(
            REVIEW_UNSUPPORTED_ACTION,
            f"unsupported conflict action={request.action}",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_asset_target(
        self, request: NarrativeReviewActionRequest
    ) -> tuple[NarrativeAsset, NarrativeAssetVersion]:
        target_id = int(request.target_id)
        if request.target_type == ReviewTargetType.ASSET_VERSION:
            versions = (
                self._session.query(NarrativeAssetVersion)
                .filter(NarrativeAssetVersion.id == target_id)
                .all()
            )
            if not versions:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.ASSET_VERSION_NOT_FOUND,
                    f"asset version not found: {target_id}",
                )
            version = versions[0]
            asset = self._assets.get_asset(version.asset_id)
            return asset, version
        asset = self._assets.get_asset(target_id)
        canonical = self._assets.get_canonical_asset_version(asset.id)
        if canonical is not None:
            return asset, canonical
        versions = self._assets.get_asset_versions(asset.id)
        if not versions:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ASSET_VERSION_NOT_FOUND,
                f"asset {target_id} has no versions",
            )
        return asset, versions[-1]

    def _resolve_relation_target(
        self, request: NarrativeReviewActionRequest
    ) -> tuple[NarrativeRelation, NarrativeRelationVersion]:
        target_id = int(request.target_id)
        if request.target_type == ReviewTargetType.RELATION_VERSION:
            version = self._session.get(NarrativeRelationVersion, target_id)
            if version is None:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.RELATION_VERSION_NOT_FOUND,
                    f"relation version not found: {target_id}",
                )
            relation = self._relations.get_relation(version.relation_id)
            return relation, version
        relation = self._relations.get_relation(target_id)
        versions = self._relations.get_relation_versions(relation.id)
        canonical = next((v for v in versions if v.is_canonical), None)
        if canonical is not None:
            return relation, canonical
        if not versions:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.RELATION_VERSION_NOT_FOUND,
                f"relation {target_id} has no versions",
            )
        return relation, versions[-1]

    @staticmethod
    def _asset_concurrency_token(
        asset: NarrativeAsset, version: NarrativeAssetVersion
    ) -> str:
        # Prefer version id as expected_version for version-scoped ops.
        return str(version.id)

    @staticmethod
    def _relation_concurrency_token(
        relation: NarrativeRelation, version: NarrativeRelationVersion
    ) -> str:
        return str(version.id)

    @staticmethod
    def _assert_expected_version(*, expected: int | str, actual: str) -> None:
        if str(expected) != str(actual):
            raise ReviewActionAdapterError(
                REVIEW_EXPECTED_VERSION_MISMATCH,
                f"expected_version={expected} but current={actual}; refresh and retry",
            )

    def _assert_support_evidence_asset(self, version: NarrativeAssetVersion) -> None:
        evidence = self._assets.list_asset_version_evidence(version.id)
        if not any(e.evidence_role == EvidenceRole.SUPPORT.value for e in evidence):
            raise ReviewActionAdapterError(
                REVIEW_CONFIRM_REQUIRES_EVIDENCE,
                f"confirm requires support evidence on version {version.id}",
            )

    def _assert_support_evidence_relation(
        self, version: NarrativeRelationVersion
    ) -> None:
        evidence = self._relations.list_relation_version_evidence(version.id)
        if not any(e.evidence_role == EvidenceRole.SUPPORT.value for e in evidence):
            raise ReviewActionAdapterError(
                REVIEW_CONFIRM_REQUIRES_EVIDENCE,
                f"confirm requires support evidence on relation version {version.id}",
            )

    def _copy_asset_evidence(self, from_version_id: int, to_version_id: int) -> None:
        for ev in self._assets.list_asset_version_evidence(from_version_id):
            self._assets.attach_asset_evidence(
                to_version_id,
                book_snapshot_id=ev.book_snapshot_id,
                snapshot_chapter_id=ev.snapshot_chapter_id,
                snapshot_paragraph_id=ev.snapshot_paragraph_id,
                paragraph_content_hash=ev.paragraph_content_hash,
                start_offset=ev.start_offset,
                end_offset=ev.end_offset,
                evidence_role=ev.evidence_role,
                evidence_label=ev.evidence_label,
                source_scene_id=ev.source_scene_id,
                actor="user",
            )

    def _copy_relation_evidence(self, from_version_id: int, to_version_id: int) -> None:
        for ev in self._relations.list_relation_version_evidence(from_version_id):
            self._relations.attach_relation_evidence(
                to_version_id,
                book_snapshot_id=ev.book_snapshot_id,
                snapshot_chapter_id=ev.snapshot_chapter_id,
                snapshot_paragraph_id=ev.snapshot_paragraph_id,
                paragraph_content_hash=ev.paragraph_content_hash,
                start_offset=ev.start_offset,
                end_offset=ev.end_offset,
                evidence_role=ev.evidence_role,
                evidence_label=ev.evidence_label,
                source_scene_id=ev.source_scene_id,
            )

    def _asset_result(
        self,
        request: NarrativeReviewActionRequest,
        asset: NarrativeAsset,
        version: NarrativeAssetVersion,
        mutation: Any,
    ) -> ReviewActionResult:
        return ReviewActionResult(
            ok=True,
            action=request.action,
            target_type=request.target_type,
            target_id=request.target_id,
            new_version_id=int(version.id),
            review_status=str(version.review_status),
            is_locked=bool(asset.is_locked),
            is_canonical=bool(version.is_canonical),
            conflict_id=getattr(mutation, "conflict_id", None),
            canonical_switched=getattr(mutation, "canonical_switched", None),
            message=f"asset {request.action.value} ok",
            details={"prior_review_status": ReviewStatus.CANDIDATE.value},
        )

    def _relation_result(
        self,
        request: NarrativeReviewActionRequest,
        relation: NarrativeRelation,
        version: NarrativeRelationVersion,
    ) -> ReviewActionResult:
        return ReviewActionResult(
            ok=True,
            action=request.action,
            target_type=request.target_type,
            target_id=request.target_id,
            new_version_id=int(version.id),
            review_status=str(version.review_status),
            is_locked=bool(relation.is_locked),
            is_canonical=bool(version.is_canonical),
            message=f"relation {request.action.value} ok",
        )
