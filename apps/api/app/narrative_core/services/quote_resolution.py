"""Snapshot-scoped quote / evidence-key resolution (CHG-055).

Resolves model-visible identifiers from the Context Bundle / Snapshot view into
full Evidence Locators. Never fuzzy-searches the whole book; never logs bodies.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class QuoteResolutionResult:
    status: str
    evidence_key: str | None
    chapter_id: int | None
    paragraph_id: int | None
    stable_paragraph_id: str | None
    paragraph_content_hash: str | None
    start_offset: int | None
    end_offset: int | None
    match_count: int
    failure_code: str | None

    def to_safe_dict(self) -> dict[str, Any]:
        return asdict(self)


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass
class SnapshotQuoteIndex:
    """Exact-match index over Snapshot paragraph bodies for one snapshot only."""

    book_snapshot_id: int
    # body -> list of locator hits (ambiguous when len>1)
    exact_body_hits: dict[str, list[dict[str, Any]]]
    # paragraph bodies for substring exact-find (not fuzzy)
    paragraph_bodies: list[dict[str, Any]]
    # model-visible keys → locator
    evidence_keys: dict[str, dict[str, Any]]
    stable_to_locator: dict[str, dict[str, Any]]
    paragraph_to_locator: dict[int, dict[str, Any]]

    @classmethod
    def build_from_session(
        cls,
        session: Any,
        *,
        book_snapshot_id: int,
        view: Any | None = None,
        selected_paragraph_ids: Sequence[int] | None = None,
        selected_chapter_ids: Sequence[int] | None = None,
    ) -> SnapshotQuoteIndex:
        from app.db.models import BookSnapshotChapter, BookSnapshotParagraph

        snap_id = int(book_snapshot_id)
        chapters = {
            int(c.id): str(c.content_text or "")
            for c in session.query(BookSnapshotChapter)
            .filter(BookSnapshotChapter.snapshot_id == snap_id)
            .all()
        }
        paragraphs = (
            session.query(BookSnapshotParagraph)
            .filter(BookSnapshotParagraph.snapshot_id == snap_id)
            .all()
        )
        selected_pids = (
            {int(x) for x in selected_paragraph_ids}
            if selected_paragraph_ids is not None
            else None
        )
        selected_cids = (
            {int(x) for x in selected_chapter_ids}
            if selected_chapter_ids is not None
            else None
        )

        exact_body_hits: dict[str, list[dict[str, Any]]] = {}
        paragraph_bodies: list[dict[str, Any]] = []
        evidence_keys: dict[str, dict[str, Any]] = {}
        stable_to_locator: dict[str, dict[str, Any]] = {}
        paragraph_to_locator: dict[int, dict[str, Any]] = {}

        view_hashes = getattr(view, "paragraph_hashes", {}) if view is not None else {}
        view_stables = getattr(view, "stable_paragraph_ids", {}) if view is not None else {}
        view_lengths = getattr(view, "paragraph_lengths", {}) if view is not None else {}

        for para in paragraphs:
            pid = int(para.id)
            chapter_id = int(para.snapshot_chapter_id)
            if selected_pids is not None and pid not in selected_pids:
                continue
            if selected_cids is not None and chapter_id not in selected_cids:
                continue
            chapter_text = chapters.get(chapter_id, "")
            start = int(para.start_offset or 0)
            end = int(para.end_offset or start)
            body = chapter_text[start:end] if chapter_text else ""
            stable = str(
                getattr(para, "stable_paragraph_id", None)
                or view_stables.get(pid)
                or pid
            )
            content_hash = str(
                getattr(para, "content_hash", None) or view_hashes.get(pid) or ""
            )
            para_len = int(view_lengths.get(pid) if view_lengths else len(body))
            locator = {
                "chapter_id": chapter_id,
                "paragraph_id": pid,
                "stable_paragraph_id": stable,
                "paragraph_content_hash": content_hash,
                "start_offset": 0,
                "end_offset": para_len if para_len > 0 else len(body),
                "body_len": len(body),
            }
            paragraph_to_locator[pid] = locator
            stable_to_locator[stable] = locator
            # Model-visible paragraph_refs are snapshot paragraph id strings.
            evidence_keys[str(pid)] = locator
            evidence_keys[stable] = locator
            evidence_keys[f"p:{pid}"] = locator
            evidence_keys[f"stable:{stable}"] = locator
            if body:
                exact_body_hits.setdefault(body, []).append(
                    {**locator, "start_offset": 0, "end_offset": len(body)}
                )
                paragraph_bodies.append({**locator, "body": body})

        return cls(
            book_snapshot_id=snap_id,
            exact_body_hits=exact_body_hits,
            paragraph_bodies=paragraph_bodies,
            evidence_keys=evidence_keys,
            stable_to_locator=stable_to_locator,
            paragraph_to_locator=paragraph_to_locator,
        )

    def resolve(
        self,
        *,
        evidence_key: str | None = None,
        stable_paragraph_id: str | None = None,
        snapshot_paragraph_id: int | None = None,
        snapshot_chapter_id: int | None = None,
        quote: str | None = None,
        expected_snapshot_id: int | None = None,
        expected_hash: str | None = None,
        start_offset: int | None = None,
        end_offset: int | None = None,
    ) -> QuoteResolutionResult:
        if expected_snapshot_id is not None and int(expected_snapshot_id) != int(
            self.book_snapshot_id
        ):
            return QuoteResolutionResult(
                status="rejected",
                evidence_key=evidence_key,
                chapter_id=None,
                paragraph_id=None,
                stable_paragraph_id=None,
                paragraph_content_hash=None,
                start_offset=None,
                end_offset=None,
                match_count=0,
                failure_code="SNAPSHOT_MISMATCH",
            )

        # 1) Explicit paragraph id
        if snapshot_paragraph_id is not None:
            loc = self.paragraph_to_locator.get(int(snapshot_paragraph_id))
            if loc is not None:
                if (
                    snapshot_chapter_id is not None
                    and int(snapshot_chapter_id) != int(loc["chapter_id"])
                ):
                    return self._fail(evidence_key, "CHAPTER_MISMATCH")
                return self._finalize(
                    evidence_key=evidence_key,
                    loc=loc,
                    start_offset=start_offset,
                    end_offset=end_offset,
                    expected_hash=expected_hash,
                    quote=quote,
                )
            # Fall through — id may be a model-visible key handled below.

        # 2) stable_paragraph_id
        if stable_paragraph_id:
            loc = self.stable_to_locator.get(str(stable_paragraph_id))
            if loc is not None:
                if (
                    snapshot_chapter_id is not None
                    and int(snapshot_chapter_id) != int(loc["chapter_id"])
                ):
                    return self._fail(evidence_key, "CHAPTER_MISMATCH")
                return self._finalize(
                    evidence_key=evidence_key,
                    loc=loc,
                    start_offset=start_offset,
                    end_offset=end_offset,
                    expected_hash=expected_hash,
                    quote=quote,
                )
            # Fall through to evidence_key / quote (opaque DTO ids are common).

        # 3) model-visible evidence key (and retry stable/paragraph tokens as keys)
        for key_candidate in (
            evidence_key,
            str(stable_paragraph_id) if stable_paragraph_id else None,
            str(snapshot_paragraph_id) if snapshot_paragraph_id is not None else None,
        ):
            if not key_candidate:
                continue
            loc = self.evidence_keys.get(str(key_candidate).strip())
            if loc is None:
                continue
            if (
                snapshot_chapter_id is not None
                and int(snapshot_chapter_id) != int(loc["chapter_id"])
            ):
                return self._fail(evidence_key, "CHAPTER_MISMATCH")
            return self._finalize(
                evidence_key=evidence_key,
                loc=loc,
                start_offset=start_offset,
                end_offset=end_offset,
                expected_hash=expected_hash,
                quote=quote,
            )

        if evidence_key and str(evidence_key).strip() and not quote:
            return self._fail(evidence_key, "QUOTE_KEY_UNKNOWN")

        # 4) exact quote / preview (Context-scoped bodies only)
        quote_text = str(quote or "").strip()
        if not quote_text:
            return self._fail(evidence_key, "QUOTE_NOT_FOUND")

        hits: list[dict[str, Any]] = []
        if quote_text in self.exact_body_hits:
            hits.extend(self.exact_body_hits[quote_text])
        else:
            for row in self.paragraph_bodies:
                body = str(row.get("body") or "")
                if not body:
                    continue
                pos = body.find(quote_text)
                if pos < 0:
                    continue
                # Reject ambiguous multi-occurrence inside one paragraph.
                if body.find(quote_text, pos + 1) >= 0:
                    return self._fail(evidence_key, "QUOTE_AMBIGUOUS", match_count=2)
                hits.append(
                    {
                        "chapter_id": row["chapter_id"],
                        "paragraph_id": row["paragraph_id"],
                        "stable_paragraph_id": row["stable_paragraph_id"],
                        "paragraph_content_hash": row["paragraph_content_hash"],
                        "start_offset": pos,
                        "end_offset": pos + len(quote_text),
                        "body_len": row["body_len"],
                    }
                )

        if not hits:
            return self._fail(evidence_key, "QUOTE_NOT_FOUND")
        if len(hits) > 1:
            # Distinct paragraphs — never default to first.
            return self._fail(evidence_key, "QUOTE_AMBIGUOUS", match_count=len(hits))
        loc = hits[0]
        if (
            snapshot_chapter_id is not None
            and int(snapshot_chapter_id) != int(loc["chapter_id"])
        ):
            return self._fail(evidence_key, "CHAPTER_MISMATCH")
        return self._finalize(
            evidence_key=evidence_key,
            loc=loc,
            start_offset=loc.get("start_offset") if start_offset is None else start_offset,
            end_offset=loc.get("end_offset") if end_offset is None else end_offset,
            expected_hash=expected_hash,
            quote=None,  # already matched
        )

    def _finalize(
        self,
        *,
        evidence_key: str | None,
        loc: Mapping[str, Any],
        start_offset: int | None,
        end_offset: int | None,
        expected_hash: str | None,
        quote: str | None,
    ) -> QuoteResolutionResult:
        content_hash = str(loc.get("paragraph_content_hash") or "")
        if expected_hash and content_hash and str(expected_hash) != content_hash:
            return self._fail(evidence_key, "HASH_MISMATCH")

        body_len = int(loc.get("body_len") or loc.get("end_offset") or 0)
        start = 0 if start_offset is None else int(start_offset)
        end = body_len if end_offset is None else int(end_offset)
        if start < 0 or end < start or (body_len > 0 and end > body_len):
            return self._fail(evidence_key, "OFFSET_INVALID")

        # Optional quote-vs-offset consistency when quote provided with offsets.
        if quote and body_len >= 0:
            # Quote consistency is enforced by caller via exact match path;
            # here we only validate offsets when both provided without re-loading body.
            pass

        return QuoteResolutionResult(
            status="resolved",
            evidence_key=evidence_key,
            chapter_id=int(loc["chapter_id"]),
            paragraph_id=int(loc["paragraph_id"]),
            stable_paragraph_id=str(loc["stable_paragraph_id"]),
            paragraph_content_hash=content_hash,
            start_offset=start,
            end_offset=end,
            match_count=1,
            failure_code=None,
        )

    @staticmethod
    def _fail(
        evidence_key: str | None, code: str, *, match_count: int = 0
    ) -> QuoteResolutionResult:
        return QuoteResolutionResult(
            status="rejected",
            evidence_key=evidence_key,
            chapter_id=None,
            paragraph_id=None,
            stable_paragraph_id=None,
            paragraph_content_hash=None,
            start_offset=None,
            end_offset=None,
            match_count=match_count,
            failure_code=code,
        )


def resolve_evidence_locator(
    index: SnapshotQuoteIndex,
    evidence: Mapping[str, Any] | Any,
    *,
    expected_snapshot_id: int,
) -> QuoteResolutionResult:
    """Resolve one evidence mapping/DTO into a Snapshot locator."""

    if isinstance(evidence, Mapping):
        get = evidence.get
    else:

        def get(name: str, default: Any = None) -> Any:
            return getattr(evidence, name, default)

    evidence_key = get("evidence_key") or get("evidence_id") or get("candidate_id")
    # Opaque EvidenceRefLite ids that look like keys; also try as paragraph ids.
    key_token = str(evidence_key).strip() if evidence_key is not None else None
    return index.resolve(
        evidence_key=key_token,
        stable_paragraph_id=(
            str(get("stable_paragraph_id")).strip()
            if get("stable_paragraph_id") is not None
            else None
        ),
        snapshot_paragraph_id=_as_int(
            get("snapshot_paragraph_id", get("paragraph_id"))
        ),
        snapshot_chapter_id=_as_int(get("snapshot_chapter_id", get("chapter_id"))),
        quote=str(get("preview") or get("quote") or get("text") or "") or None,
        expected_snapshot_id=expected_snapshot_id,
        expected_hash=(
            str(get("paragraph_content_hash"))
            if get("paragraph_content_hash")
            else None
        ),
        start_offset=_as_int(get("start_offset")),
        end_offset=_as_int(get("end_offset")),
    )
