"""Storage for the per-book profile (CHG-20260813-089).

One row per book, not per run. The profile is a **book-level** prerequisite that both the
whole-book engine and the single-chapter pipeline read (10_ADAPTIVE_PROFILE_LAYER §4.0), and
storing it per run would mean a user confirming the same five answers every time they
analysed the same book.

Two states live in the same row. A draft is the engine's proposal; confirming it replaces the
axes in place and stamps ``confirmed_at``. Replacement rather than versioning is deliberate
and matches ADR-03's treatment of derived views: what a user needs is the answer they last
gave, and keeping every intermediate draft would accumulate rows nothing ever reads.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

__all__ = ["BookProfileRepository"]

#: Columns holding JSON documents, and the key each maps to in the profile dict.
_JSON_COLUMNS = {
    "axes_json": "axes",
    "disagreements_json": "disagreements",
    "statistics_json": "statistics",
    "name_deciles_json": "name_deciles",
    "candidate_names_json": "candidate_names",
    "opening_notes_json": "opening_notes",
    "sample_chapters_json": "sample_chapters",
}


class BookProfileRepository:
    """Read and write the profile of one book."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, book_id: int) -> dict[str, Any] | None:
        row = self._session.execute(
            text(
                "SELECT status, snapshot_id, confirmed_at, provider_name, model_name, "
                + ", ".join(_JSON_COLUMNS)
                + " FROM book_profiles WHERE book_id = :book_id"
            ),
            {"book_id": book_id},
        ).mappings().first()
        if row is None:
            return None

        profile: dict[str, Any] = {
            "book_id": book_id,
            "status": row["status"],
            "snapshot_id": row["snapshot_id"],
            "confirmed_at": row["confirmed_at"],
            "provider_name": row["provider_name"],
            "model_name": row["model_name"],
        }
        for column, key in _JSON_COLUMNS.items():
            # A row written by an older build, or hand-edited, must not take the whole
            # profile down: an unreadable column becomes an empty one and the caller sees a
            # profile it can still act on.
            try:
                profile[key] = json.loads(row[column] or "null")
            except (TypeError, ValueError):
                profile[key] = None
            if profile[key] is None:
                profile[key] = [] if key in ("disagreements", "candidate_names", "sample_chapters") else {}
        return profile

    def save_draft(
        self,
        book_id: int,
        draft: Mapping[str, Any],
        *,
        snapshot_id: int = 0,
        provider_name: str = "",
        model_name: str = "",
        sample_chapters: Sequence[int] = (),
    ) -> dict[str, Any]:
        """Write a draft, replacing any existing draft for this book.

        A **confirmed** profile is never overwritten by a draft. Re-drafting over a user's
        answer would silently discard a decision they were asked to make, and the run that
        followed would be extracting under assumptions nobody agreed to.
        """
        existing = self.get(book_id)
        if existing and existing["status"] == "confirmed":
            return existing

        payload = {
            "book_id": book_id,
            "snapshot_id": snapshot_id,
            "status": "draft",
            "provider_name": provider_name,
            "model_name": model_name,
            "sample_chapters_json": json.dumps(list(sample_chapters), ensure_ascii=False),
            "now": datetime.now(timezone.utc),
        }
        for column, key in _JSON_COLUMNS.items():
            if column == "sample_chapters_json":
                continue
            payload[column] = json.dumps(draft.get(key, {}), ensure_ascii=False)

        columns = ["book_id", "snapshot_id", "status", "provider_name", "model_name", *_JSON_COLUMNS]
        if existing:
            assignments = ", ".join(f"{c} = :{c}" for c in columns if c != "book_id")
            self._session.execute(
                text(
                    f"UPDATE book_profiles SET {assignments}, updated_at = :now, "
                    "confirmed_at = NULL WHERE book_id = :book_id"
                ),
                payload,
            )
        else:
            placeholders = ", ".join(f":{c}" for c in columns)
            self._session.execute(
                text(
                    f"INSERT INTO book_profiles ({', '.join(columns)}, created_at, updated_at) "
                    f"VALUES ({placeholders}, :now, :now)"
                ),
                payload,
            )
        return self.get(book_id) or {}

    def confirm(self, book_id: int, axes: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        """Store the confirmed axes and mark the profile authoritative."""
        updated = self._session.execute(
            text(
                "UPDATE book_profiles SET axes_json = :axes, status = 'confirmed', "
                "confirmed_at = :now, updated_at = :now WHERE book_id = :book_id"
            ),
            {
                "axes": json.dumps(dict(axes), ensure_ascii=False),
                "now": datetime.now(timezone.utc),
                "book_id": book_id,
            },
        ).rowcount
        if not updated:
            raise LookupError(f"no profile drafted for book {book_id}")
        return self.get(book_id) or {}

    def clear(self, book_id: int) -> None:
        """Drop the profile so it can be drafted again.

        The way a user changes their mind after confirming. Whether the extraction cached
        under the old profile stays valid is decided by the prompt hash, not here — a
        different set of active deltas produces a different hash and is bought again.
        """
        self._session.execute(
            text("DELETE FROM book_profiles WHERE book_id = :book_id"), {"book_id": book_id}
        )
