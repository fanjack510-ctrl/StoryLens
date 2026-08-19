"""A block that has been paid for is not bought again — and the cases where it must be.

`long_novel_blocks` was built for this and stood empty: fifteen tables, zero rows, every
re-analysis paying twice for the same extraction. These tests pin both halves of the rule,
because a cache that reuses too eagerly is worse than no cache: it answers a slightly different
question with an old answer and nothing downstream can tell.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.narrative_core.long_novel.block_store import SqlBlockAssetStore
from app.narrative_core.long_novel.contracts.l1 import BlockAsset

COMPAT = "compat-key-1"


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                -- NOT NULL where the real table has NOT NULL. A permissive fixture is why
                -- the first version of this passed while the real insert failed on a missing
                -- `asset_hash` — the constraint is the thing being tested, so the test has to
                -- carry it.
                CREATE TABLE long_novel_blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    block_key TEXT NOT NULL,
                    content_key TEXT NOT NULL,
                    occurrence_key TEXT NOT NULL,
                    duplicate_ordinal INTEGER,
                    asset_revision INTEGER,
                    chapter_start_order INTEGER NOT NULL,
                    chapter_end_order INTEGER NOT NULL,
                    asset_schema_version TEXT NOT NULL,
                    asset_json TEXT NOT NULL,
                    asset_hash TEXT NOT NULL,
                    provider_input_fingerprint TEXT NOT NULL,
                    semantic_compat_key TEXT NOT NULL,
                    snapshot_id INTEGER NOT NULL,
                    revision_hash TEXT,
                    created_in_phase TEXT NOT NULL,
                    origin TEXT,
                    provider_name TEXT,
                    model_name TEXT,
                    superseded_by_revision INTEGER,
                    invalidated_at DATETIME,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
    return sessionmaker(bind=engine)()


def _asset(chapter: int = 1) -> BlockAsset:
    return BlockAsset.model_validate(
        {
            "asset_schema_version": "l1/1.0",
            "chapter_signals": [
                {
                    "chapter_ref": chapter,
                    "dialogue_paragraphs": 6,
                    "action_paragraphs": 3,
                    "interiority_paragraphs": 2,
                    "scene_breaks": 1,
                    "new_information_beats": 2,
                    "hook_present": True,
                    "evidence": [{"paragraph_ref": 1}],
                }
            ]
        }
    )


def _store(session, *, run_id: int, snapshot_id: int = 7, compat: str = COMPAT, enabled: bool = True):
    return SqlBlockAssetStore(
        session,
        run_id=run_id,
        snapshot_id=snapshot_id,
        revision_hash="rev",
        provider_name="deepseek",
        model_name="deepseek-v4-flash",
        semantic_compat_key=compat,
        enabled=enabled,
    )


def test_a_second_run_over_the_same_book_finds_the_first_runs_work(session) -> None:
    """The case that actually recurs: 重新分析, and resuming a run that failed part-way.

    Reads cross runs on purpose. A book analysed today and re-analysed next week is two runs
    over one snapshot, and the whole point is that the second finds the first one's blocks.
    """
    _store(session, run_id=1).put("fp-a", "BLK-1", _asset())
    session.commit()

    second = _store(session, run_id=2)
    found = second.get("fp-a")

    assert found is not None
    assert found.chapter_signals[0].chapter_ref == 1
    assert second.hits == 1


def test_a_different_payload_is_a_different_question(session) -> None:
    """The fingerprint is the whole key, and it hashes the exact payload that would be sent.

    This is what stops 拆文 reusing 评测's blocks. Their L1 prompts carry different delta sets,
    so the payloads differ and neither can serve the other — even though 拆文's asset is a strict
    superset, deltas being additive by INV-P1. Reuse across readings is sound in principle and
    needs a key that is not the payload hash; doing it by loosening this one would reuse an
    answer to a question nobody asked.
    """
    _store(session, run_id=1).put("fp-diagnostic", "BLK-1", _asset())
    session.commit()

    assert _store(session, run_id=2).get("fp-breakdown") is None


def test_a_stored_block_does_not_cross_snapshots_or_contract_versions(session) -> None:
    # Same payload hash, different book revision or different engine semantics: the text under
    # the block moved, or what the block *means* did, and the stored answer is about neither.
    _store(session, run_id=1).put("fp-a", "BLK-1", _asset())
    session.commit()

    assert _store(session, run_id=2, snapshot_id=99).get("fp-a") is None
    assert _store(session, run_id=2, compat="compat-key-2").get("fp-a") is None


def test_a_superseded_or_invalidated_block_is_not_served(session) -> None:
    _store(session, run_id=1).put("fp-a", "BLK-1", _asset())
    _store(session, run_id=1).put("fp-b", "BLK-2", _asset(2))
    session.execute(text("UPDATE long_novel_blocks SET superseded_by_revision = 2 WHERE provider_input_fingerprint = 'fp-a'"))
    session.execute(text("UPDATE long_novel_blocks SET invalidated_at = CURRENT_TIMESTAMP WHERE provider_input_fingerprint = 'fp-b'"))
    session.commit()

    store = _store(session, run_id=2)
    assert store.get("fp-a") is None
    assert store.get("fp-b") is None


def test_a_stored_asset_that_no_longer_validates_is_bought_again(session) -> None:
    """A contract that moved without its compat key moving with it.

    Buying the block again is correct and costs one call. Failing the run over a cache entry
    would lose a whole analysis to a bookkeeping mistake.
    """
    _store(session, run_id=1).put("fp-a", "BLK-1", _asset())
    session.execute(
        text("UPDATE long_novel_blocks SET asset_json = :junk"),
        {"junk": json.dumps({"chapter_signals": [{"chapter_ref": "not a number"}]})},
    )
    session.commit()

    assert _store(session, run_id=2).get("fp-a") is None


def test_a_write_that_fails_does_not_take_the_run_with_it(session) -> None:
    # Storage is an optimisation. A run that cannot write its cache must still finish and hand
    # the reader a report, rather than lose a paid extraction to a bookkeeping failure.
    session.execute(text("DROP TABLE long_novel_blocks"))
    session.commit()

    store = _store(session, run_id=1)
    store.put("fp-a", "BLK-1", _asset())

    assert store.writes == 0


def test_reuse_is_off_when_the_provider_is_fake(session) -> None:
    """A fixture run must never populate — or read — the store a paid run relies on.

    A scaffolded asset validates and reuses exactly like a real one, which is the whole reason
    the repository refuses to persist anything whose origin is not `real_provider`.
    """
    disabled = _store(session, run_id=1, enabled=False)
    disabled.put("fp-a", "BLK-1", _asset())
    session.commit()

    assert disabled.writes == 0
    assert _store(session, run_id=2).get("fp-a") is None


def test_a_breakdown_extraction_cannot_serve_a_diagnostic_one(session) -> None:
    """The two readings must not share an L1 pass, and this is why.

    The tempting shortcut: a 拆文 asset carries every diagnostic field plus two more, so it
    looks like a strict superset that could be served to a diagnostic run for free. Measured on
    《一梦如初》 — three blocks, temperature 0, each arm run twice so the noise floor was known —
    a run with the 拆文 delta on returned FEWER items in 11 of the 12 shared fields and more in
    none, sign test p = 0.0005. Additive in the schema, not additive in effect: it is a thinner
    diagnostic block plus extras.

    What keeps that shortcut shut is the delta set reaching the payload through the prompt
    hash, so the two modes never produce the same fingerprint. This pins that, because the
    protection is one field in one dict and nothing else would notice its removal.
    """
    from app.narrative_core.long_novel import constants as C, ids
    from app.narrative_core.long_novel.contracts.density import (
        DensityProfileName,
        profile as density_profile,
    )
    from app.narrative_core.long_novel.deltas import DELTAS, delta_prompt, deltas_for
    from app.narrative_core.long_novel.extractor import BlockExtractor
    from app.narrative_core.long_novel.contracts.l1 import CarryForwardState
    from app.narrative_core.long_novel.prompts import prompt_template_hash

    density = density_profile(DensityProfileName.D_STD)
    breakdown = deltas_for({"mode": "story_breakdown"})
    assert [d.key for d in breakdown] == ["story_breakdown"]

    def fingerprint(deltas) -> str:
        extractor = BlockExtractor(
            provider=object(),
            profile=density,
            output_budget=8000,
            prompt_template_hash=prompt_template_hash(density, delta_prompt(deltas)),
        )
        rendered = extractor.render(())
        payload = extractor.build_payload(rendered, CarryForwardState())
        return ids.provider_input_fingerprint(
            "block", C.SEMANTIC_CONTRACT_VERSION, payload
        )

    assert fingerprint(breakdown) != fingerprint(())
    # And a diagnostic run still matches itself, or nothing would ever be reused at all.
    assert fingerprint(()) == fingerprint(())
    # Every registered delta separates, not just this one: an axis-driven delta reusing a
    # diagnostic block would drop the field the axis was confirmed to add.
    for delta in DELTAS:
        assert fingerprint((delta,)) != fingerprint(()), delta.key
