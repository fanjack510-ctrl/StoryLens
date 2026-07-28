"""Pure validators for whole_book_contract_v1 (no DB writes)."""

from __future__ import annotations

from .common import sha256_hex
from .enums import ArtifactState, EngineProposalDecision, EvidenceState
from .models import (
    NarrativeAssetVersionV1,
    SnapshotEvidenceLocatorV1,
    WholeBookSynthesisRequestV1,
    WholeBookSynthesisResponseV1,
    WholeBookWindowAnalysisResponseV1,
)


def validate_evidence_locator(
    locator: SnapshotEvidenceLocatorV1,
    snapshot_paragraph_text: str,
) -> EvidenceState:
    """Validate locator against Snapshot paragraph text. Never fuzzy-matches."""
    if locator.start_offset < 0 or locator.end_offset > len(snapshot_paragraph_text):
        return EvidenceState.unresolved
    if locator.end_offset <= locator.start_offset:
        return EvidenceState.unresolved
    expected_slice = snapshot_paragraph_text[locator.start_offset : locator.end_offset]
    if expected_slice != locator.quote_text:
        return EvidenceState.unresolved
    paragraph_hash = sha256_hex(snapshot_paragraph_text)
    if paragraph_hash != locator.paragraph_text_hash:
        return EvidenceState.stale
    if sha256_hex(locator.quote_text) != locator.quote_hash:
        return EvidenceState.unresolved
    return EvidenceState.valid


def validate_window_analysis_response_v1(
    response: WholeBookWindowAnalysisResponseV1,
) -> None:
    """Raise ValueError if cross-references are incomplete."""
    evidence_keys = [e.evidence_key for e in response.evidences]
    if len(evidence_keys) != len(set(evidence_keys)):
        raise ValueError("evidence_key must be unique in response")
    evidence_set = set(evidence_keys)

    entity_keys = {e.candidate_key for e in response.entities}
    asset_keys = {a.candidate_key for a in response.assets}
    if len(entity_keys) != len(response.entities):
        raise ValueError("entity candidate_key must be unique")
    if len(asset_keys) != len(response.assets):
        raise ValueError("asset candidate_key must be unique")

    def _require_evidence(keys: list[str], owner: str) -> None:
        missing = [k for k in keys if k not in evidence_set]
        if missing:
            raise ValueError(f"{owner} references missing evidence_keys: {missing}")

    for entity in response.entities:
        _require_evidence(entity.evidence_keys, f"entity:{entity.candidate_key}")
        for alias in entity.aliases:
            _require_evidence(alias.evidence_keys, f"entity_alias:{entity.candidate_key}")

    for asset in response.assets:
        _require_evidence(asset.evidence_keys, f"asset:{asset.candidate_key}")
        for sk in asset.subject_entity_keys:
            if sk not in entity_keys:
                raise ValueError(f"asset:{asset.candidate_key} unknown subject_entity_key {sk}")

    relation_keys = [r.candidate_key for r in response.relations]
    if len(relation_keys) != len(set(relation_keys)):
        raise ValueError("relation candidate_key must be unique")

    for relation in response.relations:
        _require_evidence(relation.evidence_keys, f"relation:{relation.candidate_key}")
        for ref, label in ((relation.subject, "subject"), (relation.object, "object")):
            pool = entity_keys if ref.kind.value == "entity" else asset_keys
            if ref.candidate_key not in pool:
                raise ValueError(
                    f"relation:{relation.candidate_key} {label} candidate_key missing: {ref.candidate_key}"
                )


def evaluate_engine_proposal_against_current_version(
    current_state: ArtifactState,
    current_version: NarrativeAssetVersionV1,
    proposed_version: NarrativeAssetVersionV1,
) -> EngineProposalDecision:
    """Contract-level Confirmed Asset protection (pure function)."""
    if current_state == ArtifactState.candidate:
        if current_version.payload_hash == proposed_version.payload_hash:
            return EngineProposalDecision.ignore_identical
        return EngineProposalDecision.replace_candidate
    if current_state == ArtifactState.confirmed:
        if current_version.payload_hash == proposed_version.payload_hash:
            return EngineProposalDecision.ignore_identical
        return EngineProposalDecision.create_conflict
    if current_state in (ArtifactState.rejected, ArtifactState.superseded):
        return EngineProposalDecision.reject_invalid
    return EngineProposalDecision.reject_invalid


def validate_synthesis_response_v1(
    request: WholeBookSynthesisRequestV1,
    response: WholeBookSynthesisResponseV1,
) -> None:
    if response.result.run_id != request.run.run_id:
        raise ValueError("synthesis response run_id mismatch")
    if response.result.snapshot_id != request.snapshot.snapshot_id:
        raise ValueError("synthesis response snapshot_id mismatch")
