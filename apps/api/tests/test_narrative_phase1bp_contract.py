"""Phase 1B-P contract verification tests (local, not full suite)."""

from __future__ import annotations

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    AnalysisConflict,
    Base,
    NarrativeAsset,
    NarrativeAssetEvidence,
    NarrativeAssetVersion,
    NarrativeEntity,
    NarrativeEntityAlias,
    NarrativeRelation,
    NarrativeRelationEvidence,
    NarrativeRelationVersion,
)
from app.narrative_core.asset_key import build_asset_key, build_relation_key, normalize_entity_name
from app.narrative_core.enums import (
    AssetType,
    ConflictSeverity,
    ConflictStatus,
    EntityLifecycleStatus,
    EntityType,
    EvidenceRole,
    OriginType,
    RelationType,
    ReviewStatus,
)
from app.narrative_core.migrations import (
    NARRATIVE_MIGRATION_ORDER,
    assert_unique_migration_ids,
)
from app.narrative_core.migrations.runner import (
    apply_narrative_phase1bp_migrations,
    apply_narrative_phase1p_migrations,
)


PHASE1B_TABLES = (
    "narrative_entities",
    "narrative_entity_aliases",
    "narrative_assets",
    "narrative_asset_versions",
    "narrative_asset_evidence",
    "narrative_relations",
    "narrative_relation_versions",
    "narrative_relation_evidence",
    "analysis_conflicts",
)


def _fk_engine(url: str):
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def test_migration_ids_001_to_010_unique_and_ordered() -> None:
    assert_unique_migration_ids()
    assert len(NARRATIVE_MIGRATION_ORDER) == 10
    assert NARRATIVE_MIGRATION_ORDER[0] == "20260723_001_schema_migrations"
    assert NARRATIVE_MIGRATION_ORDER[5] == "20260723_006_narrative_entities_aliases"
    assert NARRATIVE_MIGRATION_ORDER[9] == "20260723_010_analysis_conflicts"
    # 001–005 unchanged
    assert NARRATIVE_MIGRATION_ORDER[:5] == (
        "20260723_001_schema_migrations",
        "20260723_002_content_hashes",
        "20260723_003_book_snapshots",
        "20260723_004_analysis_run_scope",
        "20260723_005_analysis_run_stages",
    )


def test_orm_table_names_unique_include_phase1b() -> None:
    names = [table.name for table in Base.metadata.sorted_tables]
    assert len(names) == len(set(names))
    for required in PHASE1B_TABLES:
        assert required in names


def test_create_all_on_empty_temp_db(tmp_path) -> None:
    engine = _fk_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    Base.metadata.create_all(engine)
    apply_narrative_phase1bp_migrations(engine)
    apply_narrative_phase1bp_migrations(engine)  # idempotent
    names = set(inspect(engine).get_table_names())
    for required in PHASE1B_TABLES:
        assert required in names
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT migration_id FROM schema_migrations ORDER BY migration_id")
        ).fetchall()
    applied = {row[0] for row in rows}
    for mid in NARRATIVE_MIGRATION_ORDER:
        assert mid in applied


def test_upgrade_from_simulated_phase1a_preserves_old_run(tmp_path) -> None:
    engine = _fk_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE books (
                    id INTEGER PRIMARY KEY,
                    title VARCHAR(500) NOT NULL,
                    author VARCHAR(255),
                    source_file_name VARCHAR(500) NOT NULL,
                    source_file_hash VARCHAR(64) NOT NULL,
                    import_status VARCHAR(32) NOT NULL,
                    language VARCHAR(32) NOT NULL,
                    revision_number INTEGER NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE chapters (
                    id INTEGER PRIMARY KEY,
                    book_id INTEGER NOT NULL,
                    chapter_index INTEGER NOT NULL,
                    title VARCHAR(500) NOT NULL,
                    word_count INTEGER NOT NULL,
                    section_type VARCHAR(32) NOT NULL,
                    chapter_title VARCHAR(500) NOT NULL,
                    display_title VARCHAR(600) NOT NULL,
                    source_title_line VARCHAR(600) NOT NULL,
                    FOREIGN KEY(book_id) REFERENCES books(id)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE paragraphs (
                    id VARCHAR(32) PRIMARY KEY,
                    book_id INTEGER NOT NULL,
                    chapter_id INTEGER NOT NULL,
                    paragraph_index INTEGER NOT NULL,
                    raw_text TEXT NOT NULL,
                    normalized_text TEXT NOT NULL,
                    char_start INTEGER NOT NULL,
                    char_end INTEGER NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE analysis_runs (
                    id INTEGER PRIMARY KEY,
                    task_type VARCHAR(100) NOT NULL,
                    subject_type VARCHAR(50) NOT NULL,
                    subject_id VARCHAR(100) NOT NULL,
                    provider VARCHAR(100) NOT NULL,
                    model VARCHAR(255) NOT NULL,
                    prompt_version VARCHAR(50) NOT NULL,
                    schema_version VARCHAR(50) NOT NULL,
                    input_hash VARCHAR(64) NOT NULL,
                    prompt_hash VARCHAR(64) NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    progress_current INTEGER NOT NULL,
                    progress_total INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    queued_at DATETIME NOT NULL,
                    started_at DATETIME NOT NULL,
                    execution_mode VARCHAR(16) NOT NULL,
                    analysis_mode VARCHAR(40) NOT NULL,
                    cloud_consent INTEGER NOT NULL,
                    sends_content_to_cloud INTEGER NOT NULL,
                    retryable INTEGER NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE analysis_artifacts (
                    id INTEGER PRIMARY KEY,
                    run_id INTEGER NOT NULL,
                    artifact_type VARCHAR(50) NOT NULL,
                    subject_type VARCHAR(50) NOT NULL,
                    subject_id VARCHAR(100) NOT NULL,
                    schema_version VARCHAR(50) NOT NULL,
                    prompt_version VARCHAR(50) NOT NULL,
                    payload_json TEXT NOT NULL,
                    confidence FLOAT NOT NULL,
                    validation_status VARCHAR(32) NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO analysis_runs ("
                "id,task_type,subject_type,subject_id,provider,model,prompt_version,"
                "schema_version,input_hash,prompt_hash,status,progress_current,progress_total,"
                "created_at,queued_at,started_at,execution_mode,analysis_mode,"
                "cloud_consent,sends_content_to_cloud,retryable"
                ") VALUES ("
                "42,'scene_pipeline','chapter','7','local','m','v1','v1','h','p',"
                "'completed',1,1,'2026-01-01','2026-01-01','2026-01-01','local',"
                "'automatic',0,0,0)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO analysis_artifacts ("
                "id,run_id,artifact_type,subject_type,subject_id,schema_version,"
                "prompt_version,payload_json,confidence,validation_status,created_at"
                ") VALUES (1,42,'scene_analysis','chapter','7','v1','v1','{}',0.5,"
                "'valid','2026-01-01')"
            )
        )
    # Simulate Phase 1A already applied, then Phase 1B-P upgrade.
    apply_narrative_phase1p_migrations(engine)
    apply_narrative_phase1bp_migrations(engine)
    apply_narrative_phase1bp_migrations(engine)
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT subject_type, subject_id, status FROM analysis_runs WHERE id = 42"
            )
        ).fetchone()
        artifact = connection.execute(
            text("SELECT artifact_type FROM analysis_artifacts WHERE id = 1")
        ).fetchone()
    assert row is not None
    assert row[0] == "chapter"
    assert row[1] == "7"
    assert row[2] == "completed"
    assert artifact is not None
    assert artifact[0] == "scene_analysis"
    names = set(inspect(engine).get_table_names())
    for required in PHASE1B_TABLES:
        assert required in names


def test_foreign_key_targets_exist() -> None:
    """Every Phase 1B FK target table is present in metadata."""
    table_by_name = {t.name: t for t in Base.metadata.sorted_tables}
    for table_name in PHASE1B_TABLES:
        table = table_by_name[table_name]
        for fk in table.foreign_keys:
            assert fk.column.table.name in table_by_name


def test_stable_row_separated_from_version_row() -> None:
    asset_cols = {c.name for c in NarrativeAsset.__table__.columns}
    version_cols = {c.name for c in NarrativeAssetVersion.__table__.columns}
    assert "asset_key" in asset_cols
    assert "summary" not in asset_cols
    assert "title" in version_cols
    assert "review_status" in version_cols
    assert "is_canonical" in version_cols
    assert "asset_key" not in version_cols

    relation_cols = {c.name for c in NarrativeRelation.__table__.columns}
    rel_version_cols = {c.name for c in NarrativeRelationVersion.__table__.columns}
    assert "relation_key" in relation_cols
    assert "source_asset_id" in relation_cols
    assert "summary" not in relation_cols
    assert "review_status" in rel_version_cols
    assert "is_canonical" in rel_version_cols


def test_review_status_and_origin_enums() -> None:
    assert {s.value for s in ReviewStatus} == {
        "candidate",
        "confirmed",
        "corrected",
        "rejected",
    }
    assert {s.value for s in OriginType} == {"model", "user", "migrated", "system"}
    assert AssetType.FORESHADOWING == "foreshadowing"
    assert RelationType.PAYS_OFF == "pays_off"
    assert EntityType.CHARACTER == "character"
    assert EntityLifecycleStatus.ACTIVE == "active"
    # lifecycle must not encode candidate/confirmed
    assert "candidate" not in {s.value for s in EntityLifecycleStatus}


def test_lock_independent_of_review_status() -> None:
    assert "is_locked" in {c.name for c in NarrativeAsset.__table__.columns}
    assert "is_locked" in {c.name for c in NarrativeRelation.__table__.columns}
    assert "is_locked" in {c.name for c in NarrativeEntity.__table__.columns}
    assert "review_status" not in {c.name for c in NarrativeAsset.__table__.columns}
    assert "review_status" in {c.name for c in NarrativeAssetVersion.__table__.columns}


def test_evidence_requires_snapshot_and_hash_and_offsets() -> None:
    for model in (NarrativeAssetEvidence, NarrativeRelationEvidence):
        cols = {c.name for c in model.__table__.columns}
        assert "book_snapshot_id" in cols
        assert "snapshot_paragraph_id" in cols
        assert "paragraph_content_hash" in cols
        assert "start_offset" in cols
        assert "end_offset" in cols
        assert "source_scene_id" in cols
        # scene nullable; paragraph not
        assert model.__table__.c.snapshot_paragraph_id.nullable is False
        assert model.__table__.c.source_scene_id.nullable is True
        assert model.__table__.c.book_snapshot_id.nullable is False
    assert EvidenceRole.SUPPORT == "support"


def test_analysis_conflict_status_severity() -> None:
    assert {s.value for s in ConflictStatus} == {"open", "resolved", "dismissed"}
    assert {s.value for s in ConflictSeverity} == {"info", "warning", "blocking"}
    cols = {c.name for c in AnalysisConflict.__table__.columns}
    assert {
        "conflict_type",
        "left_ref_type",
        "left_ref_id",
        "right_ref_type",
        "right_ref_id",
        "severity",
        "status",
        "resolution_json",
    } <= cols


def test_canonical_unique_contract_asset(tmp_path) -> None:
    engine = _fk_engine(f"sqlite:///{tmp_path / 'canon_asset.db'}")
    Base.metadata.create_all(engine)
    apply_narrative_phase1bp_migrations(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO books (id,title,source_file_name,source_file_hash,"
                "import_status,language,revision_number,import_diagnostics_json,created_at) VALUES "
                "(1,'t','f','h','imported','zh-CN',1,'{}','2026-01-01')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO narrative_assets (id,book_id,asset_key,lifecycle_status,"
                "is_locked,created_at,updated_at) VALUES "
                "(1,1,'na_test','active',0,'2026-01-01','2026-01-01')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO narrative_asset_versions ("
                "id,asset_id,asset_type,title,summary,narrative_function,attributes_json,"
                "confidence,importance,source_fingerprint,origin_type,review_status,"
                "is_canonical,created_at) VALUES "
                "(1,1,'event','a','','','{}',0,0,'','model','confirmed',1,'2026-01-01')"
            )
        )
    with engine.begin() as connection:
        try:
            connection.execute(
                text(
                    "INSERT INTO narrative_asset_versions ("
                    "id,asset_id,asset_type,title,summary,narrative_function,attributes_json,"
                    "confidence,importance,source_fingerprint,origin_type,review_status,"
                    "is_canonical,created_at) VALUES "
                    "(2,1,'event','b','','','{}',0,0,'','model','confirmed',1,'2026-01-01')"
                )
            )
            raised = False
        except IntegrityError:
            raised = True
    assert raised


def test_canonical_unique_contract_relation(tmp_path) -> None:
    engine = _fk_engine(f"sqlite:///{tmp_path / 'canon_rel.db'}")
    Base.metadata.create_all(engine)
    apply_narrative_phase1bp_migrations(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO books (id,title,source_file_name,source_file_hash,"
                "import_status,language,revision_number,import_diagnostics_json,created_at) VALUES "
                "(1,'t','f','h','imported','zh-CN',1,'{}','2026-01-01')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO narrative_assets (id,book_id,asset_key,lifecycle_status,"
                "is_locked,created_at,updated_at) VALUES "
                "(1,1,'na_a','active',0,'2026-01-01','2026-01-01'),"
                "(2,1,'na_b','active',0,'2026-01-01','2026-01-01')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO narrative_relations ("
                "id,book_id,source_asset_id,target_asset_id,relation_key,"
                "lifecycle_status,is_locked,created_at,updated_at) VALUES "
                "(1,1,1,2,'nr_test','active',0,'2026-01-01','2026-01-01')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO narrative_relation_versions ("
                "id,relation_id,relation_type,summary,attributes_json,confidence,"
                "importance,source_fingerprint,origin_type,review_status,"
                "is_canonical,created_at) VALUES "
                "(1,1,'causes','','{}',0,0,'','model','confirmed',1,'2026-01-01')"
            )
        )
    with engine.begin() as connection:
        try:
            connection.execute(
                text(
                    "INSERT INTO narrative_relation_versions ("
                    "id,relation_id,relation_type,summary,attributes_json,confidence,"
                    "importance,source_fingerprint,origin_type,review_status,"
                    "is_canonical,created_at) VALUES "
                    "(2,1,'causes','','{}',0,0,'','model','confirmed',1,'2026-01-01')"
                )
            )
            raised = False
        except IntegrityError:
            raised = True
    assert raised


def test_protocol_modules_importable() -> None:
    from app.narrative_core.contracts import (
        AnalysisConflictService,
        AnalysisRunService,
        BookSnapshotRepository,
        NarrativeAssetService,
        NarrativeEntityService,
        NarrativeRelationService,
        SnapshotValidationGateway,
    )
    from app.narrative_core.contracts.dto import (
        EvidenceBindingDTO,
        PatternMapAssetProjectionDTO,
    )

    assert NarrativeEntityService is not None
    assert NarrativeAssetService is not None
    assert NarrativeRelationService is not None
    assert AnalysisConflictService is not None
    assert SnapshotValidationGateway is not None
    assert BookSnapshotRepository is not None
    assert AnalysisRunService is not None
    assert EvidenceBindingDTO is not None
    assert PatternMapAssetProjectionDTO is not None


def test_pattern_dto_not_coupled_to_orm_tables() -> None:
    """Pattern Map frontend DTO must not imply narrative_patterns ORM tables."""
    from pathlib import Path

    names = {t.name for t in Base.metadata.sorted_tables}
    assert "narrative_patterns" not in names
    assert "pattern_nodes" not in names
    assert "pattern_evidence" not in names
    draft = (
        Path(__file__).resolve().parents[2]
        / "desktop"
        / "src"
        / "features"
        / "narrativePattern"
        / "contracts"
        / "patternMap.draft.ts"
    )
    assert draft.is_file()
    text_body = draft.read_text(encoding="utf-8")
    assert "relatedAssetIds" in text_body
    assert "paragraphContentHash" in text_body
    assert "CREATE TABLE" not in text_body


def test_asset_key_not_python_hash() -> None:
    key_a = build_asset_key(book_id=1, asset_type="event", stable_label="开门")
    key_b = build_asset_key(book_id=1, asset_type="event", stable_label="开门")
    key_c = build_asset_key(book_id=2, asset_type="event", stable_label="开门")
    assert key_a == key_b
    assert key_a != key_c
    assert key_a.startswith("na_")
    rel = build_relation_key(
        book_id=1, source_asset_id=1, target_asset_id=2, relation_type="causes"
    )
    assert rel.startswith("nr_")
    assert normalize_entity_name("  A  B ") == "a b"


def test_alias_unique_and_entity_columns() -> None:
    cols = {c.name for c in NarrativeEntityAlias.__table__.columns}
    assert "normalized_alias" in cols
    assert "review_status" in cols
    assert "canonical_name" not in cols
    # UniqueConstraint present
    constraint_names = {c.name for c in NarrativeEntityAlias.__table__.constraints}
    assert "uq_narrative_entity_aliases_entity_normalized" in constraint_names
