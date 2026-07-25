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
from app.narrative_core.product_contract.module_results import normalize_coverage_scope_wire
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
        usage = dict(result.usage or {})
        engine_id = str(result.engine_id or self.engine_id)
        engine_version = str(result.engine_version or self.engine_version)
        is_synthetic = bool((result.module_outputs or {}).get("synthetic", False))
        if mock and "fake.signed" in engine_id:
            is_synthetic = True
        is_fake = bool(mock) or "fake.signed" in engine_id or bool(
            (result.module_outputs or {}).get("fake", False)
        )
        provider_backed = bool(
            usage.get("provider_backed")
            or usage.get("transport_kind") in {"REAL_HTTP", "FAKE_HTTP_TEST"}
            or usage.get("provider_request_id")
        )
        if provider_backed:
            is_synthetic = False
            is_fake = False
        engine_kind = str(
            usage.get("engine_kind")
            or ("PRIVATE_REAL" if provider_backed or not is_fake else "TEST_FAKE")
        )
        output_fp = compute_output_fingerprint(
            {
                "module_outputs": result.module_outputs,
                "asset_candidates": list(result.asset_candidates),
                "relation_candidates": list(result.relation_candidates),
                "evidence_candidates": [
                    getattr(e, "candidate_id", str(e)) for e in result.evidence_candidates
                ],
                "engine_id": engine_id,
                "provider_request_id": usage.get("provider_request_id"),
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
                engine_id=engine_id,
                engine_version=engine_version,
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
            payload.setdefault("synthetic", is_synthetic)
            payload.setdefault("fake", is_fake)
            payload.setdefault("non_production", True)
            if provider_backed:
                payload["provider_backed"] = True
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
            payload.setdefault("synthetic", is_synthetic)
            payload.setdefault("fake", is_fake)
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
            payload.setdefault("synthetic", is_synthetic)
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
            payload.setdefault("synthetic", is_synthetic)
            conflict_commands.append(
                ConflictCandidateCommand(
                    write_kind="conflict_candidate",
                    contract=_contract("conflict_candidate"),
                    payload=payload,
                )
            )

        artifact_payload: dict[str, Any] = {
            "module_key": module_key,
            "module_version": module_version,
            "stage_key": result.stage_key,
            "status": result.status,
            "output_fingerprint": output_fp,
            "synthetic": is_synthetic,
            "fake": is_fake,
            "non_production": True,
            "provider_backed": provider_backed,
            "engine_kind": engine_kind,
            "module_outputs_summary": {
                "keys": sorted(str(k) for k in result.module_outputs.keys()),
                "fake": is_fake,
                "synthetic": is_synthetic,
            },
        }
        for meta_key in ("transport_kind", "provider_request_id"):
            if usage.get(meta_key) is not None:
                artifact_payload[meta_key] = usage[meta_key]

        module_outputs = dict(result.module_outputs or {})
        contract_ver = str(module_outputs.get("contract_version") or "").lower()
        evidence_ver = str(
            module_outputs.get("evidence_contract_version")
            or usage.get("evidence_contract_version")
            or ""
        ).lower()
        is_ss_v2 = module_key == "structure_stages" and (
            contract_ver == "v2"
            or evidence_ver == "v2"
            or str(module_outputs.get("schema") or "") == "StructureStagesResultV2"
        )
        if is_ss_v2:
            banned_keys = frozenset(
                {
                    "prompt",
                    "credential",
                    "raw_response",
                    "messages",
                    "full_text",
                    "prompt_body",
                    "system_prompt",
                }
            )

            def _scrub_mapping(value: Any) -> Any:
                if isinstance(value, Mapping):
                    return {
                        str(k): _scrub_mapping(v)
                        for k, v in value.items()
                        if str(k) not in banned_keys
                    }
                if isinstance(value, (list, tuple)):
                    return [_scrub_mapping(v) for v in value]
                return value

            artifact_payload["contract_version"] = "v2"
            artifact_payload["evidence_contract_version"] = "v2"
            artifact_payload["provider_backed"] = provider_backed
            artifact_payload["synthetic"] = False if provider_backed else is_synthetic
            if module_outputs.get("coverage_scope") is not None:
                artifact_payload["coverage_scope"] = normalize_coverage_scope_wire(
                    module_outputs.get("coverage_scope")
                )
            if module_outputs.get("stages") is not None:
                artifact_payload["stages"] = _scrub_mapping(module_outputs.get("stages"))
            if module_outputs.get("turning_points") is not None:
                artifact_payload["turning_points"] = _scrub_mapping(
                    module_outputs.get("turning_points")
                )
            catalog_fp = module_outputs.get("catalog_fingerprint") or usage.get(
                "catalog_fingerprint"
            )
            if catalog_fp:
                artifact_payload["catalog_fingerprint"] = catalog_fp
            if provider_backed and asset_commands and evidence_commands:
                artifact_payload["persistence_complete"] = True

        if provider_backed and (
            not asset_commands or not evidence_commands
        ):
            # Incomplete provider-backed result — diagnostic only, never Live success.
            artifact_payload["diagnostic"] = True
            artifact_payload["completed"] = False
            artifact_payload["persistence_complete"] = False
            if artifact_payload.get("status") in {"completed", "completed_partial"}:
                artifact_payload["status"] = "diagnostic_failed"

        artifact = StageArtifactPayload(
            write_kind="stage_artifact",
            contract=_contract("stage_artifact"),
            payload=artifact_payload,
        )

        notes = ["candidate_commands_only", "no_orm_write"]
        if provider_backed:
            notes.append("provider_backed")
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
            synthetic=is_synthetic,
            notes=tuple(notes),
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
