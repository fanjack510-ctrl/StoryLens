"""CHG-20260727-015: OverviewApiResponse engine_id passthrough from projection artifact."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.db.models import AnalysisArtifact
from app.narrative_core.contracts.pro_native_overview_flags import (
    FIXTURE_ENGINE_ID,
    PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
)
from app.narrative_core.contracts.whole_book_overview_v1 import (
    CONTRACT_VERSION,
    CreateRunRequest,
    OverviewApiResponse,
)
from app.narrative_core.services.native_overview_service import (
    OVERVIEW_PROJECTION_ARTIFACT_TYPE,
    NativeOverviewService,
)

pytest_plugins = ["test_native_overview_walking_skeleton"]

CREATE_BODY = {
    "mode": "whole_book_native",
    "module_key": "book_overview",
    "provider_id": FIXTURE_ENGINE_ID,
    "model_id": "walking-skeleton-1",
    "client_request_id": "req-engine-id-passthrough",
    "consent": {
        "estimated_tokens": 0,
        "estimated_cost": 0.0,
        "currency": "CNY",
        "confirmed": True,
    },
}


def _create_completed_fixture_run(api_env) -> int:
    from test_native_overview_walking_skeleton import _seed_pro_book

    book_id = _seed_pro_book(api_env)
    with api_env["factory"]() as session:
        service = NativeOverviewService(session)
        created = service.create_run(
            book_id,
            CreateRunRequest.model_validate(CREATE_BODY),
        )
        session.commit()
        return int(created.run_id)


def test_overview_api_response_accepts_null_engine_id():
    payload = {
        "run": {
            "run_id": "1",
            "status": "completed",
            "mode": "whole_book_native",
            "module_key": "book_overview",
            "current_stage": "finalize",
        },
        "book": {"book_id": "5", "title": "t"},
        "snapshot": {"snapshot_id": "2", "status": "completed"},
        "coverage": {
            "original_paragraphs_total": 1,
            "original_paragraphs_covered": 1,
            "original_coverage_percent": 100.0,
            "windows_total": 1,
            "windows_completed": 1,
            "evidence_count": 0,
        },
        "overview": {},
        "warnings": [],
        "evidence_index": [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine_version": "native-overview-1",
        "prompt_version": "native-overview-window-v1",
        "contract_version": CONTRACT_VERSION,
        "engine_id": None,
    }
    dto = OverviewApiResponse.model_validate(payload)
    assert dto.engine_id is None


def test_get_overview_passes_engine_id_from_artifact(api_env):
    run_id = _create_completed_fixture_run(api_env)
    with api_env["factory"]() as session:
        artifact = session.scalar(
            select(AnalysisArtifact)
            .where(
                AnalysisArtifact.run_id == run_id,
                AnalysisArtifact.artifact_type == OVERVIEW_PROJECTION_ARTIFACT_TYPE,
            )
            .order_by(AnalysisArtifact.id.desc())
        )
        assert artifact is not None
        payload = json.loads(artifact.payload_json)
        payload["engine_id"] = PRIVATE_NATIVE_OVERVIEW_ENGINE_ID
        payload["engine_version"] = "native-overview-1"
        artifact.payload_json = json.dumps(payload, ensure_ascii=False)
        session.commit()

        overview = NativeOverviewService(session).get_overview(run_id)
        assert overview.engine_id == PRIVATE_NATIVE_OVERVIEW_ENGINE_ID
        assert overview.engine_version == "native-overview-1"


def test_get_overview_legacy_artifact_without_engine_id(api_env):
    run_id = _create_completed_fixture_run(api_env)
    with api_env["factory"]() as session:
        artifact = session.scalar(
            select(AnalysisArtifact)
            .where(
                AnalysisArtifact.run_id == run_id,
                AnalysisArtifact.artifact_type == OVERVIEW_PROJECTION_ARTIFACT_TYPE,
            )
            .order_by(AnalysisArtifact.id.desc())
        )
        assert artifact is not None
        payload = json.loads(artifact.payload_json)
        payload.pop("engine_id", None)
        artifact.payload_json = json.dumps(payload, ensure_ascii=False)
        session.commit()

        overview = NativeOverviewService(session).get_overview(run_id)
        dumped = overview.model_dump(mode="json")
        assert "engine_id" in dumped
        assert dumped["engine_id"] is None


def test_get_overview_selects_projection_artifact_unchanged(api_env):
    run_id = _create_completed_fixture_run(api_env)
    with api_env["factory"]() as session:
        arts = list(
            session.scalars(
                select(AnalysisArtifact).where(
                    AnalysisArtifact.run_id == run_id,
                    AnalysisArtifact.artifact_type == OVERVIEW_PROJECTION_ARTIFACT_TYPE,
                )
            )
        )
        assert len(arts) == 1
        overview = NativeOverviewService(session).get_overview(run_id)
        assert overview.coverage.windows_completed >= 1
        assert overview.engine_id in {FIXTURE_ENGINE_ID, PRIVATE_NATIVE_OVERVIEW_ENGINE_ID, None} or (
            overview.engine_id and overview.engine_id.startswith("fixture-")
        )
