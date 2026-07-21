"""Read-only run_id=3 regression locator for evidence rules (no model calls)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.services.scene_evidence_validation import (
    EvidenceFieldView,
    SceneEvidenceValidationError,
    scene_analysis_fields_from_result,
    scene_length_band,
    validate_evidence_mapping,
)
from app.schemas.scene import SceneAnalysisResult


def main() -> None:
    db = Path("data/storylens.db")
    if not db.exists():
        print("NO_DB")
        return
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    run = con.execute("select * from analysis_runs where id=3").fetchone()
    if run is None:
        print("NO_RUN_3")
        return
    print(
        "run",
        {
            "id": run["id"],
            "status": run["status"],
            "root_error_code": run["root_error_code"],
            "root_error_message": run["root_error_message"],
            "retryable": run["retryable"],
            "failed_stage": run["failed_stage"],
            "progress": f"{run['progress_current']}/{run['progress_total']}",
        },
    )
    chapter_id = int(run["subject_id"])
    scenes = list(
        con.execute(
            "select id, scene_key, ordinal, start_paragraph_id, end_paragraph_id "
            "from scenes where chapter_id=? order by ordinal",
            (chapter_id,),
        )
    )
    print("scene_count", len(scenes))

    # Prefer validated_output / artifact payloads for the failed scene.
    validated = run["validated_output"]
    raw = run["raw_output"]
    candidates: list[tuple[str, dict]] = []
    for label, blob in (("validated_output", validated), ("raw_output", raw)):
        if not blob:
            continue
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            candidates.append((label, data))

    arts = list(
        con.execute(
            "select subject_id, artifact_type, payload_json from analysis_artifacts "
            "where run_id=3 order by id"
        )
    )
    print("artifact_count", len(arts))

    # Reconstruct paragraph sets per scene.
    paragraphs = list(
        con.execute(
            "select id, paragraph_index from paragraphs where chapter_id=? "
            "order by paragraph_index",
            (chapter_id,),
        )
    )
    pid_by_index = {int(p["paragraph_index"]): p["id"] for p in paragraphs}
    id_to_index = {p["id"]: int(p["paragraph_index"]) for p in paragraphs}

    def scene_pids(scene_row: sqlite3.Row) -> list[str]:
        start = id_to_index.get(scene_row["start_paragraph_id"])
        end = id_to_index.get(scene_row["end_paragraph_id"])
        if start is None or end is None:
            return []
        return [pid_by_index[i] for i in range(start, end + 1) if i in pid_by_index]

    # If we have a SceneAnalysisResult-shaped payload, revalidate under new rules.
    judged = False
    for label, data in candidates:
        payload = data
        if "scene_id" not in payload and isinstance(payload.get("result"), dict):
            payload = payload["result"]
        if "scene_id" not in payload:
            continue
        try:
            result = SceneAnalysisResult.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            print("parse_fail", label, type(exc).__name__)
            continue
        # Match scene
        scene_row = next((s for s in scenes if s["scene_key"] == result.scene_id), None)
        pids = scene_pids(scene_row) if scene_row else []
        if not pids:
            # fallback: union of cited ids
            from app.services.scene_pipeline import evidence_fields

            pids = sorted({pid for _, pid in evidence_fields(result)})
        fields = scene_analysis_fields_from_result(result)
        print(
            "candidate",
            label,
            "scene",
            result.scene_id,
            "paragraph_count",
            len(pids),
            "band",
            scene_length_band(len(pids)),
        )
        try:
            validate_evidence_mapping(
                scene_id=result.scene_id,
                scene_paragraph_ids=pids,
                fields=fields,
            )
            print("new_rule_classification", "ALLOWED_SHARED_OR_VALID")
        except SceneEvidenceValidationError as exc:
            print(
                "new_rule_classification",
                exc.error_code,
                {
                    "paragraph_count": exc.details.get("scene_paragraph_count"),
                    "affected_fields": exc.details.get("affected_fields"),
                    "full_scene_reuse_ratio": exc.details.get("full_scene_reuse_ratio"),
                    "duplicate_rationale_groups": exc.details.get("duplicate_rationale_groups"),
                },
            )
        judged = True
        break

    if not judged:
        # Heuristic: report failed progress scene ordinal
        done = int(run["progress_current"] or 0)
        if 0 <= done < len(scenes):
            scene_row = scenes[done]
            pids = scene_pids(scene_row)
            print(
                "fallback_failed_scene_guess",
                {
                    "ordinal": scene_row["ordinal"],
                    "scene_key": scene_row["scene_key"],
                    "paragraph_count": len(pids),
                    "band": scene_length_band(len(pids)),
                    "note": "no parseable SceneAnalysisResult payload; "
                    "legacy error was BUSINESS_VALIDATION_FAILED / "
                    "indiscriminate whole-scene citation",
                    "new_rule_expectation": (
                        "ALLOWED_SHARED_OR_VALID"
                        if scene_length_band(len(pids)) in {"micro", "short"}
                        else "needs_payload_to_confirm"
                    ),
                },
            )
        else:
            print("unable_to_locate_failed_scene_payload")


if __name__ == "__main__":
    main()
