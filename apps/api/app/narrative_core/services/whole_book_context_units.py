"""Context units, TextRef, and on-demand Snapshot text resolution (Agent Q / CHG-038).

DTOs never embed full novel body by default. Resolve only on explicit request.
Temporary caches are not a fact source. No FTS5 / vector / Neo4j / new tables.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Sequence

from sqlalchemy.orm import Session

from app.db.models import BookSnapshot, BookSnapshotChapter, BookSnapshotParagraph
from app.narrative_core.enums import SnapshotStatus
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.hash_canon import calculate_text_hash
from app.narrative_core.private_engine_contract.context import (
    GENERIC_LONG_CHAPTER_GROUPING,
    ContextUnitType,
    WholeBookContextUnit,
    sort_context_units_deterministically,
)
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl

logger = logging.getLogger(__name__)

# Rough token estimate: ~4 characters per token (language-agnostic heuristic).
_CHARS_PER_TOKEN = 4
_DEFAULT_TEXT_CACHE_MAX_ENTRIES = 64
_DEFAULT_TEXT_CACHE_MAX_CHARS = 2_000_000


class TextRefKind(StrEnum):
    CHAPTER = "chapter"
    PARAGRAPH_GROUP = "paragraph_group"
    EVIDENCE_WINDOW = "evidence_window"


@dataclass(frozen=True, slots=True)
class SnapshotTextRef:
    """On-demand text locator — never carries full body text."""

    kind: TextRefKind
    book_id: int
    book_snapshot_id: int
    snapshot_chapter_id: int
    snapshot_paragraph_ids: tuple[int, ...]
    content_hash: str
    start_offset: int | None = None
    end_offset: int | None = None

    def __post_init__(self) -> None:
        if self.book_id <= 0 or self.book_snapshot_id <= 0:
            raise ValueError("book_id and book_snapshot_id must be positive")
        if self.snapshot_chapter_id <= 0:
            raise ValueError("snapshot_chapter_id must be positive")
        if not self.snapshot_paragraph_ids:
            raise ValueError("snapshot_paragraph_ids required")
        if not self.content_hash.strip():
            raise ValueError("content_hash required")
        if self.kind == TextRefKind.EVIDENCE_WINDOW:
            if self.start_offset is None or self.end_offset is None:
                raise ValueError("evidence_window requires offsets")
            if self.start_offset < 0 or self.end_offset < self.start_offset:
                raise ValueError("invalid evidence_window offsets")
            if len(self.snapshot_paragraph_ids) != 1:
                raise ValueError("evidence_window must reference exactly one paragraph")

    def to_uri(self) -> str:
        paras = ",".join(str(p) for p in self.snapshot_paragraph_ids)
        base = (
            f"snapshot://{self.kind.value}/book/{self.book_id}"
            f"/snapshot/{self.book_snapshot_id}"
            f"/chapter/{self.snapshot_chapter_id}"
            f"/paragraphs/{paras}"
            f"/hash/{self.content_hash}"
        )
        if self.kind == TextRefKind.EVIDENCE_WINDOW:
            return f"{base}/off/{self.start_offset}-{self.end_offset}"
        return base

    @staticmethod
    def from_uri(uri: str) -> SnapshotTextRef:
        # snapshot://{kind}/book/{bid}/snapshot/{sid}/chapter/{cid}/paragraphs/{pids}/hash/{h}[/off/a-b]
        if not uri.startswith("snapshot://"):
            raise ValueError("unsupported text_ref uri")
        body = uri[len("snapshot://") :]
        parts = body.split("/")
        if len(parts) < 10 or parts[1] != "book" or parts[3] != "snapshot":
            raise ValueError("malformed text_ref uri")
        kind = TextRefKind(parts[0])
        book_id = int(parts[2])
        snapshot_id = int(parts[4])
        if parts[5] != "chapter" or parts[7] != "paragraphs" or parts[9] != "hash":
            raise ValueError("malformed text_ref uri")
        chapter_id = int(parts[6])
        para_ids = tuple(int(x) for x in parts[8].split(",") if x)
        content_hash = parts[10]
        start = end = None
        if kind == TextRefKind.EVIDENCE_WINDOW:
            if len(parts) < 13 or parts[11] != "off":
                raise ValueError("evidence_window uri missing offsets")
            a, b = parts[12].split("-", 1)
            start, end = int(a), int(b)
        return SnapshotTextRef(
            kind=kind,
            book_id=book_id,
            book_snapshot_id=snapshot_id,
            snapshot_chapter_id=chapter_id,
            snapshot_paragraph_ids=para_ids,
            content_hash=content_hash,
            start_offset=start,
            end_offset=end,
        )


@dataclass
class _TextCacheEntry:
    text: str
    content_hash: str


class SnapshotTextResolver:
    """Resolve SnapshotTextRef to body text with hash / book / snapshot checks.

    Temporary in-memory cache only. Never logs full text. Never writes Artifact.
    """

    def __init__(
        self,
        session: Session,
        *,
        snapshot_service: BookSnapshotServiceImpl | None = None,
        max_entries: int = _DEFAULT_TEXT_CACHE_MAX_ENTRIES,
        max_chars: int = _DEFAULT_TEXT_CACHE_MAX_CHARS,
    ) -> None:
        self._session = session
        self._snapshots = snapshot_service or BookSnapshotServiceImpl(session)
        self._max_entries = max(1, max_entries)
        self._max_chars = max(1, max_chars)
        self._cache: dict[str, _TextCacheEntry] = {}
        self._cache_chars = 0

    def clear_cache(self) -> None:
        self._cache.clear()
        self._cache_chars = 0

    def resolve(self, text_ref: SnapshotTextRef | str) -> str:
        ref = text_ref if isinstance(text_ref, SnapshotTextRef) else SnapshotTextRef.from_uri(text_ref)
        cache_key = ref.to_uri()
        hit = self._cache.get(cache_key)
        if hit is not None and hit.content_hash == ref.content_hash:
            return hit.text

        snapshot = self._require_completed_snapshot(ref.book_id, ref.book_snapshot_id)
        chapter = self._session.get(BookSnapshotChapter, ref.snapshot_chapter_id)
        if chapter is None or chapter.snapshot_id != snapshot.id:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.SNAPSHOT_INTEGRITY_FAILED,
                "text_ref chapter not in snapshot",
            )

        paragraphs = self._load_paragraphs(ref, snapshot.id, chapter.id)
        if ref.kind == TextRefKind.CHAPTER:
            text = chapter.content_text or ""
            if calculate_text_hash(text) != chapter.content_hash:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.EVIDENCE_HASH_MISMATCH,
                    "chapter content hash mismatch",
                )
            if ref.content_hash != chapter.content_hash:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.EVIDENCE_HASH_MISMATCH,
                    "text_ref chapter hash mismatch",
                )
        elif ref.kind == TextRefKind.PARAGRAPH_GROUP:
            parts: list[str] = []
            for para in paragraphs:
                parts.append(self._snapshots.get_snapshot_paragraph_text(para.id))
            text = "\n".join(parts)
            if calculate_text_hash(text) != ref.content_hash:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.EVIDENCE_HASH_MISMATCH,
                    "paragraph_group hash mismatch",
                )
        else:
            para = paragraphs[0]
            full = self._snapshots.get_snapshot_paragraph_text(para.id)
            assert ref.start_offset is not None and ref.end_offset is not None
            if ref.end_offset > len(full):
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.EVIDENCE_OFFSET_OUT_OF_RANGE,
                    "evidence_window offset out of range",
                )
            text = full[ref.start_offset : ref.end_offset]
            if calculate_text_hash(text) != ref.content_hash:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.EVIDENCE_HASH_MISMATCH,
                    "evidence_window hash mismatch",
                )

        self._store_cache(cache_key, text, ref.content_hash)
        logger.debug(
            "resolved text_ref kind=%s snapshot=%s chapter=%s chars=%s",
            ref.kind.value,
            ref.book_snapshot_id,
            ref.snapshot_chapter_id,
            len(text),
        )
        return text

    def _require_completed_snapshot(self, book_id: int, snapshot_id: int) -> BookSnapshot:
        self._snapshots.validate_snapshot_for_book(snapshot_id, book_id)
        snapshot = self._snapshots.get_completed_snapshot(snapshot_id)
        return snapshot

    def _load_paragraphs(
        self,
        ref: SnapshotTextRef,
        snapshot_id: int,
        chapter_id: int,
    ) -> list[BookSnapshotParagraph]:
        rows: list[BookSnapshotParagraph] = []
        for pid in ref.snapshot_paragraph_ids:
            para = self._session.get(BookSnapshotParagraph, pid)
            if para is None:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.SNAPSHOT_NOT_FOUND,
                    f"snapshot paragraph not found: {pid}",
                )
            if para.snapshot_id != snapshot_id:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.SNAPSHOT_BOOK_MISMATCH,
                    "paragraph crosses snapshot",
                )
            if para.snapshot_chapter_id != chapter_id:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.EVIDENCE_SNAPSHOT_PARAGRAPH_MISMATCH,
                    "paragraph crosses chapter",
                )
            rows.append(para)
        return rows

    def _store_cache(self, key: str, text: str, content_hash: str) -> None:
        size = len(text)
        if size > self._max_chars:
            return
        while self._cache and (
            len(self._cache) >= self._max_entries or self._cache_chars + size > self._max_chars
        ):
            old_key = next(iter(self._cache))
            old = self._cache.pop(old_key)
            self._cache_chars -= len(old.text)
        self._cache[key] = _TextCacheEntry(text=text, content_hash=content_hash)
        self._cache_chars += size


def estimate_tokens(character_count: int) -> int:
    if character_count <= 0:
        return 0
    return max(1, (character_count + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)


def make_unit_id(
    unit_type: ContextUnitType | str,
    book_snapshot_id: int,
    *,
    chapter_order: int | None = None,
    scene_id: int | None = None,
    paragraph_ids: Sequence[int] = (),
    extra: str = "",
) -> str:
    """Deterministic unit_id from structural keys (not book title / author)."""
    payload = "|".join(
        (
            str(unit_type.value if isinstance(unit_type, ContextUnitType) else unit_type),
            str(book_snapshot_id),
            str(chapter_order if chapter_order is not None else ""),
            str(scene_id if scene_id is not None else ""),
            ",".join(str(p) for p in paragraph_ids),
            extra,
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    prefix = unit_type.value if isinstance(unit_type, ContextUnitType) else str(unit_type)
    return f"{prefix}:{book_snapshot_id}:{digest}"


def content_hash_for_parts(parts: Sequence[str]) -> str:
    return calculate_text_hash("\n".join(parts))


@dataclass(frozen=True, slots=True)
class ChapterNormalizeRecord:
    book_id: int
    book_snapshot_id: int
    snapshot_chapter_id: int
    chapter_order: int
    title: str
    content_hash: str
    character_count: int
    source_language: str
    snapshot_paragraph_ids: tuple[int, ...]
    stable_paragraph_ids: tuple[str, ...]
    paragraph_hashes: tuple[str, ...]
    paragraph_orders: tuple[int, ...]
    # Offsets relative to chapter.content_text — for grouping only, not full body.
    paragraph_offsets: tuple[tuple[int, int], ...] = ()


class ContextUnitBuilder:
    """Generic unit builder — no book-title / author / character-name branches."""

    def __init__(
        self,
        *,
        source_language: str = "unknown",
        grouping: Mapping[str, Any] | None = None,
    ) -> None:
        self._source_language = source_language
        self._grouping = dict(grouping or GENERIC_LONG_CHAPTER_GROUPING)
        self._max_per_group = int(self._grouping.get("max_paragraphs_per_group", 40))
        self._overlap = int(self._grouping.get("overlap_paragraphs", 2))
        if self._max_per_group < 1:
            raise ValueError("max_paragraphs_per_group must be >= 1")
        if self._overlap < 0 or self._overlap >= self._max_per_group:
            raise ValueError("overlap_paragraphs must be in [0, max_paragraphs_per_group)")

    def build_book_unit(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        snapshot_content_hash: str,
        chapter_count: int,
        character_count: int,
        metadata: Mapping[str, Any] | None = None,
    ) -> WholeBookContextUnit:
        meta = dict(metadata or {})
        meta.setdefault("chapter_count", chapter_count)
        meta.setdefault("toc", True)
        return WholeBookContextUnit(
            unit_id=make_unit_id(ContextUnitType.BOOK, book_snapshot_id, extra=snapshot_content_hash),
            unit_type=ContextUnitType.BOOK,
            book_snapshot_id=book_snapshot_id,
            snapshot_chapter_id=None,
            snapshot_paragraph_ids=(),
            chapter_order=None,
            scene_id=None,
            stable_paragraph_ids=(),
            content_hash=snapshot_content_hash,
            text_ref=None,
            character_count=character_count,
            token_estimate=estimate_tokens(character_count),
            source_language=self._source_language,
            metadata=meta,
            book_id=book_id,
        )

    def build_chapter_unit(self, chapter: ChapterNormalizeRecord) -> WholeBookContextUnit:
        uri = None
        if chapter.snapshot_paragraph_ids:
            uri = SnapshotTextRef(
                kind=TextRefKind.CHAPTER,
                book_id=chapter.book_id,
                book_snapshot_id=chapter.book_snapshot_id,
                snapshot_chapter_id=chapter.snapshot_chapter_id,
                snapshot_paragraph_ids=chapter.snapshot_paragraph_ids,
                content_hash=chapter.content_hash,
            ).to_uri()
        return WholeBookContextUnit(
            unit_id=make_unit_id(
                ContextUnitType.CHAPTER,
                chapter.book_snapshot_id,
                chapter_order=chapter.chapter_order,
                paragraph_ids=chapter.snapshot_paragraph_ids,
            ),
            unit_type=ContextUnitType.CHAPTER,
            book_snapshot_id=chapter.book_snapshot_id,
            snapshot_chapter_id=chapter.snapshot_chapter_id,
            snapshot_paragraph_ids=chapter.snapshot_paragraph_ids,
            chapter_order=chapter.chapter_order,
            scene_id=None,
            stable_paragraph_ids=chapter.stable_paragraph_ids,
            content_hash=chapter.content_hash,
            text_ref=uri,
            character_count=chapter.character_count,
            token_estimate=estimate_tokens(chapter.character_count),
            source_language=chapter.source_language or self._source_language,
            metadata={"title_len": len(chapter.title or "")},
            book_id=chapter.book_id,
        )

    def build_scene_unit(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        snapshot_chapter_id: int,
        chapter_order: int,
        scene_id: int,
        snapshot_paragraph_ids: Sequence[int],
        stable_paragraph_ids: Sequence[str],
        paragraph_texts_or_hashes: Sequence[str],
        hashes_only: bool = True,
        source_language: str | None = None,
        stale: bool = False,
    ) -> WholeBookContextUnit:
        para_ids = tuple(snapshot_paragraph_ids)
        if hashes_only:
            content_hash = content_hash_for_parts(tuple(paragraph_texts_or_hashes))
            char_count = 0
        else:
            content_hash = content_hash_for_parts(tuple(paragraph_texts_or_hashes))
            char_count = sum(len(t) for t in paragraph_texts_or_hashes) + max(
                0, len(paragraph_texts_or_hashes) - 1
            )
        text_ref = None
        if para_ids:
            text_ref = SnapshotTextRef(
                kind=TextRefKind.PARAGRAPH_GROUP,
                book_id=book_id,
                book_snapshot_id=book_snapshot_id,
                snapshot_chapter_id=snapshot_chapter_id,
                snapshot_paragraph_ids=para_ids,
                content_hash=content_hash,
            ).to_uri()
        return WholeBookContextUnit(
            unit_id=make_unit_id(
                ContextUnitType.SCENE,
                book_snapshot_id,
                chapter_order=chapter_order,
                scene_id=scene_id,
                paragraph_ids=para_ids,
            ),
            unit_type=ContextUnitType.SCENE,
            book_snapshot_id=book_snapshot_id,
            snapshot_chapter_id=snapshot_chapter_id,
            snapshot_paragraph_ids=para_ids,
            chapter_order=chapter_order,
            scene_id=scene_id,
            stable_paragraph_ids=tuple(stable_paragraph_ids),
            content_hash=content_hash,
            text_ref=text_ref,
            character_count=char_count,
            token_estimate=estimate_tokens(char_count),
            source_language=source_language or self._source_language,
            metadata={"stale": stale, "aux_asset": True},
            book_id=book_id,
        )

    def build_paragraph_group_units(
        self,
        chapter: ChapterNormalizeRecord,
        *,
        paragraph_texts: Sequence[str] | None = None,
    ) -> tuple[WholeBookContextUnit, ...]:
        """Generic long-chapter grouping from config — not book-specific thresholds.

        When ``paragraph_texts`` is provided (formal Snapshot path), ``content_hash``
        matches ``SnapshotTextResolver`` for PARAGRAPH_GROUP
        (``hash(\"\\n\".join(texts))``). Synth/index-only callers may omit texts.
        """
        ids = chapter.snapshot_paragraph_ids
        if not ids:
            return ()
        if paragraph_texts is not None and len(paragraph_texts) != len(ids):
            raise ValueError("paragraph_texts length must match snapshot_paragraph_ids")
        hashes = chapter.paragraph_hashes
        stables = chapter.stable_paragraph_ids
        units: list[WholeBookContextUnit] = []
        step = max(1, self._max_per_group - self._overlap)
        start = 0
        group_index = 0
        while start < len(ids):
            end = min(len(ids), start + self._max_per_group)
            slice_ids = ids[start:end]
            slice_hashes = hashes[start:end]
            slice_stables = stables[start:end]
            if paragraph_texts is not None:
                slice_texts = tuple(paragraph_texts[start:end])
                content_hash = content_hash_for_parts(slice_texts)
                char_count = sum(len(t) for t in slice_texts) + max(0, len(slice_texts) - 1)
            else:
                # Structural fingerprint for synth/index fixtures (no TextRef resolve).
                content_hash = content_hash_for_parts(slice_hashes)
                if chapter.paragraph_offsets and end <= len(chapter.paragraph_offsets):
                    char_count = sum(
                        max(0, o[1] - o[0]) for o in chapter.paragraph_offsets[start:end]
                    )
                else:
                    char_count = 0
            text_ref = SnapshotTextRef(
                kind=TextRefKind.PARAGRAPH_GROUP,
                book_id=chapter.book_id,
                book_snapshot_id=chapter.book_snapshot_id,
                snapshot_chapter_id=chapter.snapshot_chapter_id,
                snapshot_paragraph_ids=slice_ids,
                content_hash=content_hash,
            ).to_uri()
            units.append(
                WholeBookContextUnit(
                    unit_id=make_unit_id(
                        ContextUnitType.PARAGRAPH_GROUP,
                        chapter.book_snapshot_id,
                        chapter_order=chapter.chapter_order,
                        paragraph_ids=slice_ids,
                        extra=f"g{group_index}",
                    ),
                    unit_type=ContextUnitType.PARAGRAPH_GROUP,
                    book_snapshot_id=chapter.book_snapshot_id,
                    snapshot_chapter_id=chapter.snapshot_chapter_id,
                    snapshot_paragraph_ids=slice_ids,
                    chapter_order=chapter.chapter_order,
                    scene_id=None,
                    stable_paragraph_ids=slice_stables,
                    content_hash=content_hash,
                    text_ref=text_ref,
                    character_count=char_count,
                    token_estimate=estimate_tokens(char_count),
                    source_language=chapter.source_language or self._source_language,
                    metadata={
                        "group_index": group_index,
                        "group_start": start,
                        "group_end": end,
                        "grouping": "paragraph_window",
                    },
                    book_id=chapter.book_id,
                )
            )
            group_index += 1
            if end >= len(ids):
                break
            start += step
        return sort_context_units_deterministically(units)

    def build_evidence_window_unit(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        snapshot_chapter_id: int,
        chapter_order: int,
        snapshot_paragraph_id: int,
        stable_paragraph_id: str,
        paragraph_content_hash: str,
        start_offset: int,
        end_offset: int,
        excerpt_hash: str,
        character_count: int,
        source_language: str | None = None,
    ) -> WholeBookContextUnit:
        text_ref = SnapshotTextRef(
            kind=TextRefKind.EVIDENCE_WINDOW,
            book_id=book_id,
            book_snapshot_id=book_snapshot_id,
            snapshot_chapter_id=snapshot_chapter_id,
            snapshot_paragraph_ids=(snapshot_paragraph_id,),
            content_hash=excerpt_hash,
            start_offset=start_offset,
            end_offset=end_offset,
        )
        return WholeBookContextUnit(
            unit_id=make_unit_id(
                ContextUnitType.EVIDENCE_WINDOW,
                book_snapshot_id,
                chapter_order=chapter_order,
                paragraph_ids=(snapshot_paragraph_id,),
                extra=f"{start_offset}-{end_offset}",
            ),
            unit_type=ContextUnitType.EVIDENCE_WINDOW,
            book_snapshot_id=book_snapshot_id,
            snapshot_chapter_id=snapshot_chapter_id,
            snapshot_paragraph_ids=(snapshot_paragraph_id,),
            chapter_order=chapter_order,
            scene_id=None,
            stable_paragraph_ids=(stable_paragraph_id,),
            content_hash=excerpt_hash,
            text_ref=text_ref.to_uri(),
            character_count=character_count,
            token_estimate=estimate_tokens(character_count),
            source_language=source_language or self._source_language,
            metadata={
                "paragraph_content_hash": paragraph_content_hash,
                "start_offset": start_offset,
                "end_offset": end_offset,
            },
            book_id=book_id,
        )

    def build_derived_summary_ref(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        summary_ref: str,
        content_hash: str,
        snapshot_chapter_id: int | None = None,
        chapter_order: int | None = None,
    ) -> WholeBookContextUnit:
        """Placeholder derived_summary unit — never final original evidence."""
        return WholeBookContextUnit(
            unit_id=make_unit_id(
                ContextUnitType.DERIVED_SUMMARY,
                book_snapshot_id,
                chapter_order=chapter_order,
                extra=summary_ref,
            ),
            unit_type=ContextUnitType.DERIVED_SUMMARY,
            book_snapshot_id=book_snapshot_id,
            snapshot_chapter_id=snapshot_chapter_id,
            snapshot_paragraph_ids=(),
            chapter_order=chapter_order,
            scene_id=None,
            stable_paragraph_ids=(),
            content_hash=content_hash,
            text_ref=summary_ref,
            character_count=0,
            token_estimate=0,
            source_language=self._source_language,
            metadata={"placeholder": True},
            derived=True,
            book_id=book_id,
        )


def chapter_record_from_orm(
    *,
    book_id: int,
    snapshot: BookSnapshot,
    chapter: BookSnapshotChapter,
    source_language: str = "unknown",
) -> ChapterNormalizeRecord:
    paragraphs = sorted(chapter.paragraphs, key=lambda p: p.paragraph_order)
    return ChapterNormalizeRecord(
        book_id=book_id,
        book_snapshot_id=snapshot.id,
        snapshot_chapter_id=chapter.id,
        chapter_order=int(chapter.chapter_order),
        title=str(chapter.title or ""),
        content_hash=str(chapter.content_hash),
        character_count=len(chapter.content_text or ""),
        source_language=source_language,
        snapshot_paragraph_ids=tuple(p.id for p in paragraphs),
        stable_paragraph_ids=tuple(str(p.stable_paragraph_id) for p in paragraphs),
        paragraph_hashes=tuple(str(p.content_hash) for p in paragraphs),
        paragraph_orders=tuple(int(p.paragraph_order) for p in paragraphs),
        paragraph_offsets=tuple((int(p.start_offset), int(p.end_offset)) for p in paragraphs),
    )


def assert_snapshot_completed(snapshot: BookSnapshot) -> None:
    if snapshot.snapshot_status != SnapshotStatus.COMPLETED:
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.SNAPSHOT_NOT_COMPLETED,
            f"snapshot {snapshot.id} status={snapshot.snapshot_status}",
        )


@dataclass
class UnitBuildConfig:
    source_language: str = "unknown"
    grouping: Mapping[str, Any] = field(
        default_factory=lambda: dict(GENERIC_LONG_CHAPTER_GROUPING)
    )

    @classmethod
    def from_grouping_policy(cls, policy: Any, *, source_language: str = "unknown") -> UnitBuildConfig:
        """Build from ParagraphGroupingPolicy when available (Integration wiring)."""

        if hasattr(policy, "to_grouping_dict"):
            return cls(source_language=source_language, grouping=policy.to_grouping_dict())
        if isinstance(policy, Mapping):
            return cls(source_language=source_language, grouping=dict(policy))
        return cls(source_language=source_language)
