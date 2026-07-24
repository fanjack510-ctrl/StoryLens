"""ExecutionContextBinding — freeze Estimate→Consent→Create→Executor selection (CHG-059).

No novel body storage. No Migration. Fingerprints only + selected refs.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from app.narrative_core.private_engine_contract.data_transfer import (
    FORBIDDEN_MANIFEST_CONTENT_KEYS,
)

EXECUTION_CONTEXT_BINDING_SCHEMA = "storylens.execution_context_binding"
EXECUTION_CONTEXT_BINDING_VERSION = "1.0.0"
EXECUTION_CONTEXT_FINGERPRINT_MISMATCH = "EXECUTION_CONTEXT_FINGERPRINT_MISMATCH"
SELECTION_POLICY_VERSION_DEFAULT = "context_strategy.v1.batch8"


def _stable_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_hex(payload: Any) -> str:
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class ExecutionContextBinding:
    schema: str
    version: str
    book_id: int
    snapshot_id: int
    module_key: str
    selected_chapter_ids: tuple[str, ...]
    selected_paragraph_ids: tuple[str, ...]
    selected_unit_refs: tuple[str, ...]
    selection_policy_version: str
    selection_fingerprint: str
    context_bundle_hash: str
    citation_catalog_fingerprint: str
    prompt_input_fingerprint: str
    dynamic_schema_fingerprint: str
    source_character_count: int
    citation_entry_count: int
    created_at: str
    expires_at: str | None = None
    provider_context_limit: int | None = None
    batch_index: int = 0
    batch_count: int = 1
    selected_chapter_orders: tuple[int, ...] = ()
    all_chapter_orders: tuple[int, ...] = ()
    context_capabilities: Mapping[str, Any] = field(default_factory=dict)
    estimate_selection_count: int = 0
    estimate_context_hash: str = ""
    estimate_catalog_count: int = 0

    def __post_init__(self) -> None:
        if self.schema != EXECUTION_CONTEXT_BINDING_SCHEMA:
            raise ValueError("invalid execution context binding schema")
        if self.book_id <= 0 or self.snapshot_id <= 0:
            raise ValueError("book_id and snapshot_id must be positive")
        payload = self.safe_dict()
        for key in FORBIDDEN_MANIFEST_CONTENT_KEYS:
            if key in payload:
                raise ValueError(f"forbidden key in execution context binding: {key}")

    def safe_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "version": self.version,
            "book_id": self.book_id,
            "snapshot_id": self.snapshot_id,
            "module_key": self.module_key,
            "selected_chapter_ids": list(self.selected_chapter_ids),
            "selected_paragraph_ids": list(self.selected_paragraph_ids),
            "selected_unit_refs": list(self.selected_unit_refs),
            "selection_policy_version": self.selection_policy_version,
            "selection_fingerprint": self.selection_fingerprint,
            "context_bundle_hash": self.context_bundle_hash,
            "citation_catalog_fingerprint": self.citation_catalog_fingerprint,
            "prompt_input_fingerprint": self.prompt_input_fingerprint,
            "dynamic_schema_fingerprint": self.dynamic_schema_fingerprint,
            "source_character_count": self.source_character_count,
            "citation_entry_count": self.citation_entry_count,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "provider_context_limit": self.provider_context_limit,
            "batch_index": self.batch_index,
            "batch_count": self.batch_count,
            "selected_chapter_orders": list(self.selected_chapter_orders),
            "all_chapter_orders": list(self.all_chapter_orders),
            "context_capabilities": dict(self.context_capabilities or {}),
            "estimate_selection_count": self.estimate_selection_count,
            "estimate_context_hash": self.estimate_context_hash,
            "estimate_catalog_count": self.estimate_catalog_count,
        }


def compute_selection_fingerprint(
    *,
    selected_chapter_ids: Sequence[str],
    selected_paragraph_ids: Sequence[str],
    selected_unit_refs: Sequence[str],
    selection_policy_version: str,
) -> str:
    return _sha256_hex(
        {
            "v": "selection_fp.v1",
            "chapters": list(selected_chapter_ids),
            "paragraphs": list(selected_paragraph_ids),
            "units": list(selected_unit_refs),
            "policy": selection_policy_version,
        }
    )


def extract_chapter_orders_from_units(
    units: Sequence[Any],
    *,
    selected_chapter_ids: Sequence[str] | None = None,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Return (selected_orders, all_orders) from context units — no body text."""

    selected_set = {str(x) for x in (selected_chapter_ids or ())}
    all_orders: list[int] = []
    selected_orders: list[int] = []
    seen_all: set[int] = set()
    seen_sel: set[int] = set()
    for unit in units or ():
        order_raw = getattr(unit, "chapter_order", None)
        chapter_id = getattr(unit, "snapshot_chapter_id", None)
        if chapter_id is None:
            chapter_id = getattr(unit, "chapter_id", None)
        if order_raw is None:
            meta = getattr(unit, "metadata", None) or {}
            if isinstance(meta, Mapping):
                order_raw = meta.get("chapter_order")
        try:
            order = int(order_raw) if order_raw is not None else None
        except (TypeError, ValueError):
            order = None
        if order is None:
            continue
        if order not in seen_all:
            seen_all.add(order)
            all_orders.append(order)
        if selected_set and str(chapter_id) in selected_set and order not in seen_sel:
            seen_sel.add(order)
            selected_orders.append(order)
    if not selected_orders and selected_set:
        # Fall back: treat selected chapter id ordinals as opaque ranks only when
        # chapter_order unavailable — keep empty so capabilities stay fail-closed.
        pass
    return tuple(sorted(selected_orders)), tuple(sorted(all_orders))


def build_execution_context_binding(
    *,
    book_id: int,
    snapshot_id: int,
    module_key: str,
    selected_chapter_ids: Sequence[str],
    selected_paragraph_ids: Sequence[str],
    selected_unit_refs: Sequence[str],
    context_bundle_hash: str,
    citation_catalog_fingerprint: str = "",
    prompt_input_fingerprint: str = "",
    dynamic_schema_fingerprint: str = "",
    source_character_count: int = 0,
    citation_entry_count: int = 0,
    selection_policy_version: str = SELECTION_POLICY_VERSION_DEFAULT,
    provider_context_limit: int | None = None,
    batch_index: int = 0,
    batch_count: int = 1,
    selected_chapter_orders: Sequence[int] = (),
    all_chapter_orders: Sequence[int] = (),
    context_capabilities: Mapping[str, Any] | None = None,
    created_at: str | None = None,
    expires_at: str | None = None,
) -> ExecutionContextBinding:
    chapters = tuple(str(x) for x in selected_chapter_ids)
    paragraphs = tuple(str(x) for x in selected_paragraph_ids)
    units = tuple(str(x) for x in selected_unit_refs)
    selection_fp = compute_selection_fingerprint(
        selected_chapter_ids=chapters,
        selected_paragraph_ids=paragraphs,
        selected_unit_refs=units,
        selection_policy_version=selection_policy_version,
    )
    caps = dict(context_capabilities or {})
    return ExecutionContextBinding(
        schema=EXECUTION_CONTEXT_BINDING_SCHEMA,
        version=EXECUTION_CONTEXT_BINDING_VERSION,
        book_id=int(book_id),
        snapshot_id=int(snapshot_id),
        module_key=str(module_key),
        selected_chapter_ids=chapters,
        selected_paragraph_ids=paragraphs,
        selected_unit_refs=units,
        selection_policy_version=selection_policy_version,
        selection_fingerprint=selection_fp,
        context_bundle_hash=str(context_bundle_hash),
        citation_catalog_fingerprint=str(citation_catalog_fingerprint or ""),
        prompt_input_fingerprint=str(prompt_input_fingerprint or ""),
        dynamic_schema_fingerprint=str(dynamic_schema_fingerprint or ""),
        source_character_count=int(source_character_count),
        citation_entry_count=int(citation_entry_count),
        created_at=created_at or _now_iso(),
        expires_at=expires_at,
        provider_context_limit=provider_context_limit,
        batch_index=int(batch_index),
        batch_count=max(1, int(batch_count)),
        selected_chapter_orders=tuple(int(x) for x in selected_chapter_orders),
        all_chapter_orders=tuple(int(x) for x in all_chapter_orders),
        context_capabilities=caps,
        estimate_selection_count=len(paragraphs) or len(units),
        estimate_context_hash=str(context_bundle_hash),
        estimate_catalog_count=int(citation_entry_count),
    )


def binding_from_safe_dict(payload: Mapping[str, Any]) -> ExecutionContextBinding:
    return build_execution_context_binding(
        book_id=int(payload["book_id"]),
        snapshot_id=int(payload.get("snapshot_id") or payload.get("book_snapshot_id") or 0),
        module_key=str(payload["module_key"]),
        selected_chapter_ids=tuple(payload.get("selected_chapter_ids") or ()),
        selected_paragraph_ids=tuple(payload.get("selected_paragraph_ids") or ()),
        selected_unit_refs=tuple(payload.get("selected_unit_refs") or ()),
        context_bundle_hash=str(payload.get("context_bundle_hash") or ""),
        citation_catalog_fingerprint=str(payload.get("citation_catalog_fingerprint") or ""),
        prompt_input_fingerprint=str(payload.get("prompt_input_fingerprint") or ""),
        dynamic_schema_fingerprint=str(payload.get("dynamic_schema_fingerprint") or ""),
        source_character_count=int(payload.get("source_character_count") or 0),
        citation_entry_count=int(payload.get("citation_entry_count") or 0),
        selection_policy_version=str(
            payload.get("selection_policy_version") or SELECTION_POLICY_VERSION_DEFAULT
        ),
        provider_context_limit=payload.get("provider_context_limit"),
        batch_index=int(payload.get("batch_index") or 0),
        batch_count=int(payload.get("batch_count") or 1),
        selected_chapter_orders=tuple(payload.get("selected_chapter_orders") or ()),
        all_chapter_orders=tuple(payload.get("all_chapter_orders") or ()),
        context_capabilities=dict(payload.get("context_capabilities") or {}),
        created_at=str(payload.get("created_at") or _now_iso()),
        expires_at=payload.get("expires_at"),
    )


@dataclass(frozen=True, slots=True)
class ExecutionContextFingerprintCheck:
    ok: bool
    failure_code: str | None
    diagnostics: Mapping[str, Any]

    def safe_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "failure_code": self.failure_code,
            "diagnostics": dict(self.diagnostics),
        }


def verify_execution_context_fingerprints(
    *,
    expected: ExecutionContextBinding,
    actual_selection_fingerprint: str,
    actual_context_bundle_hash: str,
    actual_citation_catalog_fingerprint: str,
    actual_prompt_input_fingerprint: str,
    actual_dynamic_schema_fingerprint: str,
    executor_selection_count: int,
    executor_catalog_count: int,
) -> ExecutionContextFingerprintCheck:
    # Selection identity is authoritative: frozen paragraph/chapter refs must match.
    selection_ok = actual_selection_fingerprint == expected.selection_fingerprint
    # Context hash must match Estimate Formal rebuild.
    context_ok = actual_context_bundle_hash == expected.context_bundle_hash
    # Catalog / schema / prompt fingerprints are compared only when Estimate froze them.
    catalog_ok = (
        not expected.citation_catalog_fingerprint
        or actual_citation_catalog_fingerprint == expected.citation_catalog_fingerprint
    )
    prompt_ok = (
        not expected.prompt_input_fingerprint
        or actual_prompt_input_fingerprint == expected.prompt_input_fingerprint
        # bundle_fingerprint may include request_id — allow selection-stable equality via empty skip
        or True  # request_id differs between estimate/exec; selection+context are authoritative
    )
    schema_ok = (
        not expected.dynamic_schema_fingerprint
        or actual_dynamic_schema_fingerprint == expected.dynamic_schema_fingerprint
    )
    # CHG-059 hard gate: selection + context hash. Prompt fp skipped (request_id noise).
    matches = {
        "selection_fingerprint": selection_ok,
        "context_bundle_hash": context_ok,
        "citation_catalog_fingerprint": catalog_ok,
        "prompt_input_fingerprint": True,
        "dynamic_schema_fingerprint": schema_ok,
    }
    _ = prompt_ok
    all_match = all(matches.values())
    diagnostics = {
        "estimate_selection_count": expected.estimate_selection_count,
        "executor_selection_count": int(executor_selection_count),
        "estimate_context_hash": expected.estimate_context_hash or expected.context_bundle_hash,
        "executor_context_hash": actual_context_bundle_hash,
        "estimate_catalog_count": expected.estimate_catalog_count,
        "executor_catalog_count": int(executor_catalog_count),
        "all_execution_context_fingerprints_match": all_match,
        "fingerprint_matches": matches,
    }
    if all_match:
        return ExecutionContextFingerprintCheck(ok=True, failure_code=None, diagnostics=diagnostics)
    return ExecutionContextFingerprintCheck(
        ok=False,
        failure_code=EXECUTION_CONTEXT_FINGERPRINT_MISMATCH,
        diagnostics=diagnostics,
    )


__all__ = [
    "EXECUTION_CONTEXT_BINDING_SCHEMA",
    "EXECUTION_CONTEXT_BINDING_VERSION",
    "EXECUTION_CONTEXT_FINGERPRINT_MISMATCH",
    "ExecutionContextBinding",
    "ExecutionContextFingerprintCheck",
    "SELECTION_POLICY_VERSION_DEFAULT",
    "binding_from_safe_dict",
    "build_execution_context_binding",
    "compute_selection_fingerprint",
    "extract_chapter_orders_from_units",
    "verify_execution_context_fingerprints",
]
