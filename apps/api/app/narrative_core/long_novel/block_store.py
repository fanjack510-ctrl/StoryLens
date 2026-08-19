"""Where a paid block extraction is kept, so the next run does not buy it again.

`long_novel_blocks` was built for this and stood empty: fifteen tables, zero rows, and every
re-analysis paying for the same extraction a second time. This is the connection.

**What may be reused, and what may not.** The key is `provider_input_fingerprint` and nothing
else — the design's own rule, because that value hashes the exact payload that would be sent,
while every component hash describes which inputs were *selected* rather than what was
assembled. So a stored asset is reused only when the call about to be made is byte-for-byte the
call that produced it: same text, same carry-in, same prompt, same deltas, same model.

That rules out what looked like the case worth wanting — and it turns out to rule it out
correctly. 拆文 and 评测 read the same book with different L1 delta sets, so their payloads
differ and neither can serve the other. The obvious objection was that 拆文's asset is a strict
superset of the diagnostic's, deltas being additive by INV-P1, so it should be allowed to serve
a diagnostic reading.

**It should not, and that is measured rather than argued.** Replaying three blocks of
《一梦如初》 at temperature 0, each arm run twice so the noise floor was known, a run with the
拆文 delta on came back with FEWER items in 11 of the 12 fields both modes share and more in
none — sign test p = 0.0005. Additive in the schema, not additive in effect: a 拆文 block is a
*thinner* diagnostic block plus extras. Serving it to a diagnostic reading would publish a
measurably sparser extraction under the other reading's name, and the run would report success.

The mechanism is attention, not budget — the block was capped at 8 chapters while the budget
afforded 24, and responses ran about 3.5k tokens against 8k — so no amount of re-budgeting makes
this reuse sound. Cross-reading reuse is closed, not deferred. See ``deltas.py``.

What this does deliver is the case that actually recurs: re-analysing a book, and resuming a run
that failed after paying for some of its blocks.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.narrative_core.long_novel.contracts.l1 import BlockAsset

logger = logging.getLogger(__name__)


class SqlBlockAssetStore:
    """Block assets in `long_novel_blocks`, keyed on the provider input fingerprint.

    Reads across runs and writes for one. A book analysed today and re-analysed next week is
    two runs over the same snapshot, and the whole point is that the second one finds the first
    one's work.
    """

    def __init__(
        self,
        session: Session,
        *,
        run_id: int,
        snapshot_id: int,
        revision_hash: str,
        provider_name: str,
        model_name: str,
        semantic_compat_key: str,
        enabled: bool = True,
    ) -> None:
        self._session = session
        self._run_id = int(run_id)
        self._snapshot_id = int(snapshot_id)
        self._revision_hash = str(revision_hash or "")
        self._provider_name = str(provider_name or "")
        self._model_name = str(model_name or "")
        self._compat = str(semantic_compat_key or "")
        self._enabled = bool(enabled)
        self.hits = 0
        self.writes = 0

    def get(self, fingerprint: str) -> BlockAsset | None:
        if not self._enabled or not fingerprint:
            return None
        row = self._session.execute(
            text(
                "SELECT asset_json, run_id FROM long_novel_blocks"
                " WHERE provider_input_fingerprint = :fingerprint"
                "   AND snapshot_id = :snapshot_id"
                "   AND semantic_compat_key = :compat"
                "   AND superseded_by_revision IS NULL"
                "   AND invalidated_at IS NULL"
                "   AND origin = 'real_provider'"
                " ORDER BY id DESC LIMIT 1"
            ),
            {
                "fingerprint": fingerprint,
                "snapshot_id": self._snapshot_id,
                "compat": self._compat,
            },
        ).first()
        if row is None:
            return None
        try:
            asset = BlockAsset.model_validate(json.loads(row[0]))
        except Exception:  # noqa: BLE001
            # A stored asset that no longer validates is a contract that moved without the
            # compat key moving with it. Buying the block again is correct and cheap; failing
            # the run over a cache entry is not.
            logger.warning(
                "long_novel_block_reuse_rejected run_id=%s reason=asset_no_longer_valid",
                self._run_id,
            )
            return None
        self.hits += 1
        logger.info(
            "long_novel_block_reused run_id=%s from_run_id=%s", self._run_id, row[1]
        )
        return asset

    def put(self, fingerprint: str, block_key: str, asset: BlockAsset) -> None:
        if not self._enabled or not fingerprint:
            return
        asset_json = json.dumps(asset.model_dump(mode="json"), ensure_ascii=False)
        payload: dict[str, Any] = {
            "run_id": self._run_id,
            "block_key": block_key,
            "content_key": fingerprint,
            "occurrence_key": fingerprint,
            "duplicate_ordinal": 0,
            "asset_revision": 1,
            "chapter_start_order": _first_chapter(asset),
            "chapter_end_order": _last_chapter(asset),
            "asset_schema_version": "l1/1.0",
            "asset_json": asset_json,
            # Required by the table and worth having: two runs that stored the same asset
            # can be told apart from two that stored different ones without reading the JSON.
            "asset_hash": hashlib.sha256(asset_json.encode("utf-8")).hexdigest(),
            "provider_input_fingerprint": fingerprint,
            "semantic_compat_key": self._compat,
            "snapshot_id": self._snapshot_id,
            "revision_hash": self._revision_hash,
            "created_in_phase": "EXTRACTING_BLOCKS",
            "origin": "real_provider",
            "provider_name": self._provider_name,
            "model_name": self._model_name,
        }
        columns = ", ".join(payload)
        placeholders = ", ".join(f":{c}" for c in payload)
        try:
            self._session.execute(
                text(
                    f"INSERT INTO long_novel_blocks ({columns}, created_at)"
                    f" VALUES ({placeholders}, CURRENT_TIMESTAMP)"
                ),
                payload,
            )
            self.writes += 1
        except Exception:  # noqa: BLE001
            # Storage is an optimisation. A run that cannot write its cache must still finish
            # and hand the reader a report — the alternative is losing a paid extraction to a
            # bookkeeping failure.
            logger.warning(
                "long_novel_block_store_failed run_id=%s block=%s", self._run_id, block_key,
                exc_info=True,
            )


def _first_chapter(asset: BlockAsset) -> int:
    refs = [int(s.chapter_ref) for s in asset.chapter_signals]
    return min(refs) if refs else 0


def _last_chapter(asset: BlockAsset) -> int:
    refs = [int(s.chapter_ref) for s in asset.chapter_signals]
    return max(refs) if refs else 0
