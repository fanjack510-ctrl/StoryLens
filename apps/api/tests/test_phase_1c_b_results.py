"""Phase 1C-B: completed Scene Analysis results viewing API + export."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.db.models import (
    AnalysisArtifact,
    AnalysisEvidence,
    AnalysisRun,
    BoundaryReviewSession,
    BoundaryRevision,
    Book,
    Chapter,
    ModelInvocation,
    Paragraph,
    Scene,
)


def _seed_completed_run(session, *, scene_specs):
    """Seed a succeeded run. scene_specs: list of (span, boundary_source, offline)."""
    book = Book(title="B", source_file_name="b.txt", source_file_hash="a" * 64)
    session.add(book)
    session.flush()
    chapter = Chapter(
        book_id=book.id, chapter_index=2, title="第1章 戏鬼回家", section_type="chapter"
    )
    session.add(chapter)
    session.flush()
    total_paras = sum(span for span, _src, _off in scene_specs)
    paragraphs = []
    for index in range(1, total_paras + 1):
        row = Paragraph(
            id=f"B0001-C0002-P{index:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=index,
            raw_text=f"正文段落{index}内容",
            normalized_text=f"正文段落{index}内容",
            char_start=index * 10,
            char_end=index * 10 + 8,
        )
        session.add(row)
        paragraphs.append(row)
    run = AnalysisRun(
        task_type="scene_pipeline",
        provider="aliyun_qwen_plus",
        model="qwen3.7-plus",
        prompt_version="v3.5",
        schema_version="v1",
        input_hash="b" * 64,
        status="succeeded",
        subject_type="chapter",
        subject_id=str(chapter.id),
        prompt_hash="c" * 64,
        analysis_mode="assisted_boundary_review",
        execution_mode="cloud",
        cloud_consent=True,
        sends_content_to_cloud=True,
        completed_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.flush()
    review = BoundaryReviewSession(
        book_id=book.id,
        chapter_id=chapter.id,
        analysis_run_id=run.id,
        prompt_version="v3.5",
        provider="aliyun_qwen_plus",
        model="qwen3.7-plus",
        status="confirmed",
        candidate_count=0,
        accepted_count=0,
        rejected_count=0,
        manually_added_count=0,
        confirmed_by="desktop-user",
        completed_at=datetime.now(timezone.utc),
    )
    session.add(review)
    session.flush()
    revision = BoundaryRevision(
        review_session_id=review.id,
        chapter_id=chapter.id,
        analysis_run_id=run.id,
        revision_number=1,
        final_boundaries_json="[]",
        confirmed_by="desktop-user",
        confirmed_at=datetime.now(timezone.utc),
        coverage_rate=1.0,
    )
    session.add(revision)
    session.flush()

    scenes = []
    cursor = 0
    for ordinal, (span, source, offline) in enumerate(scene_specs, start=1):
        start = paragraphs[cursor]
        end = paragraphs[cursor + span - 1]
        cursor += span
        scene = Scene(
            scene_key=f"B0001-C0002-R0001-S{ordinal:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            ordinal=ordinal,
            start_paragraph_id=start.id,
            end_paragraph_id=end.id,
            content_hash="d" * 64,
            created_by_run_id=run.id,
            boundary_confidence=0.9,
            boundary_detected=True,
            boundary_revision_id=revision.id,
            boundary_source=source,
        )
        session.add(scene)
        session.flush()
        payload = {
            "scene_id": scene.scene_key,
            "entry_state": {"summary": f"进入-{ordinal}", "evidence_paragraph_ids": [start.id]},
            "goal": {"summary": f"目标-{ordinal}", "evidence_paragraph_ids": [start.id]},
            "obstacle": {"summary": "", "evidence_paragraph_ids": []},
            "key_actions": [
                {"summary": f"动作-{ordinal}", "evidence_paragraph_ids": [start.id]}
            ],
            "turning_point": {"summary": "", "evidence_paragraph_ids": []},
            "outcome": {"summary": f"结果-{ordinal}", "evidence_paragraph_ids": [end.id]},
            "unresolved_question": {"summary": "", "evidence_paragraph_ids": []},
            "function_tags": ["事件推进"],
            "confidence": 0.8,
        }
        artifact = AnalysisArtifact(
            run_id=run.id,
            artifact_type="scene_analysis",
            subject_type="scene",
            subject_id=str(scene.id),
            schema_version="v1",
            prompt_version="v3.1",
            payload_json=json.dumps(payload, ensure_ascii=False),
            confidence=0.8,
            validation_status="valid",
        )
        session.add(artifact)
        session.flush()
        for path, pid in [
            ("entry_state.evidence", start.id),
            ("goal.evidence", start.id),
            ("key_actions.0.evidence", start.id),
            ("outcome.evidence", end.id),
        ]:
            session.add(
                AnalysisEvidence(
                    artifact_id=artifact.id,
                    field_path=path,
                    paragraph_id=pid,
                    paragraph_hash="h" * 64,
                )
            )
        # offline-recovered scenes have NO succeeded invocation; normal scenes do.
        session.add(
            ModelInvocation(
                run_id=run.id,
                task_type="scene_analysis",
                provider_name="aliyun_qwen_plus",
                model_name="qwen3.7-plus",
                prompt_version="v3.1",
                schema_version="v1",
                attempt_no=1,
                invocation_kind="initial",
                request_hash=f"{ordinal}".zfill(64),
                input_snapshot_json=json.dumps(
                    {"paragraph_ids": [start.id, end.id], "content_hash": "x" * 64}
                ),
                raw_response_text="{}",
                parsed_response_json=json.dumps(payload, ensure_ascii=False),
                status="failed" if offline else "succeeded",
                latency_ms=10,
                http_request_sent=True,
                http_status_code=200,
                error_code="EVIDENCE_VALIDATION_FAILED" if offline else None,
                audit_type="provider_invocation",
            )
        )
        scenes.append(scene)
    session.commit()
    return book, chapter, run, revision, scenes, paragraphs


# Run #55 shape: 14 scenes, single-para at ord 3/5/6/13, offline at ord 5 & 13.
_RUN55_SPECS = [
    (12, "user_added", False),   # 1
    (2, "model_accepted", False),  # 2
    (1, "user_added", False),      # 3 single
    (2, "user_accepted_model_conflict", False),  # 4
    (1, "user_added", True),       # 5 single offline
    (1, "model_accepted", False),  # 6 single
    (9, "model_accepted", False),  # 7
    (4, "user_accepted_model_conflict", False),  # 8
    (16, "model_accepted", False),  # 9 longest
    (8, "model_accepted", False),  # 10
    (3, "model_accepted", False),  # 11
    (3, "model_accepted", False),  # 12
    (1, "user_accepted_model_conflict", True),  # 13 single offline
    (5, None, False),              # 14 chapter end
]


def test_run_results_returns_14_scenes_in_order(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _b, _c, run, _rev, _scenes, _p = _seed_completed_run(session, scene_specs=_RUN55_SPECS)
        run_id = run.id

    resp = client.get(f"/api/v1/analysis-runs/{run_id}/results")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["run"]["id"] == run_id
    assert body["chapter"]["chapter_index"] == 2
    assert body["boundary_revision"]["coverage_rate"] == 1.0
    assert len(body["scenes"]) == 14
    ordinals = [s["scene"]["ordinal"] for s in body["scenes"]]
    assert ordinals == list(range(1, 15))
    summary = body["summary"]
    assert summary["total_scene_count"] == 14
    assert summary["single_paragraph_scene_count"] == 4
    assert summary["longest_scene_ordinal"] == 9
    assert summary["longest_scene_paragraph_count"] == 16
    assert summary["manual_added_boundary_count"] == 3
    assert summary["model_accepted_boundary_count"] == 7
    assert summary["user_accepted_conflict_count"] == 3
    assert summary["evidence_coverage_rate"] == 1.0
    assert summary["offline_recovered_scene_count"] == 2


def test_every_scene_has_valid_artifact_and_evidence(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _b, _c, run, _rev, _scenes, _p = _seed_completed_run(session, scene_specs=_RUN55_SPECS)
        run_id = run.id

    body = client.get(f"/api/v1/analysis-runs/{run_id}/results").json()
    for item in body["scenes"]:
        assert item["analysis_artifact"] is not None
        assert item["analysis_artifact"]["validation_status"] == "valid"
        assert len(item["evidence"]) >= 1
        assert item["illegal_evidence"] == []


def test_single_paragraph_and_offline_recovered_scenes(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _b, _c, run, _rev, _scenes, _p = _seed_completed_run(session, scene_specs=_RUN55_SPECS)
        run_id = run.id

    body = client.get(f"/api/v1/analysis-runs/{run_id}/results").json()
    by_ord = {s["scene"]["ordinal"]: s for s in body["scenes"]}
    # single-paragraph scenes render without error
    for ordinal in (3, 5, 6, 13):
        assert by_ord[ordinal]["scene"]["is_single_paragraph"] is True
        assert by_ord[ordinal]["analysis_artifact"] is not None
    # offline-recovered scenes are marked but not hidden
    assert by_ord[5]["analysis_artifact"]["offline_recovered"] is True
    assert by_ord[13]["analysis_artifact"]["offline_recovered"] is True
    assert by_ord[9]["analysis_artifact"]["offline_recovered"] is False


def test_evidence_ordered_by_prose_position(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _b, _c, run, _rev, _scenes, _p = _seed_completed_run(session, scene_specs=_RUN55_SPECS)
        run_id = run.id

    body = client.get(f"/api/v1/analysis-runs/{run_id}/results").json()
    first = body["scenes"][0]
    order = [e["order_index"] for e in first["evidence"]]
    assert order == sorted(order)


def test_scene_analysis_and_paragraphs_endpoints(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _b, _c, run, _rev, scenes, _p = _seed_completed_run(session, scene_specs=_RUN55_SPECS)
        run_id = run.id
        scene5_id = scenes[4].id
        scene9_id = scenes[8].id

    single = client.get(f"/api/v1/scenes/{scene5_id}/analysis")
    assert single.status_code == 200, single.text
    assert single.json()["analysis_artifact"]["offline_recovered"] is True

    paras = client.get(f"/api/v1/scenes/{scene9_id}/paragraphs")
    assert paras.status_code == 200, paras.text
    body = paras.json()
    assert len(body["paragraphs"]) == 16
    assert all(p["in_scene"] for p in body["paragraphs"])

    del run_id


def test_export_json_and_markdown(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _b, _c, run, _rev, _scenes, _p = _seed_completed_run(session, scene_specs=_RUN55_SPECS)
        run_id = run.id

    js = client.get(f"/api/v1/analysis-runs/{run_id}/results/export?format=json")
    assert js.status_code == 200
    assert "attachment" in js.headers["content-disposition"]
    assert len(js.json()["scenes"]) == 14

    md = client.get(f"/api/v1/analysis-runs/{run_id}/results/export?format=markdown")
    assert md.status_code == 200
    text = md.text
    assert "# 分析结果：Run #" in text
    assert "Scene 总数：14" in text
    assert "## Scene 01" in text
    # markdown must not embed full chapter prose paragraph bodies
    assert "正文段落1内容" not in text


def test_results_do_not_leak_credentials_or_raw_response(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _b, _c, run, _rev, _scenes, _p = _seed_completed_run(session, scene_specs=_RUN55_SPECS)
        run_id = run.id

    raw = client.get(f"/api/v1/analysis-runs/{run_id}/results").text.lower()
    for banned in [
        "api_key",
        "authorization",
        "workspace_id",
        "base_url",
        "dashscope.aliyuncs.com",
        "raw_response",
        "input_snapshot",
    ]:
        assert banned not in raw


def test_incomplete_run_not_disguised_as_complete(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _b, _c, run, _rev, _scenes, _p = _seed_completed_run(session, scene_specs=_RUN55_SPECS)
        run.status = "scene_analysis_partial"
        session.commit()
        run_id = run.id

    resp = client.get(f"/api/v1/analysis-runs/{run_id}/results")
    assert resp.status_code == 409
    detail = resp.json().get("detail") or resp.json()
    assert detail["error_code"] == "RUN_NOT_COMPLETED"
