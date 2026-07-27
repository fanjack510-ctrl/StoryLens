"""Candidate output-ref registry and provider alias resolution (CHG-055).

Provider DTO aliases such as ``book_overview.claim`` are never treated as
unconditional canonical refs. Formal refs such as
``structure_stages.stage.{key}.boundary.start`` resolve via ``extra_refs`` once
registered by the V2 mapper.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping, Sequence


class OutputRefResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    UNKNOWN = "UNKNOWN"
    AMBIGUOUS = "AMBIGUOUS"
    MODULE_MISMATCH = "MODULE_MISMATCH"
    CANDIDATE_MISSING = "CANDIDATE_MISSING"


@dataclass(frozen=True, slots=True)
class OutputRefResolution:
    provider_output_ref: str
    canonical_output_ref: str | None
    module_key: str
    candidate_key: str | None
    claim_key: str | None
    resolution_status: str
    resolution_code: str
    candidate_match_count: int

    def to_safe_dict(self) -> dict[str, Any]:
        return asdict(self)


def module_primary_output_ref(module_key: str) -> str:
    return f"{str(module_key).strip()}.out"


def module_claim_alias_ref(module_key: str) -> str:
    return f"{str(module_key).strip()}.claim"


def candidate_canonical_ref(module_key: str, candidate_key: str) -> str:
    """Stable, recomputable canonical ref (no DB id / UUID / book text)."""

    mk = str(module_key).strip()
    ck = str(candidate_key).strip()
    return f"module:{mk}:candidate:{ck}"


def claim_canonical_ref(module_key: str, claim_key: str) -> str:
    mk = str(module_key).strip()
    ck = str(claim_key).strip()
    return f"module:{mk}:claim:{ck}"


def _asset_output_ref(asset: Mapping[str, Any]) -> str | None:
    raw = asset.get("output_ref") or asset.get("stable_label")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _asset_candidate_key(asset: Mapping[str, Any], *, index: int) -> str:
    for key in ("candidate_key", "claim_key", "asset_key", "stable_key"):
        value = asset.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    ref = _asset_output_ref(asset)
    if ref:
        # Prefer trailing semantic token: book_overview.out → out
        if "." in ref:
            return ref.rsplit(".", 1)[-1]
        return ref
    asset_type = str(asset.get("asset_type") or "asset").strip() or "asset"
    return f"{asset_type}:{index}"


def build_candidate_output_refs(
    *,
    module_key: str,
    asset_candidates: Sequence[Any],
    extra_refs: Sequence[str] = (),
) -> tuple[str, ...]:
    """Build the Candidate Output Ref Registry for one module result."""

    mk = str(module_key).strip()
    refs: list[str] = []
    seen: set[str] = set()

    def _add(ref: str | None) -> None:
        if not ref:
            return
        token = str(ref).strip()
        if not token or token in seen:
            return
        seen.add(token)
        refs.append(token)

    _add(module_primary_output_ref(mk))
    for index, asset in enumerate(asset_candidates or ()):
        if not isinstance(asset, Mapping):
            continue
        out_ref = _asset_output_ref(asset)
        _add(out_ref)
        candidate_key = _asset_candidate_key(asset, index=index)
        _add(candidate_canonical_ref(mk, candidate_key))
        claim_key = asset.get("claim_key")
        if claim_key is not None and str(claim_key).strip():
            _add(claim_canonical_ref(mk, str(claim_key).strip()))
            # Semantic claim aliases used by DTO evidence targets.
            _add(f"{mk}.{str(claim_key).strip()}")

    for extra in extra_refs or ():
        _add(str(extra))
    return tuple(refs)


def resolve_provider_output_ref(
    provider_output_ref: str,
    *,
    module_key: str,
    registered_refs: Sequence[str],
    asset_candidates: Sequence[Any] = (),
    claim_key: str | None = None,
    claim_index: int | None = None,
    expected_module_key: str | None = None,
) -> OutputRefResolution:
    """Resolve a Provider DTO target ref to a registered canonical ref.

    Never defaults to ``candidates[0]``. ``{module}.claim`` is an input alias
    only — it resolves to ``{module}.out`` when that primary ref is registered,
    or to a uniquely matching claim/candidate when claim_key/index is provided.
    """

    mk = str(module_key).strip()
    provider = str(provider_output_ref or "").strip()
    registry = tuple(str(x).strip() for x in registered_refs if str(x).strip())
    registry_set = set(registry)
    expected = str(expected_module_key or mk).strip()

    if expected and mk and expected != mk:
        return OutputRefResolution(
            provider_output_ref=provider,
            canonical_output_ref=None,
            module_key=mk,
            candidate_key=None,
            claim_key=claim_key,
            resolution_status=OutputRefResolutionStatus.MODULE_MISMATCH.value,
            resolution_code="TARGET_MODULE_MISMATCH",
            candidate_match_count=0,
        )

    if not provider:
        return OutputRefResolution(
            provider_output_ref=provider,
            canonical_output_ref=None,
            module_key=mk,
            candidate_key=None,
            claim_key=claim_key,
            resolution_status=OutputRefResolutionStatus.UNKNOWN.value,
            resolution_code="TARGET_OUTPUT_REF_UNKNOWN",
            candidate_match_count=0,
        )

    # Exact registry hit — already canonical.
    if provider in registry_set:
        return OutputRefResolution(
            provider_output_ref=provider,
            canonical_output_ref=provider,
            module_key=mk,
            candidate_key=_candidate_key_for_ref(provider, mk=mk, assets=asset_candidates),
            claim_key=claim_key,
            resolution_status=OutputRefResolutionStatus.RESOLVED.value,
            resolution_code="TARGET_OUTPUT_REF_EXACT",
            candidate_match_count=1,
        )

    # Cross-module provider ref.
    if "." in provider:
        prefix = provider.split(".", 1)[0]
        if prefix and prefix != mk and not provider.startswith(f"module:{mk}:"):
            return OutputRefResolution(
                provider_output_ref=provider,
                canonical_output_ref=None,
                module_key=mk,
                candidate_key=None,
                claim_key=claim_key,
                resolution_status=OutputRefResolutionStatus.MODULE_MISMATCH.value,
                resolution_code="TARGET_MODULE_MISMATCH",
                candidate_match_count=0,
            )

    claim = str(claim_key).strip() if claim_key is not None else ""
    assets = [a for a in (asset_candidates or ()) if isinstance(a, Mapping)]

    # Claim-key / claim-index precise match.
    if claim:
        matches = _match_assets_by_claim(assets, mk=mk, claim_key=claim)
        return _from_matches(
            provider=provider,
            mk=mk,
            claim_key=claim,
            matches=matches,
            registry_set=registry_set,
        )
    if claim_index is not None:
        matches = _match_assets_by_index(assets, mk=mk, claim_index=int(claim_index))
        return _from_matches(
            provider=provider,
            mk=mk,
            claim_key=claim or None,
            matches=matches,
            registry_set=registry_set,
        )

    # Module-level DTO alias: ``{module}.claim``
    if provider == module_claim_alias_ref(mk) or provider.endswith(".claim"):
        primary = module_primary_output_ref(mk)
        if primary in registry_set:
            return OutputRefResolution(
                provider_output_ref=provider,
                canonical_output_ref=primary,
                module_key=mk,
                candidate_key="out",
                claim_key=claim or "logline",
                resolution_status=OutputRefResolutionStatus.RESOLVED.value,
                resolution_code="TARGET_OUTPUT_REF_PRIMARY_ALIAS",
                candidate_match_count=1,
            )
        # No primary .out — unique candidate only.
        asset_refs = [r for r in (_asset_output_ref(a) for a in assets) if r]
        unique_refs = sorted(set(asset_refs))
        if len(unique_refs) == 0:
            return OutputRefResolution(
                provider_output_ref=provider,
                canonical_output_ref=None,
                module_key=mk,
                candidate_key=None,
                claim_key=claim or None,
                resolution_status=OutputRefResolutionStatus.CANDIDATE_MISSING.value,
                resolution_code="TARGET_OUTPUT_REF_CANDIDATE_MISSING",
                candidate_match_count=0,
            )
        if len(unique_refs) == 1 and unique_refs[0] in registry_set:
            return OutputRefResolution(
                provider_output_ref=provider,
                canonical_output_ref=unique_refs[0],
                module_key=mk,
                candidate_key=_candidate_key_for_ref(unique_refs[0], mk=mk, assets=assets),
                claim_key=claim or None,
                resolution_status=OutputRefResolutionStatus.RESOLVED.value,
                resolution_code="TARGET_OUTPUT_REF_UNIQUE_CANDIDATE",
                candidate_match_count=1,
            )
        return OutputRefResolution(
            provider_output_ref=provider,
            canonical_output_ref=None,
            module_key=mk,
            candidate_key=None,
            claim_key=claim or None,
            resolution_status=OutputRefResolutionStatus.AMBIGUOUS.value,
            resolution_code="TARGET_OUTPUT_REF_AMBIGUOUS",
            candidate_match_count=len(unique_refs),
        )

    return OutputRefResolution(
        provider_output_ref=provider,
        canonical_output_ref=None,
        module_key=mk,
        candidate_key=None,
        claim_key=claim or None,
        resolution_status=OutputRefResolutionStatus.UNKNOWN.value,
        resolution_code="TARGET_OUTPUT_REF_UNKNOWN",
        candidate_match_count=0,
    )


def canonicalize_evidence_target_ref(
    evidence: Mapping[str, Any] | Any,
    *,
    module_key: str,
    registered_refs: Sequence[str],
    asset_candidates: Sequence[Any] = (),
) -> OutputRefResolution:
    """Canonicalize one evidence target using the Candidate Output Ref Registry."""

    if isinstance(evidence, Mapping):
        provider = str(
            evidence.get("provider_output_ref")
            or evidence.get("target_output_ref")
            or evidence.get("output_ref")
            or evidence.get("target")
            or ""
        )
        claim_key = evidence.get("claim_key") or evidence.get("claim_id")
        claim_index = evidence.get("claim_index")
        target_module = evidence.get("target_module_key") or module_key
    else:
        provider = str(
            getattr(evidence, "provider_output_ref", None)
            or getattr(evidence, "target_output_ref", None)
            or ""
        )
        claim_key = getattr(evidence, "claim_key", None)
        claim_index = getattr(evidence, "claim_index", None)
        target_module = getattr(evidence, "target_module_key", module_key)

    return resolve_provider_output_ref(
        provider,
        module_key=str(target_module or module_key),
        registered_refs=registered_refs,
        asset_candidates=asset_candidates,
        claim_key=str(claim_key) if claim_key is not None else None,
        claim_index=int(claim_index) if claim_index is not None else None,
        expected_module_key=str(module_key),
    )


def _match_assets_by_claim(
    assets: Sequence[Mapping[str, Any]], *, mk: str, claim_key: str
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for index, asset in enumerate(assets):
        keys = {
            str(asset.get("claim_key") or "").strip(),
            str(asset.get("candidate_key") or "").strip(),
            _asset_candidate_key(asset, index=index),
        }
        ref = _asset_output_ref(asset)
        if ref and "." in ref:
            keys.add(ref.rsplit(".", 1)[-1])
        if claim_key in keys or f"{mk}.{claim_key}" == ref:
            if ref:
                out.append((ref, claim_key))
    return out


def _match_assets_by_index(
    assets: Sequence[Mapping[str, Any]], *, mk: str, claim_index: int
) -> list[tuple[str, str]]:
    _ = mk
    if claim_index < 0 or claim_index >= len(assets):
        return []
    asset = assets[claim_index]
    ref = _asset_output_ref(asset)
    if not ref:
        return []
    return [(ref, _asset_candidate_key(asset, index=claim_index))]


def _from_matches(
    *,
    provider: str,
    mk: str,
    claim_key: str | None,
    matches: Sequence[tuple[str, str]],
    registry_set: set[str],
) -> OutputRefResolution:
    if not matches:
        return OutputRefResolution(
            provider_output_ref=provider,
            canonical_output_ref=None,
            module_key=mk,
            candidate_key=None,
            claim_key=claim_key,
            resolution_status=OutputRefResolutionStatus.CANDIDATE_MISSING.value,
            resolution_code="TARGET_OUTPUT_REF_CANDIDATE_MISSING",
            candidate_match_count=0,
        )
    unique = sorted({m[0] for m in matches if m[0] in registry_set})
    if len(unique) == 1:
        return OutputRefResolution(
            provider_output_ref=provider,
            canonical_output_ref=unique[0],
            module_key=mk,
            candidate_key=matches[0][1],
            claim_key=claim_key,
            resolution_status=OutputRefResolutionStatus.RESOLVED.value,
            resolution_code="TARGET_OUTPUT_REF_CLAIM_MATCH",
            candidate_match_count=1,
        )
    if len(unique) == 0:
        return OutputRefResolution(
            provider_output_ref=provider,
            canonical_output_ref=None,
            module_key=mk,
            candidate_key=None,
            claim_key=claim_key,
            resolution_status=OutputRefResolutionStatus.CANDIDATE_MISSING.value,
            resolution_code="TARGET_OUTPUT_REF_CANDIDATE_MISSING",
            candidate_match_count=0,
        )
    return OutputRefResolution(
        provider_output_ref=provider,
        canonical_output_ref=None,
        module_key=mk,
        candidate_key=None,
        claim_key=claim_key,
        resolution_status=OutputRefResolutionStatus.AMBIGUOUS.value,
        resolution_code="TARGET_OUTPUT_REF_AMBIGUOUS",
        candidate_match_count=len(unique),
    )


def _candidate_key_for_ref(
    ref: str, *, mk: str, assets: Sequence[Any]
) -> str | None:
    for index, asset in enumerate(assets or ()):
        if not isinstance(asset, Mapping):
            continue
        if _asset_output_ref(asset) == ref:
            return _asset_candidate_key(asset, index=index)
    if ref == module_primary_output_ref(mk):
        return "out"
    if ref.startswith(f"module:{mk}:candidate:"):
        return ref.rsplit(":", 1)[-1]
    return None
