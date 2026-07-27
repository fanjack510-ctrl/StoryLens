"""Candidate persistence contract (Phase 2B-P).

First-four modules may write candidates only — never auto confirm/lock/canonical.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


FORBIDDEN_AUTO_ACTIONS: frozenset[str] = frozenset(
    {
        "auto_confirm",
        "auto_corrected",
        "auto_lock",
        "canonical_overwrite",
        "delete_user_version",
        "mutate_old_snapshot_evidence",
    }
)

ALLOWED_CANDIDATE_WRITE_KINDS: frozenset[str] = frozenset(
    {
        "candidate_asset_version",
        "candidate_relation_version",
        "evidence",
        "conflict_candidate",
        "stage_artifact",
    }
)


@dataclass(frozen=True, slots=True)
class CandidatePersistenceContract:
    run_id: int
    run_stage_id: int | None
    book_snapshot_id: int
    engine_id: str
    engine_version: str
    module_key: str
    module_version: str
    prompt_pack_id: str
    prompt_pack_version: str
    configuration_fingerprint: str
    output_fingerprint: str
    evidence_refs: tuple[str, ...]
    mock: bool
    private_engine: bool
    write_kind: str

    def __post_init__(self) -> None:
        if self.write_kind not in ALLOWED_CANDIDATE_WRITE_KINDS:
            raise ValueError(f"write_kind not allowed: {self.write_kind}")
        if self.mock is not False:
            # Real analysis path requires mock=false; fixtures may set explicitly.
            pass
        if self.run_id <= 0 or self.book_snapshot_id <= 0:
            raise ValueError("run_id and book_snapshot_id must be positive")
        if not self.configuration_fingerprint.strip() or not self.output_fingerprint.strip():
            raise ValueError("fingerprints required")
        if not self.private_engine and not self.mock:
            raise ValueError("non-mock writes require private_engine=True in Phase 2B-P freeze")


def assert_no_forbidden_auto_actions(actions: Mapping[str, Any]) -> None:
    for key, value in actions.items():
        if key in FORBIDDEN_AUTO_ACTIONS and value:
            raise ValueError(f"forbidden auto action: {key}")
        if value is True and str(key).lower() in {
            "confirm",
            "corrected",
            "lock",
            "canonical",
            "overwrite_canonical",
        }:
            raise ValueError(f"forbidden auto action flag: {key}")


@dataclass(frozen=True, slots=True)
class FakeCandidateWriteFixture:
    contract: CandidatePersistenceContract
    payload: Mapping[str, Any]
    forbidden_actions: Mapping[str, bool]

    def __post_init__(self) -> None:
        assert_no_forbidden_auto_actions(self.forbidden_actions)
        for action in FORBIDDEN_AUTO_ACTIONS:
            if self.forbidden_actions.get(action, False):
                raise ValueError(f"fixture must not enable {action}")


def fake_candidate_write_fixture() -> FakeCandidateWriteFixture:
    contract = CandidatePersistenceContract(
        run_id=1,
        run_stage_id=1,
        book_snapshot_id=1,
        engine_id="fake.signed.private_engine",
        engine_version="0.0.1-fake",
        module_key="book_overview",
        module_version="1.0.0",
        prompt_pack_id="fake.prompt_pack.first_four",
        prompt_pack_version="0.0.1-fake",
        configuration_fingerprint="fake-config-fp",
        output_fingerprint="fake-output-fp",
        evidence_refs=("ev-fake-1",),
        mock=False,
        private_engine=True,
        write_kind="candidate_asset_version",
    )
    return FakeCandidateWriteFixture(
        contract=contract,
        payload={"fake": True, "review_status": "candidate"},
        forbidden_actions={action: False for action in sorted(FORBIDDEN_AUTO_ACTIONS)},
    )
