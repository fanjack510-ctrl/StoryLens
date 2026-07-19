"""Read-only assembly of completed Scene Analysis results (zero model calls).

Builds the results bundle consumed by the desktop reader and the JSON/Markdown
exporters. Only valid artifacts of the requested run are returned; no cloud raw
responses, credentials, base URLs, or workspace identifiers are exposed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisArtifact,
    AnalysisEvidence,
    AnalysisRun,
    BoundaryRevision,
    Chapter,
    ModelInvocation,
    Paragraph,
    Scene,
)

# Analysis field -> stable evidence group used in the "证据" tab.
EVIDENCE_FIELD_GROUPS: list[tuple[str, str]] = [
    ("entry_state", "entry_state"),
    ("goal", "goal"),
    ("obstacle", "obstacle"),
    ("key_actions", "key_actions"),
    ("turning_point", "turning_point"),
    ("outcome", "outcome"),
    ("unresolved_question", "unresolved_question"),
]


def _evidence_group(field_path: str) -> str:
    head = field_path.split(".", 1)[0]
    return head


@dataclass(frozen=True)
class SceneResultBundle:
    scene: Scene
    artifact: AnalysisArtifact | None
    analysis: dict
    evidence: list[dict]
    paragraph_count: int
    is_single_paragraph: bool
    offline_recovered: bool
    provider: str
    model: str
    illegal_evidence: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class RunResultsBundle:
    run: AnalysisRun
    chapter: Chapter
    boundary_revision: BoundaryRevision | None
    scenes: list[SceneResultBundle]
    summary: dict


def _chapter_paragraph_ids(session: Session, chapter_id: int) -> list[str]:
    return list(
        session.scalars(
            select(Paragraph.id)
            .where(Paragraph.chapter_id == chapter_id)
            .order_by(Paragraph.paragraph_index)
        )
    )


def _scene_allowed_ids(ordered_ids: list[str], scene: Scene) -> list[str]:
    try:
        start = ordered_ids.index(scene.start_paragraph_id)
        end = ordered_ids.index(scene.end_paragraph_id)
    except ValueError:
        return []
    if start > end:
        start, end = end, start
    return ordered_ids[start : end + 1]


def _scene_succeeded_invocation_exists(
    invocations: list[ModelInvocation], scene: Scene
) -> bool:
    for inv in invocations:
        if inv.status != "succeeded":
            continue
        try:
            snap = json.loads(inv.input_snapshot_json or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(snap, dict):
            continue
        pids = snap.get("paragraph_ids")
        if isinstance(pids, list) and pids:
            if pids[0] == scene.start_paragraph_id and pids[-1] == scene.end_paragraph_id:
                return True
        if snap.get("scene_id") == scene.scene_key:
            return True
    return False


def _valid_scene_artifact(
    session: Session, run_id: int, scene_id: int
) -> AnalysisArtifact | None:
    return session.scalar(
        select(AnalysisArtifact)
        .where(
            AnalysisArtifact.run_id == run_id,
            AnalysisArtifact.artifact_type == "scene_analysis",
            AnalysisArtifact.subject_id == str(scene_id),
            AnalysisArtifact.validation_status == "valid",
        )
        .order_by(AnalysisArtifact.id.desc())
    )


def _artifact_evidence(session: Session, artifact_id: int) -> list[AnalysisEvidence]:
    return list(
        session.scalars(
            select(AnalysisEvidence)
            .where(AnalysisEvidence.artifact_id == artifact_id)
            .order_by(AnalysisEvidence.id)
        )
    )


def build_scene_bundle(
    session: Session,
    run: AnalysisRun,
    scene: Scene,
    ordered_ids: list[str],
    invocations: list[ModelInvocation],
) -> SceneResultBundle:
    allowed = _scene_allowed_ids(ordered_ids, scene)
    allowed_set = set(allowed)
    paragraph_count = len(allowed)
    artifact = _valid_scene_artifact(session, run.id, scene.id)
    analysis: dict = {}
    evidence_out: list[dict] = []
    illegal: list[dict] = []
    if artifact is not None:
        try:
            analysis = json.loads(artifact.payload_json)
        except json.JSONDecodeError:
            analysis = {}
        rows = _artifact_evidence(session, artifact.id)
        index_of = {pid: pos for pos, pid in enumerate(ordered_ids)}
        for row in rows:
            in_scope = row.paragraph_id in allowed_set
            item = {
                "field_path": row.field_path,
                "group": _evidence_group(row.field_path),
                "paragraph_id": row.paragraph_id,
                "in_scope": in_scope,
                "order_index": index_of.get(row.paragraph_id, 10**9),
            }
            evidence_out.append(item)
            if not in_scope:
                illegal.append(
                    {"field_path": row.field_path, "paragraph_id": row.paragraph_id}
                )
        evidence_out.sort(key=lambda item: (item["order_index"], item["field_path"]))
    offline_recovered = artifact is not None and not _scene_succeeded_invocation_exists(
        invocations, scene
    )
    return SceneResultBundle(
        scene=scene,
        artifact=artifact,
        analysis=analysis,
        evidence=evidence_out,
        paragraph_count=paragraph_count,
        is_single_paragraph=scene.start_paragraph_id == scene.end_paragraph_id,
        offline_recovered=offline_recovered,
        provider=run.provider,
        model=run.model,
        illegal_evidence=illegal,
    )


def _summary(
    scenes: list[SceneResultBundle],
    boundary_revision: BoundaryRevision | None,
) -> dict:
    total = len(scenes)
    single = sum(1 for item in scenes if item.is_single_paragraph)
    longest = max(scenes, key=lambda item: item.paragraph_count, default=None)
    manual_added = sum(
        1 for item in scenes if item.scene.boundary_source == "user_added"
    )
    model_accepted = sum(
        1 for item in scenes if item.scene.boundary_source == "model_accepted"
    )
    user_conflict = sum(
        1
        for item in scenes
        if item.scene.boundary_source == "user_accepted_model_conflict"
    )
    scenes_with_evidence = sum(
        1 for item in scenes if any(e["in_scope"] for e in item.evidence)
    )
    scenes_with_artifact = sum(1 for item in scenes if item.artifact is not None)
    return {
        "total_scene_count": total,
        "coverage_rate": boundary_revision.coverage_rate if boundary_revision else None,
        "single_paragraph_scene_count": single,
        "longest_scene_ordinal": longest.scene.ordinal if longest else None,
        "longest_scene_paragraph_count": longest.paragraph_count if longest else 0,
        "manual_added_boundary_count": manual_added,
        "model_accepted_boundary_count": model_accepted,
        "user_accepted_conflict_count": user_conflict,
        "artifact_coverage_rate": (scenes_with_artifact / total) if total else 0.0,
        "evidence_coverage_rate": (scenes_with_evidence / total) if total else 0.0,
        "offline_recovered_scene_count": sum(
            1 for item in scenes if item.offline_recovered
        ),
    }


def build_run_results(session: Session, run: AnalysisRun) -> RunResultsBundle:
    chapter = session.get(Chapter, int(run.subject_id))
    if chapter is None:
        raise ValueError("CHAPTER_NOT_FOUND")
    scenes = list(
        session.scalars(
            select(Scene)
            .where(Scene.created_by_run_id == run.id)
            .order_by(Scene.ordinal)
        )
    )
    boundary_revision = session.scalar(
        select(BoundaryRevision)
        .where(BoundaryRevision.analysis_run_id == run.id)
        .order_by(BoundaryRevision.revision_number.desc())
    )
    ordered_ids = _chapter_paragraph_ids(session, chapter.id)
    invocations = list(
        session.scalars(
            select(ModelInvocation).where(
                ModelInvocation.run_id == run.id,
                ModelInvocation.task_type == "scene_analysis",
            )
        )
    )
    bundles = [
        build_scene_bundle(session, run, scene, ordered_ids, invocations)
        for scene in scenes
    ]
    return RunResultsBundle(
        run=run,
        chapter=chapter,
        boundary_revision=boundary_revision,
        scenes=bundles,
        summary=_summary(bundles, boundary_revision),
    )
