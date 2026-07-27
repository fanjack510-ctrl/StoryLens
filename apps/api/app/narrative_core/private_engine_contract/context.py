"""WholeBook Context Pipeline contracts (Phase 2B-P).

Snapshot is the sole fact source. No FTS5 / vector DB / Neo4j / new tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

CONTEXT_PIPELINE_VERSION = "1.0.0"
CONTEXT_SCHEMA = "storylens.whole_book_context"
CONTEXT_SCHEMA_VERSION = "1.0.0"
CONTEXT_BUNDLE_REF_PREFIX = "ctx-bundle:"


def make_context_bundle_ref(bundle_hash: str) -> str:
    """Canonical registry key for a Context Bundle (single source of truth)."""

    digest = str(bundle_hash or "").strip()
    if not digest:
        raise ValueError("bundle_hash is required for context_bundle_ref")
    if digest.startswith(CONTEXT_BUNDLE_REF_PREFIX):
        return digest
    return f"{CONTEXT_BUNDLE_REF_PREFIX}{digest}"


def parse_context_bundle_hash(context_bundle_ref: str) -> str:
    """Extract content hash from a canonical context_bundle_ref."""

    ref = str(context_bundle_ref or "").strip()
    if not ref:
        raise ValueError("context_bundle_ref is required")
    if ref.startswith(CONTEXT_BUNDLE_REF_PREFIX):
        digest = ref[len(CONTEXT_BUNDLE_REF_PREFIX) :].strip()
    else:
        # Explicit reject of legacy Executor-only bundle:{run_id} inventing.
        if ref.startswith("bundle:"):
            raise ValueError("legacy bundle:{run_id} context_bundle_ref is not allowed")
        digest = ref
    if not digest:
        raise ValueError("context_bundle_ref has empty hash")
    return digest


class ContextUnitType(StrEnum):
    BOOK = "book"
    CHAPTER = "chapter"
    SCENE = "scene"
    PARAGRAPH_GROUP = "paragraph_group"
    EVIDENCE_WINDOW = "evidence_window"
    DERIVED_SUMMARY = "derived_summary"


class ContextLevel(IntEnum):
    """Generic hierarchical context strategy (not book-specific)."""

    LEVEL_0_BOOK_METADATA = 0  # book metadata + chapter TOC
    LEVEL_1_CHAPTER_REFS = 1  # chapter content refs + chapter summary refs
    LEVEL_2_SCENE_OR_GROUP = 2  # scene / paragraph group refs
    LEVEL_3_EVIDENCE_WINDOW = 3  # evidence window original-text refs


CONTEXT_LEVEL_DESCRIPTIONS: Mapping[ContextLevel, str] = {
    ContextLevel.LEVEL_0_BOOK_METADATA: "完整书籍元数据与章节目录",
    ContextLevel.LEVEL_1_CHAPTER_REFS: "章节级内容引用和章节摘要引用",
    ContextLevel.LEVEL_2_SCENE_OR_GROUP: "Scene / Paragraph Group 内容引用",
    ContextLevel.LEVEL_3_EVIDENCE_WINDOW: "Evidence Window 原文引用",
}

# Generic long-chapter grouping (not book-specific knobs).
GENERIC_LONG_CHAPTER_GROUPING = {
    "strategy": "paragraph_window",
    "max_paragraphs_per_group": 40,
    "overlap_paragraphs": 2,
    "book_specific_branches_forbidden": True,
}


@dataclass(frozen=True, slots=True)
class WholeBookContextUnit:
    unit_id: str
    unit_type: ContextUnitType
    book_snapshot_id: int
    snapshot_chapter_id: int | None
    snapshot_paragraph_ids: tuple[int, ...]
    chapter_order: int | None
    scene_id: int | None
    stable_paragraph_ids: tuple[str, ...]
    content_hash: str
    text_ref: str | None
    character_count: int
    token_estimate: int
    source_language: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    derived: bool = False
    book_id: int | None = None

    def __post_init__(self) -> None:
        if self.unit_type == ContextUnitType.DERIVED_SUMMARY and not self.derived:
            raise ValueError("derived_summary units must be marked derived=True")
        if self.derived and self.unit_type != ContextUnitType.DERIVED_SUMMARY:
            # derived flag only for derived_summary type in this freeze
            raise ValueError("derived=True is reserved for derived_summary units")
        if self.character_count < 0 or self.token_estimate < 0:
            raise ValueError("counts must be >= 0")
        # text_ref is on-demand; must not embed unbounded full text in metadata.
        if "full_text" in self.metadata or "novel_body" in self.metadata:
            raise ValueError("context unit metadata must not embed full text")


@dataclass(frozen=True, slots=True)
class ContextBundle:
    book_id: int
    book_snapshot_id: int
    snapshot_content_hash: str
    chapter_hashes: tuple[str, ...]
    paragraph_hashes: tuple[str, ...]
    context_schema: str
    context_schema_version: str
    pipeline_version: str
    configuration_fingerprint: str
    units: tuple[WholeBookContextUnit, ...] = ()
    bundle_hash: str = ""

    def __post_init__(self) -> None:
        if self.book_id <= 0 or self.book_snapshot_id <= 0:
            raise ValueError("book_id and book_snapshot_id must be positive")
        if not self.snapshot_content_hash.strip():
            raise ValueError("snapshot_content_hash is required")
        for unit in self.units:
            if unit.book_snapshot_id != self.book_snapshot_id:
                raise ValueError("context units must not mix snapshots")
            if unit.book_id is not None and unit.book_id != self.book_id:
                raise ValueError("context units must not cross books")


CONTEXT_PIPELINE_METHODS: tuple[str, ...] = (
    "prepare_snapshot",
    "normalize_chapters",
    "build_chapter_units",
    "build_scene_units",
    "build_paragraph_units",
    "build_context_index",
    "build_module_context",
    "build_context_bundle",
    "validate_context_bundle",
)


@runtime_checkable
class WholeBookContextPipeline(Protocol):
    def prepare_snapshot(self, book_id: int, book_snapshot_id: int) -> Mapping[str, Any]: ...

    def normalize_chapters(self, snapshot_ref: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]: ...

    def build_chapter_units(
        self, chapters: Sequence[Mapping[str, Any]]
    ) -> Sequence[WholeBookContextUnit]: ...

    def build_scene_units(
        self, chapters: Sequence[Mapping[str, Any]]
    ) -> Sequence[WholeBookContextUnit]: ...

    def build_paragraph_units(
        self, chapters: Sequence[Mapping[str, Any]]
    ) -> Sequence[WholeBookContextUnit]: ...

    def build_context_index(self, units: Sequence[WholeBookContextUnit]) -> Mapping[str, Any]: ...

    def build_module_context(
        self,
        *,
        module_key: str,
        units: Sequence[WholeBookContextUnit],
        level: ContextLevel,
    ) -> Sequence[WholeBookContextUnit]: ...

    def build_context_bundle(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        snapshot_content_hash: str,
        units: Sequence[WholeBookContextUnit],
        configuration_fingerprint: str,
    ) -> ContextBundle: ...

    def validate_context_bundle(self, bundle: ContextBundle) -> None: ...


def sort_context_units_deterministically(
    units: Sequence[WholeBookContextUnit],
) -> tuple[WholeBookContextUnit, ...]:
    return tuple(
        sorted(
            units,
            key=lambda u: (
                u.chapter_order if u.chapter_order is not None else -1,
                u.unit_type.value,
                u.unit_id,
            ),
        )
    )


@dataclass
class FakeContextPipeline:
    """Deterministic Fake context builder — no DB / FTS5 / vector / Neo4j."""

    pipeline_version: str = CONTEXT_PIPELINE_VERSION

    def prepare_snapshot(self, book_id: int, book_snapshot_id: int) -> Mapping[str, Any]:
        return {
            "book_id": book_id,
            "book_snapshot_id": book_snapshot_id,
            "fact_source": "snapshot",
            "fts5": False,
            "vector_db": False,
            "neo4j": False,
            "new_tables": False,
        }

    def normalize_chapters(self, snapshot_ref: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
        chapters = list(snapshot_ref.get("chapters", ()))
        return tuple(sorted(chapters, key=lambda c: int(c.get("chapter_order", 0))))

    def build_chapter_units(
        self, chapters: Sequence[Mapping[str, Any]]
    ) -> Sequence[WholeBookContextUnit]:
        units: list[WholeBookContextUnit] = []
        for chapter in chapters:
            units.append(
                WholeBookContextUnit(
                    unit_id=f"chapter:{chapter.get('snapshot_chapter_id')}",
                    unit_type=ContextUnitType.CHAPTER,
                    book_snapshot_id=int(chapter["book_snapshot_id"]),
                    snapshot_chapter_id=int(chapter["snapshot_chapter_id"]),
                    snapshot_paragraph_ids=tuple(chapter.get("snapshot_paragraph_ids", ())),
                    chapter_order=int(chapter.get("chapter_order", 0)),
                    scene_id=None,
                    stable_paragraph_ids=tuple(chapter.get("stable_paragraph_ids", ())),
                    content_hash=str(chapter.get("content_hash", "fake-chapter-hash")),
                    text_ref=str(chapter.get("text_ref", f"snapshot://chapter/{chapter.get('snapshot_chapter_id')}")),
                    character_count=int(chapter.get("character_count", 0)),
                    token_estimate=int(chapter.get("token_estimate", 0)),
                    source_language=str(chapter.get("source_language", "unknown")),
                    book_id=int(chapter["book_id"]) if "book_id" in chapter else None,
                )
            )
        return sort_context_units_deterministically(units)

    def build_scene_units(
        self, chapters: Sequence[Mapping[str, Any]]
    ) -> Sequence[WholeBookContextUnit]:
        return ()

    def build_paragraph_units(
        self, chapters: Sequence[Mapping[str, Any]]
    ) -> Sequence[WholeBookContextUnit]:
        # Generic long-chapter grouping strategy (fixture only).
        _ = GENERIC_LONG_CHAPTER_GROUPING
        return ()

    def build_context_index(self, units: Sequence[WholeBookContextUnit]) -> Mapping[str, Any]:
        ordered = sort_context_units_deterministically(units)
        return {"unit_ids": tuple(u.unit_id for u in ordered), "count": len(ordered)}

    def build_module_context(
        self,
        *,
        module_key: str,
        units: Sequence[WholeBookContextUnit],
        level: ContextLevel,
    ) -> Sequence[WholeBookContextUnit]:
        _ = module_key
        if level == ContextLevel.LEVEL_0_BOOK_METADATA:
            return tuple(u for u in units if u.unit_type in (ContextUnitType.BOOK, ContextUnitType.CHAPTER))
        if level == ContextLevel.LEVEL_3_EVIDENCE_WINDOW:
            return tuple(u for u in units if u.unit_type == ContextUnitType.EVIDENCE_WINDOW)
        return sort_context_units_deterministically(units)

    def build_context_bundle(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        snapshot_content_hash: str,
        units: Sequence[WholeBookContextUnit],
        configuration_fingerprint: str,
    ) -> ContextBundle:
        ordered = sort_context_units_deterministically(units)
        chapter_hashes = tuple(
            u.content_hash for u in ordered if u.unit_type == ContextUnitType.CHAPTER
        )
        return ContextBundle(
            book_id=book_id,
            book_snapshot_id=book_snapshot_id,
            snapshot_content_hash=snapshot_content_hash,
            chapter_hashes=chapter_hashes,
            paragraph_hashes=(),
            context_schema=CONTEXT_SCHEMA,
            context_schema_version=CONTEXT_SCHEMA_VERSION,
            pipeline_version=self.pipeline_version,
            configuration_fingerprint=configuration_fingerprint,
            units=ordered,
            bundle_hash=f"fake-bundle:{snapshot_content_hash}:{len(ordered)}",
        )

    def validate_context_bundle(self, bundle: ContextBundle) -> None:
        if bundle.context_schema != CONTEXT_SCHEMA:
            raise ValueError("invalid context schema")
        if not bundle.snapshot_content_hash:
            raise ValueError("snapshot hash required")
        for unit in bundle.units:
            if unit.book_snapshot_id != bundle.book_snapshot_id:
                raise ValueError("cross-snapshot mix forbidden")


def fake_context_bundle(
    *,
    book_id: int = 1,
    book_snapshot_id: int = 1,
) -> ContextBundle:
    pipeline = FakeContextPipeline()
    chapters = (
        {
            "book_id": book_id,
            "book_snapshot_id": book_snapshot_id,
            "snapshot_chapter_id": 1,
            "chapter_order": 1,
            "content_hash": "fake-ch-1",
            "character_count": 12,
            "token_estimate": 4,
            "source_language": "zh",
            "snapshot_paragraph_ids": (1, 2),
            "stable_paragraph_ids": ("p1", "p2"),
        },
    )
    units = pipeline.build_chapter_units(chapters)
    return pipeline.build_context_bundle(
        book_id=book_id,
        book_snapshot_id=book_snapshot_id,
        snapshot_content_hash="fake-snapshot-hash",
        units=units,
        configuration_fingerprint="fake-config-fp",
    )
