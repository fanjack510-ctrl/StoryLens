"""Module Candidate Builder (Phase 2B Agent R / CHG-039).

Builds command/DTO payloads only — never writes ORM, never auto confirm/lock/canonical.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Mapping, Sequence

from app.narrative_core.private_engine_contract.candidate import (
    ALLOWED_CANDIDATE_WRITE_KINDS,
    FORBIDDEN_AUTO_ACTIONS,
    CandidatePersistenceContract,
    assert_no_forbidden_auto_actions,
)
from app.narrative_core.private_engine_contract.protocol import PrivateEngineExecutionResult
from app.narrative_core.private_engine_contract.validation import ModuleOutputValidationReport


@dataclass(frozen=True, slots=True)
class AssetCandidateCommand:
    write_kind: str
    contract: CandidatePersistenceContract
    payload: Mapping[str, Any]
    review_status: str = "candidate"
    auto_confirm: bool = False
    auto_lock: bool = False
    canonical_overwrite: bool = False

    def __post_init__(self) -> None:
        if self.write_kind != "candidate_asset_version":
            raise ValueError("AssetCandidateCommand write_kind mismatch")
        if self.review_status != "candidate":
            raise ValueError("candidates only")
        if self.auto_confirm or self.auto_lock or self.canonical_overwrite:
            raise ValueError("forbidden auto actions on asset candidate")


@dataclass(frozen=True, slots=True)
class RelationCandidateCommand:
    write_kind: str
    contract: CandidatePersistenceContract
    payload: Mapping[str, Any]
    review_status: str = "candidate"
    auto_confirm: bool = False
    auto_lock: bool = False
    canonical_overwrite: bool = False

    def __post_init__(self) -> None:
        if self.write_kind != "candidate_relation_version":
            raise ValueError("RelationCandidateCommand write_kind mismatch")
        if self.auto_confirm or self.auto_lock or self.canonical_overwrite:
            raise ValueError("forbidden auto actions on relation candidate")


@dataclass(frozen=True, slots=True)
class EvidenceCandidateCommand:
    write_kind: str
    contract: CandidatePersistenceContract
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.write_kind != "evidence":
            raise ValueError("EvidenceCandidateCommand write_kind mismatch")


@dataclass(frozen=True, slots=True)
class ConflictCandidateCommand:
    write_kind: str
    contract: CandidatePersistenceContract
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.write_kind != "conflict_candidate":
            raise ValueError("ConflictCandidateCommand write_kind mismatch")


@dataclass(frozen=True, slots=True)
class StageArtifactPayload:
    write_kind: str
    contract: CandidatePersistenceContract
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.write_kind != "stage_artifact":
            raise ValueError("StageArtifactPayload write_kind mismatch")
        # Artifact must not embed full model raw response or prompt bodies.
        for banned in ("raw_response", "prompt_body", "system_prompt", "full_text"):
            if banned in self.payload:
                raise ValueError(f"artifact must not include {banned}")


@dataclass(frozen=True, slots=True)
class ModuleCandidateBuildResult:
    asset_commands: tuple[AssetCandidateCommand, ...]
    relation_commands: tuple[RelationCandidateCommand, ...]
    evidence_commands: tuple[EvidenceCandidateCommand, ...]
    conflict_commands: tuple[ConflictCandidateCommand, ...]
    stage_artifact: StageArtifactPayload | None
    output_fingerprint: str
    rejected: bool
    orm_written: bool = False
    auto_confirm: bool = False
    auto_lock: bool = False
    canonical_overwrite: bool = False
    synthetic: bool = True
    notes: tuple[str, ...] = ()


def compute_output_fingerprint(payload: Mapping[str, Any] | Sequence[Any] | Any) -> str:
    def _normalize(value: Any) -> Any:
        if is_dataclass(value) and not isinstance(value, type):
            return _normalize(asdict(value))
        if isinstance(value, Mapping):
            return {str(k): _normalize(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
        if isinstance(value, (list, tuple)):
            return [_normalize(v) for v in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    raw = json.dumps(_normalize(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class ModuleCandidateBuilder:
    """Pure command/DTO builder — Integration wires persistence later."""

    engine_id: str = "fake.signed.private_engine"
    engine_version: str = "0.0.1-fake"
    default_prompt_pack_id: str = "fake.prompt_pack.first_four"
    default_prompt_pack_version: str = "0.0.1-fake"

    def build(
        self,
        *,
        result: PrivateEngineExecutionResult,
        validation: ModuleOutputValidationReport,
        run_id: int,
        run_stage_id: int | None,
        book_snapshot_id: int,
        module_key: str,
        module_version: str,
        configuration_fingerprint: str,
        prompt_pack_id: str | None = None,
        prompt_pack_version: str | None = None,
        evidence_refs: Sequence[str] = (),
        mock: bool = False,
        force_real_engine_fixture_marker: bool = False,
    ) -> ModuleCandidateBuildResult:
        """Build candidate commands.

        ``mock=False`` + ``force_real_engine_fixture_marker`` is reserved for future
        real-engine fixtures and does NOT mean this Agent R Fake path already ran
        a production analysis.
        """

        if not validation.accepted:
            return ModuleCandidateBuildResult(
                asset_commands=(),
                relation_commands=(),
                evidence_commands=(),
                conflict_commands=(),
                stage_artifact=None,
                output_fingerprint="",
                rejected=True,
                notes=("rejected_input_no_candidate_build",),
            )

        pack_id = prompt_pack_id or self.default_prompt_pack_id
        pack_version = prompt_pack_version or self.default_prompt_pack_version
        output_fp = compute_output_fingerprint(
            {
                "module_outputs": result.module_outputs,
                "asset_candidates": list(result.asset_candidates),
                "relation_candidates": list(result.relation_candidates),
                "evidence_candidates": [
                    getattr(e, "candidate_id", str(e)) for e in result.evidence_candidates
                ],
            }
        )
        refs = tuple(evidence_refs) or tuple(
            str(getattr(e, "candidate_id", e)) for e in result.evidence_candidates
        )

        def _contract(write_kind: str) -> CandidatePersistenceContract:
            if write_kind not in ALLOWED_CANDIDATE_WRITE_KINDS:
                raise ValueError(f"disallowed write_kind: {write_kind}")
            return CandidatePersistenceContract(
                run_id=run_id,
                run_stage_id=run_stage_id,
                book_snapshot_id=book_snapshot_id,
                engine_id=self.engine_id,
                engine_version=self.engine_version,
                module_key=module_key,
                module_version=module_version,
                prompt_pack_id=pack_id,
                prompt_pack_version=pack_version,
                configuration_fingerprint=configuration_fingerprint,
                output_fingerprint=output_fp,
                evidence_refs=refs,
                mock=False if force_real_engine_fixture_marker else mock,
                private_engine=True,
                write_kind=write_kind,
            )

        actions = {action: False for action in sorted(FORBIDDEN_AUTO_ACTIONS)}
        assert_no_forbidden_auto_actions(actions)

        asset_commands: list[AssetCandidateCommand] = []
        for idx, asset in enumerate(result.asset_candidates):
            payload = dict(asset) if isinstance(asset, Mapping) else {"value": asset}
            payload.setdefault("review_status", "candidate")
            payload.setdefault("synthetic", True)
            payload.setdefault("fake", True)
            payload.setdefault("non_production", True)
            asset_commands.append(
                AssetCandidateCommand(
                    write_kind="candidate_asset_version",
                    contract=_contract("candidate_asset_version"),
                    payload=payload,
                )
            )
            _ = idx

        relation_commands: list[RelationCandidateCommand] = []
        for relation in result.relation_candidates:
            payload = dict(relation) if isinstance(relation, Mapping) else {"value": relation}
            payload.setdefault("review_status", "candidate")
            payload.setdefault("synthetic", True)
            payload.setdefault("fake", True)
            relation_commands.append(
                RelationCandidateCommand(
                    write_kind="candidate_relation_version",
                    contract=_contract("candidate_relation_version"),
                    payload=payload,
                )
            )

        evidence_commands: list[EvidenceCandidateCommand] = []
        for evidence in result.evidence_candidates:
            if is_dataclass(evidence) and not isinstance(evidence, type):
                payload = asdict(evidence)
            elif isinstance(evidence, Mapping):
                payload = dict(evidence)
            else:
                payload = {"value": str(evidence)}
            payload.setdefault("synthetic", True)
            evidence_commands.append(
                EvidenceCandidateCommand(
                    write_kind="evidence",
                    contract=_contract("evidence"),
                    payload=payload,
                )
            )

        conflict_commands: list[ConflictCandidateCommand] = []
        for conflict in result.conflict_candidates:
            payload = dict(conflict) if isinstance(conflict, Mapping) else {"value": conflict}
            payload.setdefault("synthetic", True)
            conflict_commands.append(
                ConflictCandidateCommand(
                    write_kind="conflict_candidate",
                    contract=_contract("conflict_candidate"),
                    payload=payload,
                )
            )

        artifact = StageArtifactPayload(
            write_kind="stage_artifact",
            contract=_contract("stage_artifact"),
            payload={
                "module_key": module_key,
                "module_version": module_version,
                "stage_key": result.stage_key,
                "status": result.status,
                "output_fingerprint": output_fp,
                "synthetic": True,
                "fake": True,
                "non_production": True,
                "module_outputs_summary": {
                    "keys": sorted(str(k) for k in result.module_outputs.keys()),
                    "fake": bool(result.module_outputs.get("fake", True)),
                },
            },
        )

        return ModuleCandidateBuildResult(
            asset_commands=tuple(asset_commands),
            relation_commands=tuple(relation_commands),
            evidence_commands=tuple(evidence_commands),
            conflict_commands=tuple(conflict_commands),
            stage_artifact=artifact,
            output_fingerprint=output_fp,
            rejected=False,
            orm_written=False,
            auto_confirm=False,
            auto_lock=False,
            canonical_overwrite=False,
            synthetic=True,
            notes=("candidate_commands_only", "no_orm_write"),
        )


__all__ = [
    "AssetCandidateCommand",
    "ConflictCandidateCommand",
    "EvidenceCandidateCommand",
    "ModuleCandidateBuildResult",
    "ModuleCandidateBuilder",
    "RelationCandidateCommand",
    "StageArtifactPayload",
    "compute_output_fingerprint",
]
