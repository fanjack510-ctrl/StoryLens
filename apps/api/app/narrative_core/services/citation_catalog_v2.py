"""Public Citation Catalog V2 support (CHG-058).

Prefers ``storylens_private_engine.citation`` when importable; otherwise uses a
public-local builder matching ``CIT-{8hex}-{NNNN}`` so directed tests can run.
MUST NOT call quote_resolution / SnapshotQuoteIndex.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

CITATION_ID_PREFIX = "CIT"
BUNDLE_HASH_PREFIX_LEN = 8
ORDINAL_WIDTH = 4
MAX_CITATION_UNIT_CHARS = 2000
CATALOG_VERSION = "v2"
EVIDENCE_CONTRACT_VERSION = "v2"
CITATION_ID_FORMAT_VERSION = "v2"

CITATION_ID_UNKNOWN = "CITATION_ID_UNKNOWN"
CITATION_ID_STALE_BUNDLE = "CITATION_ID_STALE_BUNDLE"
CITATION_CATALOG_MISMATCH = "CITATION_CATALOG_MISMATCH"
CITATION_SNAPSHOT_MISMATCH = "CITATION_SNAPSHOT_MISMATCH"
CITATION_LOCATOR_INVALID = "CITATION_LOCATOR_INVALID"
CITATION_HASH_MISMATCH = "CITATION_HASH_MISMATCH"
CITATION_OFFSET_INVALID = "CITATION_OFFSET_INVALID"

SOURCE_UNIT_TYPE_PARAGRAPH = "paragraph"
SOURCE_UNIT_TYPE_PARAGRAPH_SLICE = "paragraph_slice"

_PRIVATE_AVAILABLE = False
try:
    from storylens_private_engine.citation import (  # type: ignore
        CitationCatalog as _PrivateCatalog,
        CitationCatalogEntry as _PrivateEntry,
        CitationCatalogResolver as _PrivateResolver,
        CitationResolveError as _PrivateResolveError,
        CitationResolveFailure as _PrivateResolveFailure,
        ResolvedCitationLocator as _PrivateLocator,
        assert_catalog_fingerprints_match as _private_assert_fps,
        build_citation_catalog as _private_build_catalog,
        bundle_hash_prefix as _private_bundle_hash_prefix,
        compute_prompt_catalog_fingerprint as _private_prompt_fp,
        compute_resolver_catalog_fingerprint as _private_resolver_fp,
        compute_schema_catalog_fingerprint as _private_schema_fp,
        format_citation_id as _private_format_citation_id,
        parse_citation_id as _private_parse_citation_id,
    )

    _PRIVATE_AVAILABLE = True
except Exception:  # noqa: BLE001 — optional private package
    _PrivateCatalog = None  # type: ignore[misc, assignment]
    _PrivateEntry = None  # type: ignore[misc, assignment]
    _PrivateResolver = None  # type: ignore[misc, assignment]
    _PrivateResolveError = None  # type: ignore[misc, assignment]
    _PrivateResolveFailure = None  # type: ignore[misc, assignment]
    _PrivateLocator = None  # type: ignore[misc, assignment]
    _private_assert_fps = None  # type: ignore[misc, assignment]
    _private_build_catalog = None  # type: ignore[misc, assignment]
    _private_bundle_hash_prefix = None  # type: ignore[misc, assignment]
    _private_prompt_fp = None  # type: ignore[misc, assignment]
    _private_resolver_fp = None  # type: ignore[misc, assignment]
    _private_schema_fp = None  # type: ignore[misc, assignment]
    _private_format_citation_id = None  # type: ignore[misc, assignment]
    _private_parse_citation_id = None  # type: ignore[misc, assignment]


def _stable_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_hex(payload: Any) -> str:
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def bundle_hash_prefix(bundle_hash: str) -> str:
    if _PRIVATE_AVAILABLE and _private_bundle_hash_prefix is not None:
        return str(_private_bundle_hash_prefix(bundle_hash))
    raw = str(bundle_hash or "").strip()
    if raw.lower().startswith("0x"):
        raw = raw[2:]
    hex_chars = "".join(ch for ch in raw if ch in "0123456789abcdefABCDEF")
    source = hex_chars if len(hex_chars) >= BUNDLE_HASH_PREFIX_LEN else raw
    prefix = source[:BUNDLE_HASH_PREFIX_LEN].upper()
    if len(prefix) < BUNDLE_HASH_PREFIX_LEN:
        prefix = prefix.ljust(BUNDLE_HASH_PREFIX_LEN, "0")
    return prefix


def format_citation_id(bundle_hash: str, ordinal: int) -> str:
    if _PRIVATE_AVAILABLE and _private_format_citation_id is not None:
        return str(_private_format_citation_id(bundle_hash, ordinal))
    if not isinstance(ordinal, int) or ordinal < 1:
        raise ValueError(f"citation ordinal must be a positive int, got {ordinal!r}")
    prefix = bundle_hash_prefix(bundle_hash)
    return f"{CITATION_ID_PREFIX}-{prefix}-{ordinal:0{ORDINAL_WIDTH}d}"


def parse_citation_id(citation_id: str) -> tuple[str, int] | None:
    if _PRIVATE_AVAILABLE and _private_parse_citation_id is not None:
        return _private_parse_citation_id(citation_id)
    text = str(citation_id or "").strip()
    parts = text.split("-")
    if len(parts) != 3:
        return None
    head, prefix, ordinal_s = parts
    if head != CITATION_ID_PREFIX:
        return None
    if len(prefix) != BUNDLE_HASH_PREFIX_LEN:
        return None
    if len(ordinal_s) != ORDINAL_WIDTH or not ordinal_s.isdigit():
        return None
    ordinal = int(ordinal_s)
    if ordinal < 1:
        return None
    return prefix.upper(), ordinal


@dataclass(frozen=True, slots=True)
class CitationCatalogEntry:
    citation_id: str
    context_bundle_hash: str
    snapshot_id: int | str
    chapter_id: int | str | None
    paragraph_id: int | str | None
    stable_paragraph_id: str | None
    content_hash: str
    start_offset: int
    end_offset: int
    source_unit_index: int
    source_unit_type: str
    display_order: int
    text: str = field(default="", repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class CitationCatalog:
    catalog_id: str
    catalog_version: str
    context_bundle_hash: str
    snapshot_id: int | str
    context_bundle_ref: str | None
    entries: tuple[CitationCatalogEntry, ...]
    catalog_fingerprint: str

    @property
    def citation_ids(self) -> tuple[str, ...]:
        return tuple(e.citation_id for e in self.entries)

    def by_citation_id(self) -> dict[str, CitationCatalogEntry]:
        return {e.citation_id: e for e in self.entries}


@dataclass(frozen=True, slots=True)
class ResolvedCitationLocator:
    citation_id: str
    snapshot_id: int | str
    chapter_id: int | str | None
    paragraph_id: int | str | None
    stable_paragraph_id: str | None
    content_hash: str
    start_offset: int
    end_offset: int
    source_unit_index: int
    context_bundle_hash: str
    source_unit_type: str = ""
    display_order: int = 0


@dataclass(frozen=True, slots=True)
class CitationResolveFailure:
    code: str
    citation_id: str
    message: str = ""


class CitationResolveError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(message or code)


def _entry_locator_material(entry: CitationCatalogEntry) -> dict[str, Any]:
    return {
        "citation_id": entry.citation_id,
        "context_bundle_hash": entry.context_bundle_hash,
        "snapshot_id": entry.snapshot_id,
        "chapter_id": entry.chapter_id,
        "paragraph_id": entry.paragraph_id,
        "stable_paragraph_id": entry.stable_paragraph_id,
        "content_hash": entry.content_hash,
        "start_offset": entry.start_offset,
        "end_offset": entry.end_offset,
        "source_unit_index": entry.source_unit_index,
        "source_unit_type": entry.source_unit_type,
        "display_order": entry.display_order,
    }


def compute_catalog_fingerprint(entries: Sequence[CitationCatalogEntry]) -> str:
    return _sha256_hex([_entry_locator_material(e) for e in entries])


def _slice_paragraph(text: str) -> list[tuple[int, int, str]]:
    body = text if isinstance(text, str) else str(text or "")
    n = len(body)
    if n == 0:
        return [(0, 0, "")]
    if n <= MAX_CITATION_UNIT_CHARS:
        return [(0, n, body)]
    out: list[tuple[int, int, str]] = []
    start = 0
    while start < n:
        end = min(start + MAX_CITATION_UNIT_CHARS, n)
        out.append((start, end, body[start:end]))
        start = end
    return out


def _normalize_unit(unit: Mapping[str, Any] | Any) -> dict[str, Any]:
    if isinstance(unit, Mapping):
        return {
            "chapter_id": unit.get("chapter_id", unit.get("snapshot_chapter_id")),
            "paragraph_id": unit.get("paragraph_id", unit.get("snapshot_paragraph_id")),
            "stable_paragraph_id": unit.get("stable_paragraph_id"),
            "content_hash": unit.get("content_hash") or "",
            "text": unit.get("text") or "",
        }
    return {
        "chapter_id": getattr(unit, "chapter_id", getattr(unit, "snapshot_chapter_id", None)),
        "paragraph_id": getattr(
            unit, "paragraph_id", getattr(unit, "snapshot_paragraph_id", None)
        ),
        "stable_paragraph_id": getattr(unit, "stable_paragraph_id", None),
        "content_hash": getattr(unit, "content_hash", "") or "",
        "text": getattr(unit, "text", "") or "",
    }


def _local_build_citation_catalog(
    *,
    context_bundle_hash: str,
    snapshot_id: int | str,
    units: Sequence[Mapping[str, Any]],
    context_bundle_ref: str | None = None,
) -> CitationCatalog:
    bundle_hash = str(context_bundle_hash or "").strip()
    if not bundle_hash:
        raise ValueError("context_bundle_hash is required")
    entries: list[CitationCatalogEntry] = []
    ordinal = 0
    for unit_index, unit in enumerate(units):
        norm = _normalize_unit(unit)
        body = str(norm.get("text") or "")
        content_hash = str(norm.get("content_hash") or "")
        chapter_id = norm.get("chapter_id")
        paragraph_id = norm.get("paragraph_id")
        stable = norm.get("stable_paragraph_id")
        if stable is not None:
            stable = str(stable)
        slices = _slice_paragraph(body)
        for start_offset, end_offset, slice_text in slices:
            ordinal += 1
            unit_type = (
                SOURCE_UNIT_TYPE_PARAGRAPH_SLICE
                if len(body) > MAX_CITATION_UNIT_CHARS
                else SOURCE_UNIT_TYPE_PARAGRAPH
            )
            entries.append(
                CitationCatalogEntry(
                    citation_id=format_citation_id(bundle_hash, ordinal),
                    context_bundle_hash=bundle_hash,
                    snapshot_id=snapshot_id,
                    chapter_id=chapter_id,
                    paragraph_id=paragraph_id,
                    stable_paragraph_id=stable,
                    content_hash=content_hash,
                    start_offset=int(start_offset),
                    end_offset=int(end_offset),
                    source_unit_index=int(unit_index),
                    source_unit_type=unit_type,
                    display_order=ordinal - 1,
                    text=slice_text,
                )
            )
    fingerprint = compute_catalog_fingerprint(entries)
    material = {
        "catalog_version": CATALOG_VERSION,
        "context_bundle_hash": bundle_hash,
        "snapshot_id": snapshot_id,
        "entries": [
            {
                "context_bundle_hash": e.context_bundle_hash,
                "snapshot_id": e.snapshot_id,
                "chapter_id": e.chapter_id,
                "paragraph_id": e.paragraph_id,
                "stable_paragraph_id": e.stable_paragraph_id,
                "content_hash": e.content_hash,
                "start_offset": e.start_offset,
                "end_offset": e.end_offset,
                "source_unit_index": e.source_unit_index,
                "source_unit_type": e.source_unit_type,
                "display_order": e.display_order,
            }
            for e in entries
        ],
    }
    return CitationCatalog(
        catalog_id=_sha256_hex(material),
        catalog_version=CATALOG_VERSION,
        context_bundle_hash=bundle_hash,
        snapshot_id=snapshot_id,
        context_bundle_ref=context_bundle_ref,
        entries=tuple(entries),
        catalog_fingerprint=fingerprint,
    )


def _adapt_private_catalog(catalog: Any) -> CitationCatalog:
    """Normalize private catalog objects into the public CitationCatalog type."""

    if isinstance(catalog, CitationCatalog):
        return catalog
    entries = tuple(
        CitationCatalogEntry(
            citation_id=str(e.citation_id),
            context_bundle_hash=str(e.context_bundle_hash),
            snapshot_id=e.snapshot_id,
            chapter_id=e.chapter_id,
            paragraph_id=e.paragraph_id,
            stable_paragraph_id=e.stable_paragraph_id,
            content_hash=str(e.content_hash or ""),
            start_offset=int(e.start_offset),
            end_offset=int(e.end_offset),
            source_unit_index=int(e.source_unit_index),
            source_unit_type=str(e.source_unit_type),
            display_order=int(e.display_order),
            text=str(getattr(e, "text", "") or ""),
        )
        for e in catalog.entries
    )
    return CitationCatalog(
        catalog_id=str(catalog.catalog_id),
        catalog_version=str(catalog.catalog_version),
        context_bundle_hash=str(catalog.context_bundle_hash),
        snapshot_id=catalog.snapshot_id,
        context_bundle_ref=getattr(catalog, "context_bundle_ref", None),
        entries=entries,
        catalog_fingerprint=str(catalog.catalog_fingerprint),
    )


def build_catalog_from_paragraph_units(
    *,
    context_bundle_hash: str,
    snapshot_id: int | str,
    paragraph_units: Sequence[Mapping[str, Any] | Any],
    context_bundle_ref: str | None = None,
) -> CitationCatalog:
    """Build CitationCatalog from model-visible paragraph units."""

    units = [_normalize_unit(u) for u in paragraph_units]
    if _PRIVATE_AVAILABLE and _private_build_catalog is not None:
        private = _private_build_catalog(
            context_bundle_hash=context_bundle_hash,
            snapshot_id=snapshot_id,
            units=units,
            context_bundle_ref=context_bundle_ref,
        )
        return _adapt_private_catalog(private)
    return _local_build_citation_catalog(
        context_bundle_hash=context_bundle_hash,
        snapshot_id=snapshot_id,
        units=units,
        context_bundle_ref=context_bundle_ref,
    )


class CitationCatalogResolver:
    """Exact citation_id → locator via catalog dict lookup only."""

    def resolve(
        self,
        citation_id: str,
        catalog: CitationCatalog,
        *,
        expected_catalog_id: str | None = None,
        expected_bundle_hash: str | None = None,
        expected_snapshot_id: int | str | None = None,
        raise_on_error: bool = True,
    ) -> ResolvedCitationLocator | CitationResolveFailure:
        if _PRIVATE_AVAILABLE and _PrivateResolver is not None:
            # Prefer private resolver when the catalog came from private; still
            # accept public-local catalogs by converting to private-shaped dict path.
            try:
                private_catalog = catalog
                if _private_build_catalog is not None and not isinstance(
                    catalog, (_PrivateCatalog,)
                ):
                    # Rebuild via private for exact parity when possible.
                    private_catalog = _private_build_catalog(
                        context_bundle_hash=catalog.context_bundle_hash,
                        snapshot_id=catalog.snapshot_id,
                        units=[
                            {
                                "chapter_id": e.chapter_id,
                                "paragraph_id": e.paragraph_id,
                                "stable_paragraph_id": e.stable_paragraph_id,
                                "content_hash": e.content_hash,
                                "text": e.text
                                if (e.end_offset - e.start_offset) == len(e.text)
                                else (" " * max(0, e.end_offset)),
                            }
                            for e in catalog.entries
                        ],
                        context_bundle_ref=catalog.context_bundle_ref,
                    )
                result = _PrivateResolver().resolve(
                    citation_id,
                    private_catalog,
                    expected_catalog_id=expected_catalog_id,
                    expected_bundle_hash=expected_bundle_hash,
                    expected_snapshot_id=expected_snapshot_id,
                    raise_on_error=False,
                )
                if isinstance(result, _PrivateResolveFailure):
                    failure = CitationResolveFailure(
                        code=str(result.code),
                        citation_id=str(result.citation_id),
                        message=str(getattr(result, "message", "") or ""),
                    )
                    if raise_on_error:
                        raise CitationResolveError(failure.code, failure.message)
                    return failure
                return ResolvedCitationLocator(
                    citation_id=str(result.citation_id),
                    snapshot_id=result.snapshot_id,
                    chapter_id=result.chapter_id,
                    paragraph_id=result.paragraph_id,
                    stable_paragraph_id=result.stable_paragraph_id,
                    content_hash=str(result.content_hash or ""),
                    start_offset=int(result.start_offset),
                    end_offset=int(result.end_offset),
                    source_unit_index=int(result.source_unit_index),
                    context_bundle_hash=str(result.context_bundle_hash),
                    source_unit_type=str(getattr(result, "source_unit_type", "") or ""),
                    display_order=int(getattr(result, "display_order", 0) or 0),
                )
            except CitationResolveError:
                raise
            except Exception:  # noqa: BLE001 — fall through to local
                pass
        return self._local_resolve(
            citation_id,
            catalog,
            expected_catalog_id=expected_catalog_id,
            expected_bundle_hash=expected_bundle_hash,
            expected_snapshot_id=expected_snapshot_id,
            raise_on_error=raise_on_error,
        )

    def _fail(
        self,
        code: str,
        citation_id: str,
        *,
        raise_on_error: bool,
        message: str = "",
    ) -> CitationResolveFailure:
        failure = CitationResolveFailure(code=code, citation_id=citation_id, message=message)
        if raise_on_error:
            raise CitationResolveError(code, message)
        return failure

    def _local_resolve(
        self,
        citation_id: str,
        catalog: CitationCatalog,
        *,
        expected_catalog_id: str | None,
        expected_bundle_hash: str | None,
        expected_snapshot_id: int | str | None,
        raise_on_error: bool,
    ) -> ResolvedCitationLocator | CitationResolveFailure:
        cid = str(citation_id or "").strip()
        if expected_catalog_id is not None and str(expected_catalog_id) != catalog.catalog_id:
            return self._fail(
                CITATION_CATALOG_MISMATCH, cid, raise_on_error=raise_on_error, message="catalog_id mismatch"
            )
        if expected_bundle_hash is not None and str(expected_bundle_hash) != catalog.context_bundle_hash:
            return self._fail(
                CITATION_ID_STALE_BUNDLE,
                cid,
                raise_on_error=raise_on_error,
                message="expected context_bundle_hash mismatch",
            )
        if expected_snapshot_id is not None and expected_snapshot_id != catalog.snapshot_id:
            return self._fail(
                CITATION_SNAPSHOT_MISMATCH,
                cid,
                raise_on_error=raise_on_error,
                message="expected snapshot_id mismatch",
            )
        parsed = parse_citation_id(cid)
        if parsed is None:
            return self._fail(
                CITATION_ID_UNKNOWN, cid, raise_on_error=raise_on_error, message="malformed citation_id"
            )
        prefix, _ordinal = parsed
        if prefix != bundle_hash_prefix(catalog.context_bundle_hash):
            return self._fail(
                CITATION_ID_STALE_BUNDLE,
                cid,
                raise_on_error=raise_on_error,
                message="citation_id prefix does not match catalog bundle",
            )
        entry = catalog.by_citation_id().get(cid)
        if entry is None:
            return self._fail(
                CITATION_ID_UNKNOWN, cid, raise_on_error=raise_on_error, message="citation_id not in catalog"
            )
        if entry.paragraph_id is None and entry.stable_paragraph_id is None:
            return self._fail(
                CITATION_LOCATOR_INVALID, cid, raise_on_error=raise_on_error, message="locator incomplete"
            )
        if not str(entry.content_hash or "").strip():
            return self._fail(
                CITATION_HASH_MISMATCH, cid, raise_on_error=raise_on_error, message="content_hash missing"
            )
        start = int(entry.start_offset)
        end = int(entry.end_offset)
        if start < 0 or end < 0 or start > end:
            return self._fail(
                CITATION_OFFSET_INVALID, cid, raise_on_error=raise_on_error, message="invalid offsets"
            )
        return ResolvedCitationLocator(
            citation_id=entry.citation_id,
            snapshot_id=entry.snapshot_id,
            chapter_id=entry.chapter_id,
            paragraph_id=entry.paragraph_id,
            stable_paragraph_id=entry.stable_paragraph_id,
            content_hash=entry.content_hash,
            start_offset=start,
            end_offset=end,
            source_unit_index=entry.source_unit_index,
            context_bundle_hash=entry.context_bundle_hash,
            source_unit_type=entry.source_unit_type,
            display_order=entry.display_order,
        )


def resolve_citation(
    citation_id: str,
    catalog: CitationCatalog,
    **kwargs: Any,
) -> ResolvedCitationLocator | CitationResolveFailure:
    """Thin wrapper around CitationCatalogResolver.resolve."""

    return CitationCatalogResolver().resolve(citation_id, catalog, **kwargs)


def fingerprints_match(catalog: CitationCatalog) -> bool:
    """Return True when prompt/schema/resolver fingerprints equal catalog fingerprint."""

    if _PRIVATE_AVAILABLE and _private_assert_fps is not None:
        try:
            _private_assert_fps(catalog)
            return True
        except Exception:  # noqa: BLE001
            # Private assert may reject public-local catalog type; compare locally.
            pass
    expected = catalog.catalog_fingerprint
    recomputed = compute_catalog_fingerprint(catalog.entries)
    if _PRIVATE_AVAILABLE and _private_prompt_fp is not None:
        try:
            prompt_fp = str(_private_prompt_fp(catalog))
            schema_fp = str(_private_schema_fp(catalog))  # type: ignore[misc]
            resolver_fp = str(_private_resolver_fp(catalog))  # type: ignore[misc]
            return len({expected, recomputed, prompt_fp, schema_fp, resolver_fp}) == 1
        except Exception:  # noqa: BLE001
            pass
    return expected == recomputed


def private_citation_available() -> bool:
    return bool(_PRIVATE_AVAILABLE)


class _PrivateEngineCatalogAdapter:
    """Adapt public ``CitationCatalog`` (property ``citation_ids``) for private engine API."""

    __slots__ = ("_catalog",)

    def __init__(self, catalog: CitationCatalog) -> None:
        self._catalog = catalog

    def citation_ids(self) -> tuple[str, ...]:
        return tuple(self._catalog.citation_ids)

    def by_citation_id(self) -> dict[str, CitationCatalogEntry]:
        return dict(self._catalog.by_citation_id())

    @property
    def catalog_id(self) -> str:
        return self._catalog.catalog_id

    @property
    def catalog_version(self) -> str:
        return self._catalog.catalog_version

    @property
    def context_bundle_hash(self) -> str:
        return self._catalog.context_bundle_hash

    @property
    def snapshot_id(self) -> int | str:
        return self._catalog.snapshot_id

    @property
    def context_bundle_ref(self) -> str | None:
        return self._catalog.context_bundle_ref

    @property
    def entries(self) -> tuple[CitationCatalogEntry, ...]:
        return self._catalog.entries

    @property
    def catalog_fingerprint(self) -> str:
        return self._catalog.catalog_fingerprint


def catalog_for_private_engine(catalog: Any | None) -> Any | None:
    """Return a private-engine-compatible catalog view (``citation_ids()`` callable)."""

    if catalog is None:
        return None
    ids = getattr(catalog, "citation_ids", None)
    if callable(ids):
        return catalog
    if hasattr(catalog, "entries") and hasattr(catalog, "catalog_id"):
        return _PrivateEngineCatalogAdapter(catalog)
    return catalog


__all__ = [
    "BUNDLE_HASH_PREFIX_LEN",
    "CATALOG_VERSION",
    "CITATION_CATALOG_MISMATCH",
    "CITATION_HASH_MISMATCH",
    "CITATION_ID_FORMAT_VERSION",
    "CITATION_ID_PREFIX",
    "CITATION_ID_STALE_BUNDLE",
    "CITATION_ID_UNKNOWN",
    "CITATION_LOCATOR_INVALID",
    "CITATION_OFFSET_INVALID",
    "CITATION_SNAPSHOT_MISMATCH",
    "CitationCatalog",
    "CitationCatalogEntry",
    "CitationCatalogResolver",
    "CitationResolveError",
    "CitationResolveFailure",
    "EVIDENCE_CONTRACT_VERSION",
    "MAX_CITATION_UNIT_CHARS",
    "ORDINAL_WIDTH",
    "ResolvedCitationLocator",
    "build_catalog_from_paragraph_units",
    "bundle_hash_prefix",
    "catalog_for_private_engine",
    "compute_catalog_fingerprint",
    "fingerprints_match",
    "format_citation_id",
    "parse_citation_id",
    "private_citation_available",
    "resolve_citation",
]
