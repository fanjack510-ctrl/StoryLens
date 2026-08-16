"""Phase 1 Foundation acceptance tests (CHG-20260812-088).

These are the T0/T1 contract tests plus the G3/G4 durability tests named in the frozen
migration plan. Where a test maps to a numbered acceptance test in
``07_TEST_ACCEPTANCE_STRATEGY.md`` the id is in the test name, so a future reader can find
the requirement rather than guessing at intent.

The bias throughout is to assert the property that *silently* fails. Anything that raises on
its own needs no test here.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect, text

from app.db.models import Base
from app.narrative_core.long_novel import constants as C
from app.narrative_core.long_novel import ids
from app.narrative_core.long_novel.budget import ContextCosts, joint_resolve
from app.narrative_core.long_novel.contracts.density import (
    PROFILES,
    derive_per_block_fixed_tokens,
    derive_per_chapter_tokens,
    max_chapters_per_block,
    profile,
)
from app.narrative_core.long_novel.contracts.enums import RunPhase, Topic, UnitKind
from app.narrative_core.long_novel.errors import (
    LOCALLY_REPAIRABLE,
    FailureClass,
    LongNovelError,
    LongNovelErrorCode,
    failure_class,
)
from app.narrative_core.long_novel.invariants import InvariantValidator
from app.narrative_core.long_novel.mention_binding import EmittedMention, bind_mention_occurrences
from app.narrative_core.long_novel.provider_io import (
    RepairDecision,
    detect_truncation,
    plan_repair,
    recover_json,
)
from app.narrative_core.long_novel.repository import LongNovelRepository
from app.narrative_core.long_novel.usage import ScriptClass, TokenCalibrator, UsageRecorder
from app.narrative_core.migrations.runner import LONG_NOVEL_TABLES, apply_narrative_migrations

# The reference configuration the frozen contracts publish figures for (01 §4.2).
REFERENCE_COSTS = ContextCosts(
    system_prompt_tokens=3_000,
    prompt_frame_tokens=1_200,
    schema_tokens=1_800,
    provider_envelope_tokens=400,
)
REFERENCE_CHAPTER_TOKENS = 4_041
REFERENCE_PARAGRAPHS_PER_CHAPTER = 21


@pytest.fixture()
def engine():
    """A migrated database with foreign keys ENFORCED and the parent rows present.

    ``PRAGMA foreign_keys=ON`` is set explicitly rather than left to chance. The
    application registers a global ``Engine`` connect listener that turns enforcement on
    for every engine in the process, so whether these tests ran with or without foreign
    keys depended on whether some *other* test had imported ``app.db.session`` first —
    passing alone and failing in the full suite. Production always runs with enforcement
    on, so the fixture pins the strict condition.
    """
    path = os.path.join(tempfile.mkdtemp(), "long_novel_phase1.db")
    eng = create_engine(f"sqlite:///{path}")

    @event.listens_for(eng, "connect")
    def _enforce_foreign_keys(dbapi_connection, _record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=eng)
    apply_narrative_migrations(eng)

    # Parent rows for the foreign keys the long_novel tables declare. Without them the
    # inserts in these tests are only legal while enforcement happens to be off.
    # Built through the ORM so each model's Python-side NOT NULL defaults apply; hand-written
    # INSERTs miss them and break again every time a column is added.
    from sqlalchemy.orm import sessionmaker

    from app.db.models import Book, WholeBookRun

    seed = sessionmaker(bind=eng)()
    seed.add(Book(id=1, title="fixture", source_file_name="fixture.txt", source_file_hash="h"))
    seed.flush()
    seed.add(WholeBookRun(id=1, book_id=1, idempotency_key="fixture-run"))
    seed.commit()
    seed.close()
    return eng


# =====================================================================  identity


def test_t0_no_provider_array_ordinal_reaches_any_key():
    """The defect that cost the most design rounds: an array index inside an identity.

    A response reordered but otherwise identical must produce identical keys all the way up
    the chain, or a cosmetic reordering invalidates the whole book.
    """
    paragraph_text = "老王看着窗外，王主任推门进来。"
    occurrence = ids.paragraph_occurrence_key("cho-x", "hash-p1", 0)
    forward, _ = bind_mention_occurrences(
        [EmittedMention("老王", 1, "c0"), EmittedMention("王主任", 1, "c1")],
        {1: paragraph_text},
        {1: occurrence},
    )
    reversed_, _ = bind_mention_occurrences(
        [EmittedMention("王主任", 1, "c1"), EmittedMention("老王", 1, "c0")],
        {1: paragraph_text},
        {1: occurrence},
    )
    assert {m.mention_key for m in forward} == {m.mention_key for m in reversed_}

    lent_forward = ids.provisional_entity_key("blk-occ", [m.mention_key for m in forward])
    lent_reversed = ids.provisional_entity_key("blk-occ", [m.mention_key for m in reversed_])
    assert lent_forward == lent_reversed


def test_t0_57_split_yields_two_distinct_canonical_entities():
    """Splitting one provisional cluster must give two different ``CHR-*``.

    Anchoring on the ``LENT-*`` made both sides hash identically, so this test was
    unpassable by construction — it is the reason the anchor is a mention.
    """
    men_a = ids.mention_key("p-occ-1", "老王", 0)
    men_b = ids.mention_key("p-occ-2", "老王", 0)
    assert men_a != men_b
    assert ids.entity_key(men_a) != ids.entity_key(men_b)


def test_t0_43_late_alias_does_not_rekey_an_entity():
    """A later-discovered alias adds a later mention and must not move the anchor."""
    early = ids.mention_key("p-occ-1", "老王", 0)
    late = ids.mention_key("p-occ-9", "王主任", 0)
    anchor_before = ids.narrative_earliest_mention([(1, 1, 0, early)])
    anchor_after = ids.narrative_earliest_mention([(1, 1, 0, early), (9, 2, 0, late)])
    assert ids.entity_key(anchor_before) == ids.entity_key(anchor_after)


def test_t0_69_evidence_carries_no_ordinal_and_is_shared():
    """One evidence row per paragraph occurrence, shared by every fact citing it."""
    occurrence = ids.paragraph_occurrence_key("cho-1", "hash-p", 0)
    assert ids.evidence_id(occurrence) == ids.evidence_id(occurrence)
    other = ids.paragraph_occurrence_key("cho-1", "hash-p", 1)  # identical text, second time
    assert ids.evidence_id(occurrence) != ids.evidence_id(other)


def test_t0_55_fact_key_needs_payload_and_primary_evidence():
    """Same payload at different paragraphs must key differently (T0-22 agrees with this)."""
    body = {"summary": "他推开门"}
    e1 = ids.evidence_id(ids.paragraph_occurrence_key("cho-1", "h1", 0))
    e2 = ids.evidence_id(ids.paragraph_occurrence_key("cho-2", "h2", 0))
    assert ids.fact_key("event", body, [e1], prefix="EVT") != ids.fact_key("event", body, [e2], prefix="EVT")
    # identical payload AND identical primary evidence is the same fact, deduplicated
    assert ids.fact_key("event", body, [e1], prefix="EVT") == ids.fact_key("event", body, [e1], prefix="EVT")
    # position must not participate
    moved = {"summary": "他推开门", "chapter_order": 44, "position": 7}
    assert ids.fact_key("event", moved, [e1], prefix="EVT") == ids.fact_key("event", body, [e1], prefix="EVT")


def test_t0_occurrence_identity_refuses_a_null_source_chapter_id():
    """Falling back to position here is what reopens the ordinal cliff."""
    with pytest.raises(LongNovelError) as exc:
        ids.chapter_occurrence_key("hash", "")
    assert exc.value.code is LongNovelErrorCode.OCCURRENCE_LINEAGE_UNVERIFIED


def test_t0_18_id_derivation_is_deterministic_across_processes():
    """Hash randomisation must not reach any key: a resume in a new process must match."""
    script = (
        "import sys; sys.path.insert(0, %r)\n"
        "from app.narrative_core.long_novel import ids\n"
        "print(ids.fact_key('event', {'a': '甲'}, ['EVD-x'], prefix='EVT'))\n"
        "print(ids.provider_input_fingerprint('block', 'v1', {'b': [1, 2], 'a': '乙'}))\n"
        # Anchored to the package's own location, not the working directory: run from the
        # repository root this test used to fail on an import error and read as a broken
        # invariant, which is the most misleading way for a test to fail.
    ) % str(Path(ids.__file__).resolve().parents[3])
    env = dict(os.environ, PYTHONHASHSEED="0")
    first = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env)
    env["PYTHONHASHSEED"] = "12345"
    second = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env)
    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout


def test_t0_canonical_json_is_key_order_independent():
    """Two payloads differing only in key order must not be billed as two inputs."""
    a = ids.provider_input_fingerprint("block", "v1", {"a": 1, "b": 2})
    b = ids.provider_input_fingerprint("block", "v1", {"b": 2, "a": 1})
    assert a == b


# =====================================================================  mention binding


def test_t0_70_repeated_surface_across_clusters_fails_closed():
    """「老王看着老王说道」 with the two mentions on different people must refuse.

    Binding by position would silently swap two identities and propagate the swap up
    ``MEN -> LENT -> CENT -> CHR`` while passing every other invariant.
    """
    text_value = "老王看着老王说道。"
    occurrence = ids.paragraph_occurrence_key("cho-1", "h", 0)
    with pytest.raises(LongNovelError) as exc:
        bind_mention_occurrences(
            [EmittedMention("老王", 1, "cluster-A"), EmittedMention("老王", 1, "cluster-B")],
            {1: text_value},
            {1: occurrence},
        )
    assert exc.value.code is LongNovelErrorCode.MENTION_OCCURRENCE_AMBIGUOUS
    assert exc.value.detail["resolutions"]  # the repair prompt has something to say


def test_t0_70_repeated_surface_in_one_cluster_binds_and_is_permutation_stable():
    """Interchangeable repetitions are safe: the resulting key *set* cannot differ."""
    text_value = "老王看着老王说道。"
    occurrence = ids.paragraph_occurrence_key("cho-1", "h", 0)
    bound, _ = bind_mention_occurrences(
        [EmittedMention("老王", 1, "same"), EmittedMention("老王", 1, "same")],
        {1: text_value},
        {1: occurrence},
    )
    assert {m.surface_occurrence_index_in_paragraph for m in bound} == {0, 1}
    assert len({m.mention_key for m in bound}) == 2


def test_t0_70_single_mention_with_two_occurrences_binds_deterministically():
    text_value = "老王看着老王说道。"
    occurrence = ids.paragraph_occurrence_key("cho-1", "h", 0)
    bound, _ = bind_mention_occurrences(
        [EmittedMention("老王", 1, "c")], {1: text_value}, {1: occurrence}
    )
    assert len(bound) == 1 and bound[0].surface_occurrence_index_in_paragraph == 0


def test_t0_68_surface_absent_from_its_paragraph_is_dropped_not_fatal():
    """No identity is created, so the mention is dropped and reported — not the whole block.

    A real DeepSeek run put one surface in the wrong paragraph and cost an entire block:
    every fact, every chapter signal and three correctly-anchored mentions were discarded to
    punish one bad claim. Creating no identity is safe; discarding valid work is not.
    """
    occurrence = ids.paragraph_occurrence_key("cho-1", "h", 0)
    bound, rejected = bind_mention_occurrences(
        [EmittedMention("张三", 1, "c"), EmittedMention("老王", 1, "c")],
        {1: "老王看着窗外。"},
        {1: occurrence},
    )
    assert [m.surface_norm for m in bound] == ["老王"]
    assert len(rejected) == 1
    assert rejected[0].surface_norm == "张三"
    assert rejected[0].reason == "surface_not_in_paragraph"


def test_t0_68_surplus_mentions_are_dropped_and_counted():
    """One textual 老王 but two claimed: the second binds to nothing and is reported."""
    occurrence = ids.paragraph_occurrence_key("cho-1", "h", 0)
    bound, rejected = bind_mention_occurrences(
        [EmittedMention("老王", 1, "c"), EmittedMention("老王", 1, "c")],
        {1: "老王看着窗外。"},
        {1: occurrence},
    )
    assert len(bound) == 1 and len(rejected) == 1


# =====================================================================  budget


@pytest.mark.parametrize(
    "output_budget,expected",
    [(3_000, (0, 0, 2)), (4_096, (0, 2, 4)), (6_000, (3, 6, 9)),
     (7_000, (4, 7, 12)), (8_000, (6, 9, 14)), (16_000, (19, 25, 34))],
)
def test_t0_published_chapter_bound_table_is_reproduced(output_budget, expected):
    """The frozen table is derived, not typed: recompute every published cell."""
    got = tuple(max_chapters_per_block(profile(name), output_budget) for name in ("D_HIGH", "D_STD", "D_MIN"))
    assert got == expected


def test_t0_25_field_derivation_agrees_with_the_published_profile_totals():
    """Internal consistency of §2.5.2 against §2.5.3, within the declared ±1 %.

    The published totals stay authoritative because the chapter-bound table is a floor
    division of them and is sensitive at the boundary.
    """
    for p in PROFILES.values():
        for derived, published in (
            (derive_per_chapter_tokens(p), p.per_chapter_output_tokens),
            (derive_per_block_fixed_tokens(p), p.per_block_fixed_output_tokens),
        ):
            assert abs(derived - published) / published <= 0.01, p.name


@pytest.mark.parametrize(
    "label,context,p_out,expected",
    [
        ("deepseek probed", 128_000, 8_192, (8_000, "D_HIGH", 6)),
        ("deepseek unprobed", 128_000, 4_096, (4_096, "D_MIN", 4)),
        ("qwen probed", 32_768, 8_192, (7_000, "D_STD", 4)),
        ("qwen unprobed", 32_768, 4_096, (4_096, "D_MIN", 4)),
    ],
)
def test_t0_joint_resolution_matches_the_frozen_resolutions(label, context, p_out, expected):
    """A larger output budget is not always better; the qwen row is the proof.

    At ``O = 8000`` on a 32K window the block drops below viability, so the search steps
    *down* to 7000. ``min(caps)`` would have produced an infeasible plan.
    """
    resolution = joint_resolve(
        context_window=context,
        provider_max_output_tokens=p_out,
        provider_max_output_tokens_source="probed",
        costs=REFERENCE_COSTS,
        mean_chapter_tokens=REFERENCE_CHAPTER_TOKENS,
        mean_paragraphs_per_chapter=REFERENCE_PARAGRAPHS_PER_CHAPTER,
    )
    assert (resolution.output_budget, str(resolution.density_profile), resolution.chapters_per_block) == expected


def test_t0_resolve_raises_output_budget_too_low_before_any_spend():
    with pytest.raises(LongNovelError) as exc:
        joint_resolve(
            context_window=8_000,
            provider_max_output_tokens=4_096,
            provider_max_output_tokens_source="probed",
            costs=REFERENCE_COSTS,
            mean_chapter_tokens=REFERENCE_CHAPTER_TOKENS,
            mean_paragraphs_per_chapter=REFERENCE_PARAGRAPHS_PER_CHAPTER,
        )
    assert exc.value.code is LongNovelErrorCode.OUTPUT_BUDGET_TOO_LOW
    assert exc.value.failure_class is FailureClass.TERMINAL


def test_t0_65_provider_call_topology_is_single_valued():
    """4 primary topics + 0 for chapters + 1 assessment + 1 final. No other counting."""
    assert len(C.PRIMARY_PROVIDER_TOPICS) == 4
    assert C.TOPIC_PROVIDER_CALLS_BEFORE_ASSESSMENT == 4
    assert C.TOPIC_ROWS_BEFORE_ASSESSMENT == 5
    assert not Topic.CHAPTERS.is_provider_backed
    assert sum(1 for t in Topic if t.is_provider_backed) == 5  # 4 primary + assessment
    assert C.full_run_provider_calls(91, 8) == 105
    assert C.full_run_provider_calls(136, 12) == 154


# =====================================================================  provider IO


@pytest.mark.parametrize(
    "raw,kwargs,expected",
    [
        ('{"a":1}', {}, {"a": 1}),
        ("```json\n{\"a\":1}\n```", {}, {"a": 1}),
        ("Sure!\n{\"a\":1}\nDone.", {}, {"a": 1}),
        ('{"a":1,}', {}, {"a": 1}),
        ('{"evts":[]}', {"legal_keys": {"evts": ["events"]}}, {"events": []}),
        ('{"kind":"Same-Person"}', {"legal_enums": {"kind": ["same_person"]}}, {"kind": "same_person"}),
        ('{"a":1}', {"optional_containers": {"mentions": []}}, {"a": 1, "mentions": []}),
    ],
)
def test_t0_46_safe_json_recovery_is_engine_local(raw, kwargs, expected):
    """Every one of these costs zero provider calls."""
    outcome = recover_json(raw, **kwargs)
    assert outcome.recovered and outcome.value == expected


def test_t0_46_ambiguous_rename_is_not_guessed():
    """Two plausible targets is judgement the engine does not have."""
    outcome = recover_json('{"e":[]}', legal_keys={"e": ["events", "evidence"]})
    assert outcome.value == {"e": []} and outcome.steps == []


@pytest.mark.parametrize(
    "raw,expected_code",
    [('{"a":[1,2', LongNovelErrorCode.TRUNCATED_OUTPUT), ("", LongNovelErrorCode.SCHEMA_MISMATCH)],
)
def test_t0_46_unrecoverable_payloads_refuse(raw, expected_code):
    outcome = recover_json(raw)
    assert not outcome.recovered and outcome.code is expected_code


def test_t0_no_reduced_provider_repair_exists():
    """The ladder has three outcomes. A reduced form would lose facts silently."""
    assert {d.value for d in RepairDecision} == {
        "engine_local",
        "full_provider_repair",
        "escalate_at_parent",
    }


@pytest.mark.parametrize(
    "code,payload_tokens,budget,expected",
    [
        (LongNovelErrorCode.JSON_WRAPPER_DAMAGE, 5_000, 20_000, RepairDecision.ENGINE_LOCAL),
        (LongNovelErrorCode.MISSING_REQUIRED_FIELD, 5_000, 20_000, RepairDecision.FULL_PROVIDER_REPAIR),
        (LongNovelErrorCode.MISSING_REQUIRED_FIELD, 30_000, 20_000, RepairDecision.ESCALATE_AT_PARENT),
        (LongNovelErrorCode.TRUNCATED_OUTPUT, 100, 20_000, RepairDecision.ESCALATE_AT_PARENT),
    ],
)
def test_t0_46_repair_ladder_decisions(code, payload_tokens, budget, expected):
    plan = plan_repair(
        code=code,
        parent_payload_tokens=payload_tokens,
        repair_input_budget=budget,
        parent_splittable=True,
    )
    assert plan.decision is expected


def test_t0_truncation_is_distinguished_from_capability_drift():
    """A model that stops short of a budget it declared has an untrustworthy declaration."""
    assert detect_truncation(
        finish_reason="length", raw_text="{", requested_output_tokens=4_096,
        output_tokens=4_096, declared_max_output_tokens=8_192,
    ) is LongNovelErrorCode.CAPABILITY_DRIFT
    assert detect_truncation(
        finish_reason="length", raw_text="{", requested_output_tokens=8_192,
        output_tokens=8_192, declared_max_output_tokens=8_192,
    ) is LongNovelErrorCode.TRUNCATED_OUTPUT
    assert detect_truncation(
        finish_reason="stop", raw_text='{"a":1}', requested_output_tokens=8_192,
        output_tokens=20, declared_max_output_tokens=8_192,
    ) is None


def test_t0_error_taxonomy_is_total():
    """An unclassified code is a contract gap, and must not default to a disposition."""
    for code in LongNovelErrorCode:
        assert isinstance(failure_class(code), FailureClass)
    for code in LOCALLY_REPAIRABLE:
        assert failure_class(code) is FailureClass.LOCALLY_REPAIRABLE


# =====================================================================  migration


def test_t1_migration_creates_all_fifteen_tables_and_the_unit_key_column(engine):
    insp = inspect(engine)
    names = set(insp.get_table_names())
    assert all(table in names for table in LONG_NOVEL_TABLES)
    assert len(LONG_NOVEL_TABLES) == 15
    assert "unit_key" in {c["name"] for c in insp.get_columns("model_invocations")}


def test_t1_migration_is_idempotent_and_recorded_once(engine):
    apply_narrative_migrations(engine)
    apply_narrative_migrations(engine)
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT migration_id FROM schema_migrations WHERE migration_id LIKE '%018%'")
        ).fetchall()
    assert len(rows) == 1


def test_t1_interrupted_migration_converges_on_rerun():
    """Killed after the DDL committed but before the applied-record was written.

    SQLite DDL is transactional, so a kill inside the DDL leaves nothing behind; the
    reachable gap is between that commit and ``_record_applied``. On re-run the tables must
    be recognised as ours and skipped, and the record written — not a second CREATE.
    """
    path = os.path.join(tempfile.mkdtemp(), "interrupted.db")
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(bind=eng)
    apply_narrative_migrations(eng)
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM schema_migrations WHERE migration_id LIKE '%018%'"))

    apply_narrative_migrations(eng)  # must converge, not raise

    names = set(inspect(eng).get_table_names())
    assert all(table in names for table in LONG_NOVEL_TABLES)
    with eng.begin() as conn:
        rows = conn.execute(
            text("SELECT migration_id FROM schema_migrations WHERE migration_id LIKE '%018%'")
        ).fetchall()
    assert len(rows) == 1


def test_t1_name_collision_is_reported_clearly_not_as_a_missing_column():
    """A foreign table wearing one of our names must fail with a readable message.

    Skipping it because the *name* matches and then failing on the first index with
    "no such column: run_id" tells the reader nothing about what actually went wrong.
    """
    from app.narrative_core.errors import NarrativeCoreError

    path = os.path.join(tempfile.mkdtemp(), "collision.db")
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(bind=eng)
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE long_novel_blocks (id INTEGER PRIMARY KEY)"))
    with pytest.raises(NarrativeCoreError) as exc:
        apply_narrative_migrations(eng)
    assert "long_novel_blocks" in str(exc.value) and "already exists" in str(exc.value)


def test_t1_exactly_one_restrict_lock_on_book_snapshots(engine):
    """The retention row IS the lock; a second RESTRICT would be unreleasable."""
    import sqlite3

    raw = sqlite3.connect(engine.url.database)
    holders = [
        table
        for table in inspect(engine).get_table_names()
        for fk in raw.execute(f"PRAGMA foreign_key_list({table})").fetchall()
        if fk[2] == "book_snapshots" and fk[6] == "RESTRICT"
    ]
    assert holders == ["long_novel_snapshot_retentions"]


def test_t1_final_results_uses_a_partial_unique_index(engine):
    """SQLite cannot ADD COLUMN ... UNIQUE, so uniqueness is a separate partial index."""
    import sqlite3

    raw = sqlite3.connect(engine.url.database)
    sql = raw.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name='uq_ln_final_results_run'"
    ).fetchone()
    assert sql and "WHERE" in sql[0]


# =====================================================================  durability


def test_g3_g4_usage_row_survives_a_rolled_back_caller_transaction(engine):
    """A billed call must not vanish because the run's transaction later failed."""
    from sqlalchemy.orm import sessionmaker

    from app.db.models import AnalysisRun

    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    seed = factory()
    # Built through the ORM so the model's own NOT NULL defaults apply; hand-listing them
    # in raw SQL just re-breaks the test every time a column is added.
    seed.add(
        AnalysisRun(
            id=1,
            book_id=1,  # the fixture's book
            provider="deepseek",
            model="deepseek-v4-flash",
            prompt_version="lne.v1",
            schema_version="lne.v1",
            input_hash="seed",
        )
    )
    seed.commit()
    seed.close()

    caller = factory()
    recorder = UsageRecorder(factory)
    row_id = recorder.record(
        run_id=1,
        unit_kind=UnitKind.BLOCK,
        unit_key="BLK-abc",
        provider_name="deepseek",
        model_name="deepseek-v4-flash",
        attempt_no=1,
        request_payload={"x": 1},
        raw_response_text="{}",
        status="success",
        latency_ms=1200,
        input_tokens=1000,
        output_tokens=500,
    )
    caller.rollback()  # the run's own work is lost; the billing row must not be
    caller.close()

    with engine.begin() as conn:
        found = conn.execute(
            text("SELECT unit_key, input_tokens FROM model_invocations WHERE id = :id"),
            {"id": row_id},
        ).first()
    assert found == ("BLK-abc", 1000)


def test_token_calibrator_falls_back_until_it_has_enough_evidence(engine):
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    calibrator = TokenCalibrator(factory)

    first = calibrator.resolve(provider_name="deepseek", model_name="m", script_class=ScriptClass.CJK)
    assert first.tier.value == "default"

    for _ in range(40):
        calibrator.observe(
            provider_name="deepseek", model_name="m", script_class=ScriptClass.CJK,
            chars=1_325, tokens=1_000,
        )
    narrowed = calibrator.resolve(provider_name="deepseek", model_name="m", script_class=ScriptClass.CJK)
    assert narrowed.tier.value == "model_script" and narrowed.observation_count >= 30


def test_token_calibrator_discards_a_zero_token_observation(engine):
    """A provider reporting gap is not a measurement of an infinitely efficient tokenizer."""
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    calibrator = TokenCalibrator(factory)
    calibrator.observe(
        provider_name="p", model_name="m", script_class=ScriptClass.CJK, chars=100, tokens=0
    )
    assert calibrator.resolve(
        provider_name="p", model_name="m", script_class=ScriptClass.CJK
    ).tier.value == "default"


# =====================================================================  persistence


def test_t0_66_tier3_replacement_is_atomic_and_blocks_stay_insert_only(engine):
    """Result, fingerprint, legality and compatibility key move together, or not at all."""
    from sqlalchemy.orm import sessionmaker

    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    repo = LongNovelRepository(session)

    session.execute(
        text(
            """
            INSERT INTO long_novel_topic_results
                (run_id, topic, result_json, result_schema_version, projection_fingerprint,
                 digest_json, digest_fingerprint, semantic_compat_key, snapshot_id,
                 created_in_phase, created_at, provider_input_fingerprint, invalidated_at)
            VALUES (1, 'story', :result, 'v1', 'pf1', '{}', 'df1', 'sci-old', 1,
                    'synthesizing_topics', :now, 'pif-old', :now)
            """
        ),
        {"now": "2026-08-12 00:00:00", "result": '{"v":1}'},
    )
    repo.replace_derived_view(
        table="long_novel_topic_results",
        current_phase=RunPhase.SYNTHESIZING_TOPICS,
        run_id=1,
        unit_identifier="story",
        result_column="result_json",
        result_value='{"v":2}',
        provider_input_fingerprint="pif-new",
        execution_legality_json='{"ok":true}',
        semantic_compat_key="sci-new",
    )
    row = session.execute(
        text(
            "SELECT result_json, provider_input_fingerprint, semantic_compat_key, "
            "asset_revision, invalidated_at FROM long_novel_topic_results WHERE run_id = 1"
        )
    ).first()
    assert row[0] == '{"v":2}' and row[1] == "pif-new" and row[2] == "sci-new"
    assert row[3] == 2 and row[4] is None

    # blocks are not a derived view and must refuse in-place replacement
    with pytest.raises(LongNovelError) as exc:
        repo.replace_derived_view(
            table="long_novel_blocks",
            current_phase=RunPhase.EXTRACTING_BLOCKS,
            run_id=1,
            unit_identifier="BLK-1",
            result_column="asset_json",
            result_value="{}",
            provider_input_fingerprint="x",
            execution_legality_json="{}",
            semantic_compat_key="y",
        )
    assert exc.value.code is LongNovelErrorCode.ASSET_NOT_REPLACEABLE


def test_inv_2_writes_are_phase_guarded(engine):
    from sqlalchemy.orm import sessionmaker

    repo = LongNovelRepository(sessionmaker(bind=engine)())
    with pytest.raises(LongNovelError) as exc:
        repo.replace_derived_view(
            table="long_novel_topic_results",
            current_phase=RunPhase.EXTRACTING_BLOCKS,  # wrong phase
            run_id=1,
            unit_identifier="story",
            result_column="result_json",
            result_value="{}",
            provider_input_fingerprint="p",
            execution_legality_json="{}",
            semantic_compat_key="s",
        )
    assert exc.value.code is LongNovelErrorCode.PHASE_WRITE_FORBIDDEN


def test_scaffolded_asset_cannot_be_stored_in_a_formal_run(engine):
    from sqlalchemy.orm import sessionmaker

    repo = LongNovelRepository(sessionmaker(bind=engine)())
    with pytest.raises(LongNovelError) as exc:
        repo.insert_block_revision(
            current_phase=RunPhase.EXTRACTING_BLOCKS,
            row={"run_id": 1, "origin": "scaffold"},
        )
    assert exc.value.code is LongNovelErrorCode.SCAFFOLD_FORBIDDEN


def test_inv_9_derived_index_is_a_pure_function_of_the_asset(engine):
    """Rebuild must reproduce byte-identically, so the derivation reads only the asset."""
    from sqlalchemy.orm import sessionmaker

    repo = LongNovelRepository(sessionmaker(bind=engine)())
    asset = {
        "events": [
            {"fact_key": "EVT-1", "summary": "他推开门", "evidence": [{"paragraph_ref": 1}]},
            {"fact_key": "EVT-2", "summary": "她转身", "evidence": [{"paragraph_ref": 1}]},
        ]
    }
    kwargs = dict(
        run_id=1,
        block_row_id=7,
        asset_revision=1,
        snapshot_id=3,
        asset=asset,
        paragraph_occurrence_keys={1: "p-occ-1"},
        paragraph_metadata={1: {"chapter_order": 5, "paragraph_content_hash": "h"}},
    )
    first = repo.build_derived_index(**kwargs)
    second = repo.build_derived_index(**kwargs)
    assert json.dumps(first.facts, sort_keys=True) == json.dumps(second.facts, sort_keys=True)
    # two facts citing one paragraph share exactly one evidence row
    assert len(first.evidence) == 1 and len(first.facts) == 2


# =====================================================================  invariants


def test_inv_15_no_canonical_entity_and_no_provisional_entity_in_carry():
    validator = InvariantValidator()
    report = validator.validate_entity_layering(
        l1_asset_keys=["CHR-abc"], carry_keys=["LENT-xyz"], entity_traces={"CHR-abc": ["LENT-x"]}
    )
    messages = " ".join(v.message for v in report.violations)
    assert "CHR-abc appears in an L1 asset" in messages
    assert "LENT-xyz appears in carry state" in messages
    assert "does not trace to any mention" in messages


def test_inv_17_identical_text_at_two_places_does_not_collapse():
    validator = InvariantValidator()
    blocks = [
        {"block_key": "BLK-1", "content_key": "same", "occurrence_key": "occ-1"},
        {"block_key": "BLK-2", "content_key": "same", "occurrence_key": "occ-1"},
    ]
    assert not validator.validate_occurrence_uniqueness(blocks).ok


def test_inv_20_duplicate_ordinal_is_never_sufficient_across_snapshots():
    validator = InvariantValidator()
    report = validator.validate_occurrence_lineage(
        [{"block_key": "BLK-1", "cross_snapshot": True, "lineage_verified": True, "matched_on": "duplicate_ordinal"}]
    )
    assert not report.ok


def test_inv_18_a_provider_unit_without_a_planner_is_a_violation():
    validator = InvariantValidator()
    report = validator.validate_bounded_input(
        [{"unit_kind": "topic", "unit_key": "TOP-1-story", "assembled_input_tokens": 10, "declared_budget": 20}]
    )
    assert not report.ok and "has no planner" in report.violations[0].message


def test_inv_6_long_verbatim_prose_run_is_detected():
    validator = InvariantValidator()
    snapshot = "甲" * 500
    assert not validator.validate_no_prose_copy("乙" * 5 + "甲" * 200, snapshot).ok
    assert validator.validate_no_prose_copy("甲" * 100, snapshot).ok


def test_invariant_report_raises_with_every_violation_not_just_the_first():
    validator = InvariantValidator()
    report = validator.validate_reference_resolution(["a", "b"], [], level="stage")
    with pytest.raises(LongNovelError) as exc:
        report.raise_if_violated()
    assert len(exc.value.detail["violations"]) == 2


# ==========================================================  derived sections vs the contract
#
# Every section below is built by the engine from facts it already holds, with no provider
# call involved. That makes them cheap to get wrong in a way nothing catches: the fake
# provider run exercises the code path but a deterministic builder can still emit a value the
# contract rejects, and the first thing that notices is validation at the end of a paid run
# over the whole book. One such escape has already happened — ``pacing_regions`` emitted the
# Chinese label 高潮 where the contract declares a closed English vocabulary, and it surfaced
# only after 115 real calls had been spent. These tests move that discovery to 0.2 seconds.

def _curve(drives: list[int]) -> tuple[list[dict], list[int]]:
    """Points and their drive ranks, which the point itself no longer carries.

    ``reading_drive`` was ``2×hooks + beats`` and therefore a recombination of two curves
    already on the chart, so it stopped being published. It is still the signal these regions
    are found with — see ``reading_drive_ranks`` — it is just passed in now.
    """
    points = [
        {"chapter_start": i * 8 + 1, "chapter_end": i * 8 + 8} for i, _ in enumerate(drives)
    ]
    return points, list(drives)


def test_pacing_regions_emit_contract_vocabulary_not_display_text():
    from app.narrative_core.long_novel.orchestrator import RunCoordinator
    from app.narrative_core.whole_book_v2.contracts import PacingRegion

    regions = RunCoordinator._pacing_regions(*_curve([90, 92, 88, 91, 50, 10, 8, 12, 9]))
    kinds = {r["type"] for r in regions}
    assert kinds == {"climax", "fatigue"}, kinds
    for region in regions:
        PacingRegion.model_validate(region)      # the step that failed on the paid run
    # The reader-facing label still says it in Chinese; it just lives where prose belongs.
    assert any("高潮" in r["reason"] for r in regions)
    assert any("平缓" in r["reason"] for r in regions)


def test_pacing_regions_ignore_runs_shorter_than_three_bins():
    from app.narrative_core.long_novel.orchestrator import RunCoordinator

    assert RunCoordinator._pacing_regions(*_curve([90, 91, 40, 40, 40])) == []


def test_derived_story_sections_validate_against_the_contract():
    from app.narrative_core.whole_book_v2.contracts import (
        ChronologyEvent, PacingMarker, Storyline, TurningPoint,
    )
    from app.narrative_core.long_novel.orchestrator import RunCoordinator

    lifecycles = [
        {"question": "卷宗去哪了", "chapter_start": 3, "chapter_end": 210, "status": "resolved",
         "importance": 0.9, "events": [{"chapter": 3, "description": "卷宗失踪"},
                                       {"chapter": 210, "description": "在档案室找到"}]},
        {"question": "谁是内鬼", "chapter_start": 40, "chapter_end": 60, "status": "unresolved",
         "importance": 0.4, "events": []},
    ]
    for line in RunCoordinator._storylines(lifecycles):
        Storyline.model_validate(line)

    interpretations = [
        {"title": "第一幕", "chapter_start_order": 1, "chapter_end_order": 120,
         "stage_goal": "查清来历", "turning_point": "档案室失火", "summary": "开端"},
        {"title": "第二幕", "chapter_start_order": 121, "chapter_end_order": 300,
         "stage_goal": "追查", "turning_point": "", "summary": "推进"},
    ]
    for marker in RunCoordinator._event_markers(interpretations, lifecycles):
        PacingMarker.model_validate(marker)
    turns = RunCoordinator._turning_points(interpretations)
    # The stage with no turning point contributes none rather than an empty one.
    assert len(turns) == 1
    for turn in turns:
        TurningPoint.model_validate(turn)
    assert ChronologyEvent is not None


def test_revision_priorities_drop_what_the_contract_cannot_hold():
    from app.narrative_core.long_novel.adapter import build_assessment_section
    from app.narrative_core.whole_book_v2.contracts import RevisionPriority

    section = build_assessment_section({
        "overall_summary": "总评",
        "revision_priorities": [
            {"chapter_ranges": [[10, 20]], "direction": "压缩", "preserve": ["主线"]},
            "把交接提前",
            {"chapter_ranges": [["坏", 5]], "direction": "补写"},
            {"direction": "第四条，超出三档"},
        ],
        "preserve_list": ["开篇铺设", "   ", "关系层次"],
    })
    priorities = section["revision_priorities"]
    assert [p["priority"] for p in priorities] == ["first", "second", "third"]
    assert priorities[2]["chapter_ranges"] == []     # the malformed range, not the whole item
    assert section["preserve_list"] == ["开篇铺设", "关系层次"]
    for priority in priorities:
        RevisionPriority.model_validate(priority)


def test_type_profile_stays_absent_rather_than_claiming_a_genre():
    from app.narrative_core.long_novel.adapter import build_type_profile_section

    assert build_type_profile_section(None) is None
    assert build_type_profile_section({"one_sentence_story": "有故事没类型"}) is None
    profile = build_type_profile_section({"primary_genre": "悬疑", "narrative_drivers": ["秘密"]})
    assert profile["primary_genre"] == "悬疑"
    # The engine measures no genre agreement, so it must not put a number on one.
    assert profile["genre_confidence"] == 0.0


def test_uncounted_block_is_repaired_once_then_kept_not_lost():
    """Missing counters must cost a flat curve segment, never eight chapters of facts.

    The counting rule fails the block into a repair, which is the point. But if the second
    response is uncounted too, dropping the block would throw away every event, thread and
    character change inside it — a far worse outcome for a reader than a flat stretch. The
    shortfall is recorded on the asset instead.
    """
    from app.narrative_core.long_novel.contracts.enums import OutputFidelity
    from app.narrative_core.long_novel.extractor import BlockExtractor

    uncounted = {
        "asset_schema_version": C.ASSET_SCHEMA_VERSION,
        "chapter_signals": [
            {"chapter_ref": 1, "evidence": [{"paragraph_ref": 1}]},
            {"chapter_ref": 2, "evidence": [{"paragraph_ref": 2}]},
        ],
        "events": [],
    }
    class _NeverCalled:
        def complete(self, **_kwargs):  # pragma: no cover - the test must not reach it
            raise AssertionError("validation must not call the provider")

    extractor = BlockExtractor(
        provider=_NeverCalled(),
        profile=profile("D_HIGH"),
        output_budget=16_000,
        prompt_template_hash="test",
    )

    with pytest.raises(LongNovelError) as exc:
        extractor._validate("blk-1", dict(uncounted), expected_chapters=2)
    assert "counter" in exc.value.message

    kept = extractor._accept_uncounted(
        "blk-1", dict(uncounted), exc.value, expected_chapters=2
    )
    assert len(kept.chapter_signals) == 2
    assert kept.output_fidelity is OutputFidelity.REDUCED_BY_SATURATION

    # Any other validation failure still propagates — this yields on the counting rule only.
    other = LongNovelError(
        LongNovelErrorCode.CARDINALITY_VIOLATION, "blk-1: 1 chapter signal(s) for 2 chapter(s)"
    )
    with pytest.raises(LongNovelError):
        extractor._accept_uncounted("blk-1", dict(uncounted), other, expected_chapters=2)


def test_centrality_counts_mentions_so_the_lead_is_the_most_mentioned_character():
    """The protagonist must be the character the book actually talks about most.

    Counting clusters instead of mentions gives everyone who appears in a block the same
    score, so the cast ties and "protagonist" becomes whoever the sort left first. A real
    40-chapter extract named 山羊头 — a ship's figurehead — the lead of a book about 邓肯,
    and the growth tracks followed it.
    """
    from app.narrative_core.long_novel.contracts.l1 import (
        BlockAsset, EvidenceRef, Mention, ProvisionalEntity,
    )
    from app.narrative_core.long_novel.orchestrator import RunCoordinator

    def block(counts: dict[str, int]) -> BlockAsset:
        mentions, entities = [], []
        for surface, times in counts.items():
            start = len(mentions)
            for _ in range(times):
                mentions.append(Mention(
                    surface_norm=surface, paragraph_ref=len(mentions) + 1,
                    evidence=[EvidenceRef(paragraph_ref=len(mentions) + 1)],
                ))
            entities.append(ProvisionalEntity(
                member_mention_indexes=list(range(start, len(mentions))),
                display_surface_norm=surface,
            ))
        return BlockAsset(
            asset_schema_version=C.ASSET_SCHEMA_VERSION,
            mentions=mentions, provisional_entities=entities,
        )

    # 邓肯 is mentioned far more often; 山羊头 appears in exactly as many blocks.
    assets = {
        "blk-1": block({"邓肯": 30, "山羊头": 2}),
        "blk-2": block({"邓肯": 25, "山羊头": 3}),
    }
    ranked = RunCoordinator._resolve_entities(assets)
    names = [row["display_surface_norm"] for row in ranked]
    assert names[0] == "邓肯", names
    # And the score has to separate them, or importance renders 1.0 for the whole cast.
    assert ranked[0]["centrality"] > ranked[1]["centrality"]
