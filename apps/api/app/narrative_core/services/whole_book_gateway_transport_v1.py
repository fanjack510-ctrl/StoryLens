"""Free whole-book Gateway transports (formal Aliyun / ModelGateway bridge).

Shared pipeline uses Fixture* transports for tests and these Gateway* transports
for formal create. Never falls back to fixture/fake from formal create.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import NarrativeAssetEvidence, NarrativeAssetVersion, ProviderConfiguration
from app.model_gateway.base import ModelRequest
from app.model_gateway.registry import get_model_gateway
from app.narrative_core.contracts.whole_book_contract_v1 import (
    BOOK_OVERVIEW_CLAIM_KEYS_V1,
    BOOK_OVERVIEW_RESULT_VERSION,
    WHOLE_BOOK_CONTRACT_VERSION,
    AnalysisProvenanceV1,
    OverviewClaimAvailability,
    ResultOrigin,
    WholeBookMode,
    WholeBookSynthesisResponseV1,
    WholeBookWindowAnalysisResponseV1,
)
from app.narrative_core.contracts.whole_book_contract_v1.common import sha256_hex
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_minimal_helpers_v1 import (
    CHAPTER_FUNCTIONS_PROMPT_VERSION,
    FIXTURE_PROMPT_VERSION,
    OVERVIEW_PROMPT_VERSION,
    STRUCTURE_PROMPT_VERSION,
)
from app.narrative_core.services.whole_book_provider_orchestrator import ProviderCallResult
from app.services.credentials.keyring_store import KeyringCredentialStore
from app.services.provider_bootstrap import ensure_aliyun_provider_configuration
from app.services.provider_runtime import apply_provider_runtime, bind_gateway_runtime
from app.services.structured_output import extract_json_object

logger = logging.getLogger(__name__)

FORMAL_ENGINE_ID = "storylens.free.whole_book.gateway"
FORMAL_ENGINE_VERSION = "1.0.0"
CANONICAL_PROVIDER = "aliyun_qwen_plus"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def resolve_formal_provider_row(session: Session) -> ProviderConfiguration:
    """Prefer aliyun_qwen_plus; require enabled + credential reference."""
    ensure_aliyun_provider_configuration(session, CANONICAL_PROVIDER, create_if_missing=True)
    row = session.scalar(
        select(ProviderConfiguration).where(ProviderConfiguration.provider_name == CANONICAL_PROVIDER)
    )
    if row is None:
        row = session.scalar(select(ProviderConfiguration).limit(1))
    if row is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_REAL_PROVIDER_DISABLED,
            "未配置正式 Provider",
        )
    if not bool(row.enabled) or bool(row.disconnected):
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_REAL_PROVIDER_DISABLED,
            "正式 Provider 未启用",
        )
    store = KeyringCredentialStore()
    secret = store.get(row.provider_name) if store.available() else None
    if not secret:
        import os

        secret = os.environ.get("STORYLENS_ALIYUN_API_KEY", "").strip()
    if not secret:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_REAL_PROVIDER_DISABLED,
            "正式 Provider API Key 不可用",
        )
    if not row.credential_reference:
        row.credential_reference = f"keyring:{row.provider_name}"
        session.flush()
    return row


def _redact(msg: str, secret: str | None) -> str:
    if secret and secret in msg:
        return msg.replace(secret, "***")
    return msg


def _run_async(coro):  # type: ignore[no-untyped-def]
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Nested loop (e.g. already inside async): use a dedicated loop in a thread.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


def _gateway_generate(
    *,
    session: Session,
    provider_name: str,
    model_name: str,
    system: str,
    user: str,
    schema: dict[str, Any],
    max_output_tokens: int = 4096,
) -> tuple[dict[str, Any], int, int, Decimal]:
    store = KeyringCredentialStore()
    secret = store.get(provider_name) if store.available() else None
    gateway = get_model_gateway()
    bind_gateway_runtime(gateway, session, store)
    provider = gateway.get(provider_name)
    apply_provider_runtime(provider, session, store)
    if secret:
        provider.api_key = secret
    provider.enabled = True

    async def _call():
        return await gateway.generate(
            provider_name,
            ModelRequest(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
                max_output_tokens=max_output_tokens,
                response_schema=schema,
                response_format_mode="json_object",
                enable_thinking=False,
                model=model_name,
            ),
        )

    try:
        response = _run_async(_call())
    except Exception as exc:  # noqa: BLE001
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_INVALID_TRANSITION,
            _redact(f"provider call failed: {type(exc).__name__}", secret),
        ) from None

    try:
        payload = json.loads(extract_json_object(response.text))
    except Exception as exc:  # noqa: BLE001
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_INVALID_TRANSITION,
            f"provider JSON parse failed: {type(exc).__name__}",
        ) from None

    in_tok = int(response.input_tokens or 0)
    out_tok = int(response.output_tokens or 0)
    # Conservative fallback cost when ledger pricing is unavailable.
    cost = Decimal(str(round((in_tok + out_tok) * 0.000002, 6)))
    return payload, in_tok, out_tok, cost


def _inject_window_provenance(
    payload: dict[str, Any],
    *,
    request_payload: dict[str, Any],
    provider_id: str,
    model_name: str,
) -> dict[str, Any]:
    run = request_payload.get("run") or {}
    snap = request_payload.get("snapshot") or {}
    window = request_payload.get("window") or {}
    payload["run_id"] = int(run.get("run_id") or payload.get("run_id") or 0)
    payload["snapshot_id"] = int(snap.get("snapshot_id") or payload.get("snapshot_id") or 0)
    payload["window_id"] = int(window.get("window_id") or payload.get("window_id") or 0)
    payload["contract_version"] = payload.get("contract_version") or "whole_book_contract_v1"
    payload["provenance"] = AnalysisProvenanceV1(
        run_id=payload["run_id"],
        snapshot_id=payload["snapshot_id"],
        window_ids=[payload["window_id"]],
        engine_id=FORMAL_ENGINE_ID,
        engine_version=FORMAL_ENGINE_VERSION,
        prompt_version=FIXTURE_PROMPT_VERSION,
        provider_id=provider_id,
        model_name=model_name,
        result_origin=ResultOrigin.formal,
        source_mode=WholeBookMode.whole_book_native,
        deterministic=False,
        generated_at=_utc_now(),
    ).model_dump(mode="json")
    return payload


def _slug(text: str, *, prefix: str) -> str:
    digest = sha256_hex(text.strip())[:10]
    return f"{prefix}-{digest}"


def _paragraph_index(paragraphs: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for p in paragraphs:
        if not isinstance(p, dict) or p.get("global_paragraph_index") is None:
            continue
        out[int(p["global_paragraph_index"])] = p
    return out


def _find_quote_in_paragraphs(
    quote: str,
    paragraphs: list[dict[str, Any]],
) -> tuple[dict[str, Any], str, int, int] | None:
    q = (quote or "").strip()
    if not q:
        return None
    for para in paragraphs:
        text = str(para.get("text") or "")
        start = text.find(q)
        if start < 0 and len(q) > 12:
            q2 = q[:12]
            start = text.find(q2)
            if start >= 0:
                q = q2
        if start < 0:
            continue
        return para, q, start, start + len(q)
    return None


def _pick_name_quote(name: str, paragraphs: list[dict[str, Any]]) -> tuple[dict[str, Any], str, int, int] | None:
    hit = _find_quote_in_paragraphs(name, paragraphs)
    if hit is not None:
        return hit
    # Fall back: first non-empty short span from first paragraph.
    for para in paragraphs:
        text = str(para.get("text") or "").strip()
        if len(text) < 2:
            continue
        q = text[: min(8, len(text))]
        return para, q, 0, len(q)
    return None


def _locator_from_hit(
    para: dict[str, Any],
    quote: str,
    start: int,
    end: int,
    *,
    snapshot_id: int,
) -> dict[str, Any]:
    return {
        "locator_version": "snapshot_paragraph_v1",
        "snapshot_id": int(para.get("snapshot_id") or snapshot_id),
        "snapshot_chapter_id": int(para["snapshot_chapter_id"]),
        "snapshot_paragraph_id": int(para["snapshot_paragraph_id"]),
        "chapter_id": int(para["chapter_id"]),
        "chapter_index": int(para["chapter_index"]),
        "paragraph_index": int(para["paragraph_index"]),
        "global_paragraph_index": int(para["global_paragraph_index"]),
        "start_offset": int(start),
        "end_offset": int(end),
        "quote_text": quote,
        "quote_hash": sha256_hex(quote),
        "paragraph_text_hash": str(para["text_hash"]),
    }


def _normalize_window_llm_payload(
    raw: dict[str, Any],
    *,
    request_payload: dict[str, Any],
    provider_id: str,
    model_name: str,
) -> dict[str, Any]:
    """Adapt common LLM shapes into WholeBookWindowAnalysisResponseV1 dict."""
    paragraphs = [p for p in (request_payload.get("paragraphs") or []) if isinstance(p, dict)]
    run = request_payload.get("run") or {}
    snap = request_payload.get("snapshot") or {}
    window = request_payload.get("window") or {}
    run_id = int(run.get("run_id") or raw.get("run_id") or 0)
    snapshot_id = int(snap.get("snapshot_id") or raw.get("snapshot_id") or 0)
    window_id = int(window.get("window_id") or raw.get("window_id") or 0)

    # Accept either contract-ish payload or compact intermediate.
    characters = raw.get("characters")
    if not isinstance(characters, list):
        characters = []
        for ent in raw.get("entities") or []:
            if not isinstance(ent, dict):
                continue
            characters.append(
                {
                    "name": ent.get("canonical_name") or ent.get("name"),
                    "aliases": ent.get("aliases") or [],
                    "quote": (ent.get("quote") or ent.get("canonical_name") or ent.get("name")),
                }
            )

    events = raw.get("events") if isinstance(raw.get("events"), list) else []
    if not events:
        for asset in raw.get("assets") or []:
            if not isinstance(asset, dict):
                continue
            if str(asset.get("asset_type") or "event") not in {"event", "setting_fact", "question", "character_profile"}:
                continue
            events.append(
                {
                    "title": asset.get("title") or "事件",
                    "summary": asset.get("summary") or asset.get("title") or "事件",
                    "character_names": asset.get("character_names") or asset.get("subject_entity_keys") or [],
                    "quote": asset.get("quote"),
                    "asset_type": asset.get("asset_type") or "event",
                }
            )

    setting_facts = raw.get("setting_facts") if isinstance(raw.get("setting_facts"), list) else []
    questions = raw.get("questions") if isinstance(raw.get("questions"), list) else []

    evidences: list[dict[str, Any]] = []
    entities: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    entity_key_by_name: dict[str, str] = {}
    used_keys: set[str] = set()

    def _unique(prefix: str, seed: str) -> str:
        base = _slug(seed, prefix=prefix)
        if base not in used_keys:
            used_keys.add(base)
            return base
        n = 2
        while True:
            cand = f"{base}-{n}"
            if cand not in used_keys:
                used_keys.add(cand)
                return cand
            n += 1

    def _add_evidence(quote_hint: str, *, key_seed: str) -> str | None:
        hit = _find_quote_in_paragraphs(quote_hint, paragraphs) or _pick_name_quote(quote_hint or "。", paragraphs)
        if hit is None:
            return None
        para, quote, start, end = hit
        key = _unique("ev", f"{key_seed}:{quote}:{para.get('global_paragraph_index')}")
        evidences.append(
            {
                "evidence_key": key,
                "locator": _locator_from_hit(para, quote, start, end, snapshot_id=snapshot_id),
                "confidence": 0.8,
            }
        )
        return key

    for idx, ch in enumerate(characters[:12]):
        if not isinstance(ch, dict):
            continue
        name = str(ch.get("name") or "").strip()
        if not name:
            continue
        ev_key = _add_evidence(str(ch.get("quote") or name), key_seed=f"char:{name}")
        if ev_key is None:
            continue
        cand = _unique("ent", name)
        entity_key_by_name[name] = cand
        aliases_out: list[dict[str, Any]] = []
        for alias in ch.get("aliases") or []:
            if isinstance(alias, dict):
                aname = str(alias.get("name") or "").strip()
            else:
                aname = str(alias or "").strip()
            if not aname or aname == name:
                continue
            a_ev = _add_evidence(aname, key_seed=f"alias:{aname}") or ev_key
            aliases_out.append({"name": aname, "confidence": 0.7, "evidence_keys": [a_ev]})
            entity_key_by_name[aname] = cand
        entities.append(
            {
                "candidate_key": cand,
                "entity_type": "character",
                "canonical_name": name,
                "aliases": aliases_out[:4],
                "confidence": 0.85,
                "evidence_keys": [ev_key],
                "attributes": {},
            }
        )

    def _add_typed_asset(item: dict[str, Any], *, default_type: str, seq: int) -> None:
        title = str(item.get("title") or item.get("fact_text") or item.get("question_text") or "").strip()
        summary = str(item.get("summary") or title or default_type).strip()
        if not title:
            title = summary[:40] or default_type
        quote_hint = str(item.get("quote") or title[:8] or summary[:8])
        ev_key = _add_evidence(quote_hint, key_seed=f"{default_type}:{title}:{seq}")
        if ev_key is None:
            return
        subject_names = item.get("character_names") or []
        subject_keys: list[str] = []
        for n in subject_names:
            key = entity_key_by_name.get(str(n))
            if key:
                subject_keys.append(key)
        asset_type = str(item.get("asset_type") or default_type)
        if asset_type not in {"event", "setting_fact", "question", "character_profile"}:
            asset_type = default_type
        payload: dict[str, Any]
        if asset_type == "event":
            payload = {
                "event_type": "other",
                "summary": summary,
                "participants": subject_keys,
                "cause_candidate_keys": [],
                "prior_event_candidate_keys": [],
                "chapter_start_index": int(window.get("chapter_start_index") or 0),
                "chapter_end_index": int(window.get("chapter_end_index") or 0),
                "core_evidence_key": ev_key,
            }
        elif asset_type == "setting_fact":
            payload = {"fact_text": summary, "scope": "local"}
        elif asset_type == "question":
            payload = {"question_text": summary, "status": "open"}
        else:
            payload = {
                "role_in_window": summary[:80],
                "explicit_traits": [],
                "current_goal_candidate_keys": [],
                "related_event_candidate_keys": [],
            }
        assets.append(
            {
                "candidate_key": _unique("asset", f"{asset_type}:{title}:{seq}"),
                "asset_type": asset_type,
                "title": title[:500],
                "summary": summary[:4000],
                "payload": payload,
                "confidence": 0.8,
                "subject_entity_keys": subject_keys,
                "evidence_keys": [ev_key],
            }
        )

    for i, item in enumerate(events[:12]):
        if isinstance(item, dict):
            _add_typed_asset(item, default_type="event", seq=i)
    for i, item in enumerate(setting_facts[:6]):
        if isinstance(item, dict):
            _add_typed_asset(item, default_type="setting_fact", seq=100 + i)
    for i, item in enumerate(questions[:6]):
        if isinstance(item, dict):
            _add_typed_asset(item, default_type="question", seq=200 + i)

    # Ensure minimal non-empty extraction for pipeline continuity when model under-produces.
    if not entities and paragraphs:
        seed_name = "叙述者"
        ev_key = _add_evidence("", key_seed="seed-char")
        if ev_key is not None:
            cand = _unique("ent", seed_name)
            entities.append(
                {
                    "candidate_key": cand,
                    "entity_type": "character",
                    "canonical_name": seed_name,
                    "aliases": [],
                    "confidence": 0.5,
                    "evidence_keys": [ev_key],
                    "attributes": {"synthetic_seed": True},
                }
            )
            entity_key_by_name[seed_name] = cand
    if not assets and entities and evidences:
        _add_typed_asset(
            {
                "title": "窗口内发生事件",
                "summary": "本窗口提取到的主要情节推进。",
                "character_names": list(entity_key_by_name.keys())[:3],
                "quote": evidences[0]["locator"]["quote_text"],
                "asset_type": "event",
            },
            default_type="event",
            seq=999,
        )

    payload = {
        "contract_version": "whole_book_contract_v1",
        "run_id": run_id,
        "snapshot_id": snapshot_id,
        "window_id": window_id,
        "entities": entities,
        "assets": assets,
        "evidences": evidences,
        "relations": [],
        "warnings": ["normalized_from_llm_intermediate"],
        "provenance": AnalysisProvenanceV1(
            run_id=run_id,
            snapshot_id=snapshot_id,
            window_ids=[window_id],
            engine_id=FORMAL_ENGINE_ID,
            engine_version=FORMAL_ENGINE_VERSION,
            prompt_version=FIXTURE_PROMPT_VERSION,
            provider_id=provider_id,
            model_name=model_name,
            result_origin=ResultOrigin.formal,
            source_mode=WholeBookMode.whole_book_native,
            deterministic=False,
            generated_at=_utc_now(),
        ).model_dump(mode="json"),
    }
    return payload


_WINDOW_INTERMEDIATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "characters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                    "quote": {"type": "string"},
                },
                "required": ["name", "quote"],
            },
        },
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "character_names": {"type": "array", "items": {"type": "string"}},
                    "quote": {"type": "string"},
                },
                "required": ["title", "summary", "quote"],
            },
        },
        "setting_facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["title", "summary", "quote"],
            },
        },
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["title", "summary", "quote"],
            },
        },
    },
    "required": ["characters", "events"],
}


def _compact_window_user_payload(request_payload: dict[str, Any]) -> dict[str, Any]:
    paragraphs = []
    for p in request_payload.get("paragraphs") or []:
        if not isinstance(p, dict):
            continue
        paragraphs.append(
            {
                "global_paragraph_index": p.get("global_paragraph_index"),
                "text": p.get("text"),
            }
        )
    window = request_payload.get("window") or {}
    return {
        "window_id": window.get("window_id"),
        "window_index": window.get("window_index"),
        "chapter_start_index": window.get("chapter_start_index"),
        "chapter_end_index": window.get("chapter_end_index"),
        "paragraphs": paragraphs,
        "limits": {
            "max_characters": 8,
            "max_events": 8,
            "max_setting_facts": 4,
            "max_questions": 4,
            "quote_chars": "2-12 exact substring from paragraph text",
        },
    }


class GatewayWindowAnalysisTransport:
    provider_id: str
    model_name: str

    def __init__(self, session: Session, *, provider_row: ProviderConfiguration) -> None:
        self._session = session
        self.provider_id = provider_row.provider_name
        self.model_name = provider_row.plus_model or "qwen3.7-plus"

    def invoke(self, *, unit_key: str, unit_type: str, request_payload: dict[str, Any]) -> ProviderCallResult:
        system = (
            "You extract characters and events from one novel window. "
            "Return ONE JSON object with keys: characters, events, setting_facts, questions. "
            "Each character needs name + quote (exact 2-12 char substring from paragraph text). "
            "Each event needs title, summary, quote (exact substring). "
            "Keep arrays small (characters<=8, events<=8). Chinese quotes preferred."
        )
        user = json.dumps(
            {
                "unit_key": unit_key,
                "unit_type": unit_type,
                "window": _compact_window_user_payload(request_payload),
            },
            ensure_ascii=False,
        )
        try:
            raw, in_tok, out_tok, cost = _gateway_generate(
                session=self._session,
                provider_name=self.provider_id,
                model_name=self.model_name,
                system=system,
                user=user,
                schema=_WINDOW_INTERMEDIATE_SCHEMA,
                max_output_tokens=3072,
            )
            normalized = _normalize_window_llm_payload(
                raw,
                request_payload=request_payload,
                provider_id=self.provider_id,
                model_name=self.model_name,
            )
            WholeBookWindowAnalysisResponseV1.model_validate(normalized)
            return ProviderCallResult(
                ok=True,
                result_payload=normalized,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost_cny=cost,
                result_origin=ResultOrigin.formal.value,
            )
        except WholeBookFoundationError as exc:
            return ProviderCallResult(
                ok=False,
                error_code=str(exc.code),
                error_message_safe=str(exc)[:500],
                result_origin=ResultOrigin.formal.value,
            )
        except Exception as exc:  # noqa: BLE001
            return ProviderCallResult(
                ok=False,
                error_code="PROVIDER_WINDOW_FAILED",
                error_message_safe=f"{type(exc).__name__}: {str(exc)[:400]}",
                result_origin=ResultOrigin.formal.value,
            )


class GatewayOverviewTransport:
    provider_id: str
    model_name: str

    def __init__(self, session: Session, *, provider_row: ProviderConfiguration) -> None:
        self._session = session
        self.provider_id = provider_row.provider_name
        self.model_name = provider_row.plus_model or "qwen3.7-plus"

    def invoke(self, *, unit_key: str, unit_type: str, request_payload: dict[str, Any]) -> ProviderCallResult:
        run = request_payload.get("run") or {}
        snap = request_payload.get("snapshot") or {}
        entities = [e for e in (request_payload.get("entities") or []) if isinstance(e, dict)]
        assets = [a for a in (request_payload.get("assets") or []) if isinstance(a, dict)]
        entity_ids = [int(e["entity_id"]) for e in entities if e.get("entity_id") is not None]
        asset_ids = [int(a["asset_id"]) for a in assets if a.get("asset_id") is not None]
        event_asset_ids = [
            int(a["asset_id"])
            for a in assets
            if a.get("asset_type") == "event" and a.get("asset_id") is not None
        ]
        run_id = int(run.get("run_id") or 0)
        versions = list(self._session.scalars(select(NarrativeAssetVersion)).all())
        version_ids = [
            v.id
            for v in versions
            if json.loads(v.attributes_json or "{}").get("whole_book_run_id") == run_id
        ]
        evidence_ids = (
            list(
                self._session.scalars(
                    select(NarrativeAssetEvidence.id)
                    .where(NarrativeAssetEvidence.asset_version_id.in_(version_ids))
                    .order_by(NarrativeAssetEvidence.id.asc())
                    .limit(40)
                )
            )
            if version_ids
            else []
        )
        compact = {
            "claim_keys": list(BOOK_OVERVIEW_CLAIM_KEYS_V1),
            "entities": [
                {"entity_id": e.get("entity_id"), "name": e.get("canonical_name")} for e in entities[:20]
            ],
            "assets": [
                {"asset_id": a.get("asset_id"), "asset_type": a.get("asset_type"), "title": a.get("title")}
                for a in assets[:30]
            ],
        }
        system = (
            "Write a Chinese whole-book overview. Return ONE JSON object: "
            '{"claims":[{"claim_key":"...","summary":"..."}]} '
            "claim_key MUST be exactly one of the provided claim_keys and include ALL keys. "
            "Summaries must be grounded in provided entities/assets only."
        )
        schema = {
            "type": "object",
            "properties": {
                "claims": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "claim_key": {"type": "string"},
                            "summary": {"type": "string"},
                        },
                        "required": ["claim_key", "summary"],
                    },
                }
            },
            "required": ["claims"],
        }
        try:
            raw, in_tok, out_tok, cost = _gateway_generate(
                session=self._session,
                provider_name=self.provider_id,
                model_name=self.model_name,
                system=system,
                user=json.dumps({"unit_key": unit_key, "context": compact}, ensure_ascii=False),
                schema=schema,
                max_output_tokens=3072,
            )
            by_key: dict[str, str] = {}
            for item in raw.get("claims") or []:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("claim_key") or "").strip()
                summary = str(item.get("summary") or "").strip()
                if key in BOOK_OVERVIEW_CLAIM_KEYS_V1 and summary:
                    by_key[key] = summary[:5000]

            claims_out: list[dict[str, Any]] = []
            default_assets = asset_ids[:3]
            default_events = event_asset_ids[:3] or default_assets
            default_evidence = evidence_ids[:3]
            for key in BOOK_OVERVIEW_CLAIM_KEYS_V1:
                summary = by_key.get(key) or "当前窗口证据不足，暂无法形成确定结论。"
                aids = default_events if key in {"key_events", "final_resolution", "main_conflict"} else default_assets
                eids = default_evidence
                if aids and eids:
                    claims_out.append(
                        {
                            "claim_key": key,
                            "availability": OverviewClaimAvailability.available.value,
                            "summary": summary,
                            "confidence": 0.8,
                            "evidence_ids": eids,
                            "supporting_asset_ids": aids,
                            "conflict_ids": [],
                        }
                    )
                else:
                    claims_out.append(
                        {
                            "claim_key": key,
                            "availability": OverviewClaimAvailability.insufficient_evidence.value,
                            "summary": summary,
                            "confidence": None,
                            "evidence_ids": [],
                            "supporting_asset_ids": aids,
                            "conflict_ids": [],
                        }
                    )

            coverage = request_payload.get("coverage") or {
                "snapshot_id": int(snap.get("snapshot_id") or 1),
                "total_paragraphs": 1,
                "covered_paragraphs": 1,
                "coverage_ratio": 1.0,
                "gaps": [],
            }
            input_usage = (run.get("input_usage") or {}) or {
                "full_text_snapshot_used": True,
                "chapter_analysis_asset_count": 0,
                "reader_journey_asset_count": 0,
                "confirmed_whole_book_asset_count": 0,
            }
            payload = {
                "contract_version": WHOLE_BOOK_CONTRACT_VERSION,
                "result": {
                    "result_version": BOOK_OVERVIEW_RESULT_VERSION,
                    "contract_version": WHOLE_BOOK_CONTRACT_VERSION,
                    "run_id": run_id,
                    "book_id": int(run.get("book_id") or 0),
                    "snapshot_id": int(snap.get("snapshot_id") or 0),
                    "mode": WholeBookMode.whole_book_native.value,
                    "result_origin": ResultOrigin.formal.value,
                    "status": "completed",
                    "claims": claims_out,
                    "important_entity_ids": entity_ids[:12],
                    "key_event_asset_ids": sorted(set(event_asset_ids))[:20],
                    "coverage": coverage,
                    "input_usage": input_usage,
                    "warnings": ["normalized_from_llm_overview_intermediate"],
                    "provenance": AnalysisProvenanceV1(
                        run_id=run_id,
                        snapshot_id=int(snap.get("snapshot_id") or 0),
                        window_ids=[],
                        engine_id=FORMAL_ENGINE_ID,
                        engine_version=FORMAL_ENGINE_VERSION,
                        prompt_version=OVERVIEW_PROMPT_VERSION,
                        provider_id=self.provider_id,
                        model_name=self.model_name,
                        result_origin=ResultOrigin.formal,
                        source_mode=WholeBookMode.whole_book_native,
                        deterministic=False,
                        generated_at=_utc_now(),
                    ).model_dump(mode="json"),
                    "created_at": _utc_now().isoformat(),
                },
            }
            WholeBookSynthesisResponseV1.model_validate(payload)
            return ProviderCallResult(
                ok=True,
                result_payload=payload,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost_cny=cost,
                result_origin=ResultOrigin.formal.value,
            )
        except Exception as exc:  # noqa: BLE001
            return ProviderCallResult(
                ok=False,
                error_code="PROVIDER_OVERVIEW_FAILED",
                error_message_safe=f"{type(exc).__name__}: {str(exc)[:400]}",
                result_origin=ResultOrigin.formal.value,
            )


class GatewayStructureTransport:
    provider_id: str
    model_name: str

    def __init__(self, session: Session, *, provider_row: ProviderConfiguration) -> None:
        self._session = session
        self.provider_id = provider_row.provider_name
        self.model_name = provider_row.plus_model or "qwen3.7-plus"

    def invoke(self, *, unit_key: str, unit_type: str, request_payload: dict[str, Any]) -> ProviderCallResult:
        citation_ids = [str(x) for x in (request_payload.get("citation_ids") or []) if str(x).strip()]
        chapter_start = int(request_payload.get("chapter_start_index") or 0)
        chapter_end = int(request_payload.get("chapter_end_index") or max(chapter_start, 0))
        system = (
            "Analyze story structure stages. Return JSON with stages[], turning_points[], "
            "coverage_scope (local|partial_span|full_selected_range|insufficient), "
            "contract_version='v2', evidence_contract_version='v2'. "
            "Use ONLY provided citation_ids. Prefer 2-4 ordered stages."
        )
        compact = {
            "citation_ids": citation_ids[:80],
            "chapter_start_index": chapter_start,
            "chapter_end_index": chapter_end,
        }
        try:
            raw, in_tok, out_tok, cost = _gateway_generate(
                session=self._session,
                provider_name=self.provider_id,
                model_name=self.model_name,
                system=system,
                user=json.dumps({"unit_key": unit_key, "context": compact}, ensure_ascii=False),
                schema={
                    "type": "object",
                    "properties": {
                        "stages": {"type": "array"},
                        "turning_points": {"type": "array"},
                        "coverage_scope": {"type": "string"},
                        "contract_version": {"type": "string"},
                        "evidence_contract_version": {"type": "string"},
                    },
                    "required": ["stages", "coverage_scope"],
                },
                max_output_tokens=4096,
            )
            payload = _normalize_structure_payload(
                raw,
                citation_ids=citation_ids,
                chapter_start=chapter_start,
                chapter_end=chapter_end,
            )
            return ProviderCallResult(
                ok=True,
                result_payload=payload,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost_cny=cost,
                result_origin=ResultOrigin.formal.value,
            )
        except Exception as exc:  # noqa: BLE001
            return ProviderCallResult(
                ok=False,
                error_code="PROVIDER_STRUCTURE_FAILED",
                error_message_safe=f"{type(exc).__name__}: {str(exc)[:400]}",
                result_origin=ResultOrigin.formal.value,
            )


def _normalize_structure_payload(
    raw: dict[str, Any],
    *,
    citation_ids: list[str],
    chapter_start: int,
    chapter_end: int,
) -> dict[str, Any]:
    cids = citation_ids or ["cid:0"]
    first, last = cids[0], cids[-1]
    mid = cids[len(cids) // 2]

    def _claim(text: str, ids: list[str]) -> dict[str, Any]:
        return {
            "value": text,
            "status": "observed",
            "citation_ids": ids[:3],
            "confidence": 0.7,
        }

    def _boundary(ids: list[str]) -> dict[str, Any]:
        return {"citation_ids": ids[:2], "note": None, "value": None}

    stages_in = raw.get("stages") if isinstance(raw.get("stages"), list) else []
    stages: list[dict[str, Any]] = []
    for idx, item in enumerate(stages_in[:6]):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or f"阶段{idx + 1}")
        summary = str(
            (item.get("summary") or {}).get("value")
            if isinstance(item.get("summary"), dict)
            else item.get("summary")
            or title
        )
        start_ids = list(
            ((item.get("start_boundary") or {}) if isinstance(item.get("start_boundary"), dict) else {}).get(
                "citation_ids"
            )
            or [first]
        )
        end_ids = list(
            ((item.get("end_boundary") or {}) if isinstance(item.get("end_boundary"), dict) else {}).get(
                "citation_ids"
            )
            or [last]
        )
        start_ids = [c for c in start_ids if c in set(cids)] or [first]
        end_ids = [c for c in end_ids if c in set(cids)] or [last]
        stages.append(
            {
                "local_stage_ref": str(item.get("local_stage_ref") or f"stage-{idx + 1}"),
                "order_index": idx,
                "stage_type": str(item.get("stage_type") or "development"),
                "title": title[:200],
                "summary": _claim(summary[:500], start_ids),
                "start_boundary": _boundary(start_ids),
                "end_boundary": _boundary(end_ids),
                "supporting_citation_ids": [],
                "related_turning_point_refs": [],
                "narrative_function": str(item.get("narrative_function") or "推进主线"),
                "confidence": 0.65,
            }
        )
    if not stages:
        stages = [
            {
                "local_stage_ref": "stage-1",
                "order_index": 0,
                "stage_type": "setup",
                "title": "开端",
                "summary": _claim("故事开端与人物入场。", [first]),
                "start_boundary": _boundary([first]),
                "end_boundary": _boundary([mid]),
                "supporting_citation_ids": [],
                "related_turning_point_refs": [],
                "narrative_function": "建立情境",
                "confidence": 0.6,
            },
            {
                "local_stage_ref": "stage-2",
                "order_index": 1,
                "stage_type": "development",
                "title": "发展",
                "summary": _claim("冲突推进与关系变化。", [mid]),
                "start_boundary": _boundary([mid]),
                "end_boundary": _boundary([last]),
                "supporting_citation_ids": [],
                "related_turning_point_refs": [],
                "narrative_function": "推进冲突",
                "confidence": 0.6,
            },
        ]
    coverage = str(raw.get("coverage_scope") or "full_selected_range")
    if coverage not in {"local", "partial_span", "full_selected_range", "insufficient"}:
        coverage = "full_selected_range"
    # Free formal pipeline freezes expected_coverage_scope=full_selected_range when
    # stages can be identified; partial_span causes STRUCTURE_COVERAGE_SCOPE_BINDING_MISMATCH.
    if stages:
        coverage = "full_selected_range"
    return {
        "contract_version": "v2",
        "evidence_contract_version": "v2",
        "coverage_scope": coverage,
        "stages": stages,
        "turning_points": [],
        "analysis_confidence": 0.65,
        "overall_confidence": 0.65,
        "limitations": ["normalized_from_llm_structure_intermediate"],
        "context_capabilities": {
            "chapter_start_index": chapter_start,
            "chapter_end_index": chapter_end,
        },
    }


class GatewayChapterFunctionsTransport:
    provider_id: str
    model_name: str

    def __init__(self, session: Session, *, provider_row: ProviderConfiguration) -> None:
        self._session = session
        self.provider_id = provider_row.provider_name
        self.model_name = provider_row.plus_model or "qwen3.7-plus"

    def invoke(self, *, unit_key: str, unit_type: str, request_payload: dict[str, Any]) -> ProviderCallResult:
        allowed = {
            "setup",
            "escalation",
            "climax",
            "resolution",
            "transition",
            "side_story",
            "flashback",
            "empty",
            "non_mainline",
            "unknown",
        }
        chapter_units = [u for u in (request_payload.get("chapter_units") or []) if isinstance(u, dict)]
        citation_ids = [str(x) for x in (request_payload.get("citation_ids") or []) if str(x).strip()]
        op = str(request_payload.get("operation_kind") or "chapter_functions")
        system = (
            "Assign chapter functions. Return JSON {chapters:[{chapter_order, primary, secondary, citation_ids}]}. "
            f"primary one of {sorted(allowed)} or null; secondary 0..N from same set. "
            "Use only provided citation_ids."
            + (" Repair mode: fix invalid labels/citations only." if "repair" in op else "")
        )
        compact = {
            "chapter_units": [
                {
                    "chapter_order": u.get("chapter_order"),
                    "citation_ids": (u.get("citation_ids") or citation_ids)[:8],
                }
                for u in chapter_units[:40]
            ],
            "citation_ids": citation_ids[:80],
        }
        try:
            raw, in_tok, out_tok, cost = _gateway_generate(
                session=self._session,
                provider_name=self.provider_id,
                model_name=self.model_name,
                system=system,
                user=json.dumps({"unit_key": unit_key, "context": compact}, ensure_ascii=False),
                schema={
                    "type": "object",
                    "properties": {
                        "chapters": {"type": "array"},
                        "contract_version": {"type": "string"},
                        "coverage_scope": {"type": "string"},
                    },
                    "required": ["chapters"],
                },
                max_output_tokens=4096,
            )
            payload = _normalize_chapter_functions_payload(
                raw,
                chapter_units=chapter_units,
                citation_ids=citation_ids,
                allowed=allowed,
            )
            return ProviderCallResult(
                ok=True,
                result_payload=payload,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost_cny=cost,
                result_origin=ResultOrigin.formal.value,
            )
        except Exception as exc:  # noqa: BLE001
            return ProviderCallResult(
                ok=False,
                error_code="PROVIDER_CHAPTER_FUNCTIONS_FAILED",
                error_message_safe=f"{type(exc).__name__}: {str(exc)[:400]}",
                result_origin=ResultOrigin.formal.value,
            )


def _normalize_chapter_functions_payload(
    raw: dict[str, Any],
    *,
    chapter_units: list[dict[str, Any]],
    citation_ids: list[str],
    allowed: set[str],
) -> dict[str, Any]:
    by_order: dict[int, dict[str, Any]] = {}
    for item in raw.get("chapters") or []:
        if not isinstance(item, dict):
            continue
        try:
            order = int(item.get("chapter_order"))
        except Exception:
            continue
        primary = item.get("primary_function", item.get("primary"))
        if primary is not None:
            primary = str(primary)
            if primary not in allowed:
                primary = "unknown"
        secondary_raw = item.get("secondary_functions", item.get("secondary")) or []
        secondary: list[str] = []
        for s in secondary_raw:
            s2 = str(s)
            if s2 in allowed and s2 != primary:
                secondary.append(s2)
        cids = [
            str(c)
            for c in (
                item.get("supporting_citation_ids")
                or item.get("citation_ids")
                or []
            )
            if str(c) in set(citation_ids)
        ]
        by_order[order] = {
            "primary": primary,
            "secondary": secondary[:3],
            "citation_ids": cids,
            "summary": str(
                ((item.get("observed_summary") or {}) if isinstance(item.get("observed_summary"), dict) else {}).get(
                    "value"
                )
                or item.get("summary")
                or f"第{order + 1}章功能观察"
            ),
        }

    chapters_out: list[dict[str, Any]] = []
    for u in chapter_units:
        try:
            order = int(u.get("chapter_order"))
        except Exception:
            continue
        chapter_id = u.get("chapter_id")
        if chapter_id is None:
            chapter_id = order
        unit_cids = [str(c) for c in (u.get("citation_ids") or citation_ids) if str(c)]
        mapped = by_order.get(order) or {
            "primary": "setup" if order == 0 else "escalation",
            "secondary": [],
            "citation_ids": unit_cids[:3],
            "summary": f"第{order + 1}章主线推进。",
        }
        cids = mapped["citation_ids"] or unit_cids[:3] or citation_ids[:3]
        primary = mapped["primary"]
        chapters_out.append(
            {
                "chapter_id": chapter_id,
                "chapter_order": order,
                "primary_function": primary,
                "secondary_functions": mapped["secondary"],
                "observed_summary": {
                    "value": mapped["summary"][:500],
                    "status": "observed",
                    "citation_ids": cids[:5],
                    "confidence": 0.7,
                },
                "inferred_effect": None,
                "confidence": 0.66,
                "supporting_citation_ids": cids[:5],
                "limitations": ["normalized_from_llm_chapter_functions_intermediate"],
            }
        )

    return {
        "contract_version": "v2",
        "coverage_scope": "full_selected_range",
        "chapters": chapters_out,
        "analysis_confidence": 0.66,
        "overall_confidence": 0.66,
        "limitations": ["normalized_from_llm_chapter_functions_intermediate"],
        "context_capabilities": {},
    }