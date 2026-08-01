from sqlalchemy import create_engine, inspect, text

from app.db.models import Base
from app.db.session import migrate_phase_1b, migrate_phase_1c_a7


def test_phase_1a_database_is_migrated_without_deletion(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """CREATE TABLE analysis_runs (
                id INTEGER PRIMARY KEY,
                task_type VARCHAR(100) NOT NULL,
                provider VARCHAR(100) NOT NULL,
                model VARCHAR(255) NOT NULL,
                prompt_version VARCHAR(50) NOT NULL,
                schema_version VARCHAR(50) NOT NULL,
                input_hash VARCHAR(64) NOT NULL,
                status VARCHAR(32) NOT NULL,
                started_at DATETIME NOT NULL,
                completed_at DATETIME,
                raw_output TEXT,
                validated_output TEXT,
                error_message TEXT)
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO analysis_runs (id,task_type,provider,model,prompt_version,schema_version,input_hash,status,started_at) VALUES (1,'old','local','m','v1','v1','x','failed','2026-01-01')"
            )
        )
    migrate_phase_1b(engine)
    columns = {item["name"] for item in inspect(engine).get_columns("analysis_runs")}
    assert {
        "subject_type",
        "subject_id",
        "progress_current",
        "retry_of_run_id",
        "created_at",
        "queued_at",
        "run_started_at",
    } <= columns
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM analysis_runs")) == 1


def test_phase_1c_a7_migration_is_idempotent_and_preserves_history(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'phase1ca7.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO analysis_runs "
                "(id,task_type,subject_type,subject_id,provider,model,prompt_version,"
                "schema_version,input_hash,prompt_hash,status,progress_current,progress_total,"
                "created_at,queued_at,started_at,"
                "execution_mode,analysis_mode,cloud_consent,sends_content_to_cloud,retryable,"
                "status_version) "
                "VALUES (54,'scene_pipeline','chapter','1','fake','fake','v3.5','v1',"
                "'x','y','failed',0,0,'2026-01-01','2026-01-01','2026-01-01',"
                "'cloud','assisted_boundary_review',1,1,0,0)"
            )
        )
    migrate_phase_1c_a7(engine)
    migrate_phase_1c_a7(engine)
    run_columns = {item["name"] for item in inspect(engine).get_columns("analysis_runs")}
    decision_columns = {
        item["name"]
        for item in inspect(engine).get_columns("boundary_review_decisions")
    }
    assert "recovered_from_run_id" in run_columns
    assert {
        "semantic_conflict",
        "conflict_code",
        "deterministic_legal",
        "manual_reason_type",
    } <= decision_columns
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT status FROM analysis_runs WHERE id=54")) == "failed"
        assert connection.scalar(text("PRAGMA integrity_check")) == "ok"
