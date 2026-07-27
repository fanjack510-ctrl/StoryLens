"""Source context fingerprint for analysis artifacts (book/chapter/run/scene/text)."""

from __future__ import annotations

import hashlib
import json
from typing import Iterable, Sequence


FINGERPRINT_VERSION = "v1"


def _stable_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def paragraph_content_hash(raw_text: str | None) -> str:
    return hashlib.sha256((raw_text or "").encode("utf-8")).hexdigest()


def compute_source_context_fingerprint(
    *,
    book_id: int,
    chapter_id: int,
    analysis_run_id: int,
    scene_id: int | None,
    ordered_paragraph_ids: Sequence[str],
    paragraph_content_hashes: Sequence[str],
    prompt_version: str | None = None,
    contract_version: str | None = None,
    formula_version: str | None = None,
) -> str:
    """Deterministic fingerprint tying an artifact to exact textual context."""
    if len(ordered_paragraph_ids) != len(paragraph_content_hashes):
        raise ValueError("paragraph_ids and content hashes length mismatch")
    payload = {
        "v": FINGERPRINT_VERSION,
        "book_id": int(book_id),
        "chapter_id": int(chapter_id),
        "analysis_run_id": int(analysis_run_id),
        "scene_id": int(scene_id) if scene_id is not None else None,
        "paragraph_ids": list(ordered_paragraph_ids),
        "paragraph_content_hashes": list(paragraph_content_hashes),
        "prompt_version": prompt_version or "",
        "contract_version": contract_version or "",
        "formula_version": formula_version or "",
    }
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def fingerprint_digest_short(fingerprint: str | None, *, n: int = 12) -> str | None:
    if not fingerprint:
        return None
    return fingerprint[:n]


def build_request_scope_binding(
    *,
    book_id: int,
    chapter_id: int,
    analysis_run_id: int,
    scene_ids: Iterable[int],
    ordered_paragraph_ids: Sequence[str],
    exact_input_content_hash: str,
    prompt_version: str,
    contract_version: str,
    formula_version: str,
    analysis_mode: str,
    provider: str,
    model_id: str,
) -> dict[str, object]:
    """
    Scope identity that must participate in request hashing / cache keys.

    Callers should place this under ModelRequest.extra_body['analysis_scope']
    so sha256(ModelRequest JSON) includes book/run/scene/content identity.
    """
    return {
        "book_id": int(book_id),
        "chapter_id": int(chapter_id),
        "analysis_run_id": int(analysis_run_id),
        "scene_ids": sorted({int(s) for s in scene_ids}),
        "paragraph_ids": list(ordered_paragraph_ids),
        "exact_input_content_hash": exact_input_content_hash,
        "prompt_version": prompt_version,
        "contract_version": contract_version,
        "formula_version": formula_version,
        "analysis_mode": analysis_mode,
        "provider": provider,
        "model_id": model_id,
    }
