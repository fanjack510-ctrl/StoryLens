"""Fake Prompt Pack service layer (Phase 2B Agent R / CHG-039).

Refs + short non-production placeholders only. No formal analysis prompts.
Production loaders must reject Fake packs.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping

from app.narrative_core.enums import WholeBookModuleKey
from app.narrative_core.private_engine_contract.prompt_pack import (
    FakePromptPackBody,
    FakePromptPackManifest,
    PromptPackManifest,
    fake_prompt_pack_manifest as contract_fake_prompt_pack_manifest,
    prompt_hash_fingerprint_part,
)

FIRST_FOUR_MODULES: tuple[WholeBookModuleKey, ...] = (
    WholeBookModuleKey.BOOK_OVERVIEW,
    WholeBookModuleKey.STRUCTURE_STAGES,
    WholeBookModuleKey.CHAPTER_FUNCTIONS,
    WholeBookModuleKey.STORYLINES,
)

FAKE_INSTRUCTION_REFS: Mapping[str, str] = {
    "book_overview": "fake://book-overview/system",
    "structure_stages": "fake://structure-stages/system",
    "chapter_functions": "fake://chapter-functions/system",
    "storylines": "fake://storylines/system",
}

FAKE_RESPONSE_SCHEMA_REFS: Mapping[str, str] = {
    "book_overview": "dto://BookOverviewResultDto",
    "structure_stages": "dto://StructureStagesResultDto",
    "chapter_functions": "dto://ChapterFunctionsResultDto",
    "storylines": "dto://StorylinesResultDto",
}

FAKE_RESPONSE_SCHEMA_REFS_V2: Mapping[str, str] = {
    "structure_stages": "dto://StructureStagesResultV2",
}

SUPPORTED_LOCALES: tuple[str, ...] = ("zh-CN", "en-US")
SUPPORTED_SOURCE_LANGUAGES: tuple[str, ...] = ("zh", "en", "mixed", "auto", "unknown")


@dataclass(frozen=True, slots=True)
class FakePromptInstructionRefs:
    """Instruction refs only — never stores real analysis instructions."""

    by_module: Mapping[str, str] = field(default_factory=lambda: dict(FAKE_INSTRUCTION_REFS))

    def get(self, module_key: WholeBookModuleKey | str) -> str:
        key = module_key.value if isinstance(module_key, WholeBookModuleKey) else str(module_key)
        ref = self.by_module.get(key)
        if not ref:
            raise KeyError(f"no fake instruction ref for {key}")
        if not ref.startswith("fake://"):
            raise ValueError("fake instruction refs must use fake:// scheme")
        return ref


@dataclass(frozen=True, slots=True)
class FakeResponseSchemaRefs:
    by_module: Mapping[str, str] = field(default_factory=lambda: dict(FAKE_RESPONSE_SCHEMA_REFS))

    def get(self, module_key: WholeBookModuleKey | str) -> str:
        key = module_key.value if isinstance(module_key, WholeBookModuleKey) else str(module_key)
        ref = self.by_module.get(key)
        if not ref:
            raise KeyError(f"no fake response schema ref for {key}")
        return ref


def fake_response_schema_ref(
    module_key: WholeBookModuleKey | str,
    *,
    contract_version: str | None = None,
) -> str:
    """Resolve fake schema ref; V2 create paths may prefer StructureStagesResultV2."""

    key = module_key.value if isinstance(module_key, WholeBookModuleKey) else str(module_key)
    if str(contract_version or "").lower() == "v2":
        v2_ref = FAKE_RESPONSE_SCHEMA_REFS_V2.get(key)
        if v2_ref:
            return v2_ref
    return FakeResponseSchemaRefs().get(key)


def compute_fake_prompt_pack_hash(
    *,
    prompt_pack_id: str,
    prompt_pack_version: str,
    instruction_refs: Mapping[str, str],
    schema_refs: Mapping[str, str],
    locales: tuple[str, ...] = SUPPORTED_LOCALES,
) -> str:
    payload = {
        "prompt_pack_id": prompt_pack_id,
        "prompt_pack_version": prompt_pack_version,
        "instruction_refs": dict(sorted(instruction_refs.items())),
        "schema_refs": dict(sorted(schema_refs.items())),
        "locales": list(locales),
        "non_production": True,
        "formal": False,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_fake_prompt_pack_signature(
    package_hash: str,
    *,
    secret: bytes = b"storylens-fake-prompt-pack-test-only",
) -> str:
    """Deterministic test signature — not a production signing key."""

    return hmac.new(secret, package_hash.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass(frozen=True, slots=True)
class FakePromptPackServiceManifest:
    """Service-layer Fake pack with testable hash/signature and locale support."""

    contract: FakePromptPackManifest
    instruction_refs: FakePromptInstructionRefs
    response_schema_refs: FakeResponseSchemaRefs
    package_signature: str
    supported_locales: tuple[str, ...] = SUPPORTED_LOCALES
    supported_source_languages: tuple[str, ...] = SUPPORTED_SOURCE_LANGUAGES

    @property
    def manifest(self) -> PromptPackManifest:
        return self.contract.manifest

    @property
    def prompt_hash(self) -> str:
        return self.manifest.prompt_hash

    @property
    def package_hash(self) -> str:
        return self.manifest.package_hash

    def fingerprint_part(self) -> str:
        return prompt_hash_fingerprint_part(self.prompt_hash)

    def assert_compatible_with_first_four(self) -> None:
        supported = frozenset(self.manifest.supported_modules)
        missing = set(FIRST_FOUR_MODULES) - supported
        if missing:
            raise ValueError(f"fake pack missing modules: {sorted(m.value for m in missing)}")


def build_fake_prompt_pack(
    *,
    prompt_pack_id: str = "fake.prompt_pack.first_four",
    prompt_pack_version: str = "0.0.1-fake",
    created_at: datetime | None = None,
) -> FakePromptPackServiceManifest:
    instruction_refs = FakePromptInstructionRefs()
    schema_refs = FakeResponseSchemaRefs()
    package_hash = compute_fake_prompt_pack_hash(
        prompt_pack_id=prompt_pack_id,
        prompt_pack_version=prompt_pack_version,
        instruction_refs=instruction_refs.by_module,
        schema_refs=schema_refs.by_module,
    )
    prompt_hash = hashlib.sha256(
        f"{package_hash}:{prompt_pack_version}:fake-content".encode("utf-8")
    ).hexdigest()
    body = FakePromptPackBody(
        instruction_placeholder="[FAKE] non-production placeholder",
        template_placeholders={
            key: f"[FAKE] {key} template"
            for key in FAKE_INSTRUCTION_REFS
        },
    )
    manifest = PromptPackManifest(
        prompt_pack_id=prompt_pack_id,
        prompt_pack_version=prompt_pack_version,
        private=False,
        signed=False,
        package_hash=package_hash,
        supported_engine_versions=("0.0.1-fake",),
        supported_modules=FIRST_FOUR_MODULES,
        supported_languages=("zh", "en", "mixed"),
        output_schema_versions=("1.0.0",),
        instruction_ref="fake://instruction/first_four",
        template_refs=dict(FAKE_INSTRUCTION_REFS),
        example_set_refs=("fake://examples/synthetic_short",),
        evaluation_policy_ref="fake://evaluation/default",
        created_at=created_at or datetime(2026, 7, 23, 0, 0, 0),
        prompt_hash=prompt_hash,
        non_production=True,
    )
    contract = FakePromptPackManifest(manifest=manifest, body=body)
    signature = compute_fake_prompt_pack_signature(package_hash)
    service = FakePromptPackServiceManifest(
        contract=contract,
        instruction_refs=instruction_refs,
        response_schema_refs=schema_refs,
        package_signature=signature,
    )
    service.assert_compatible_with_first_four()
    return service


def reject_fake_prompt_pack_in_production(
    pack: FakePromptPackServiceManifest | FakePromptPackManifest | PromptPackManifest,
    *,
    production: bool,
) -> None:
    """Production environments must not load Fake packs."""

    if not production:
        return
    if isinstance(pack, FakePromptPackServiceManifest):
        non_production = pack.manifest.non_production
        pack_id = pack.manifest.prompt_pack_id
    elif isinstance(pack, FakePromptPackManifest):
        non_production = pack.manifest.non_production
        pack_id = pack.manifest.prompt_pack_id
    else:
        non_production = pack.non_production
        pack_id = pack.prompt_pack_id
    if non_production or pack_id.startswith("fake."):
        raise RuntimeError("production must not load Fake Prompt Pack")


def assert_no_formal_prompt_bodies(pack: FakePromptPackServiceManifest) -> None:
    """Guard: Fake pack must not carry formal analysis instruction text."""

    body = pack.contract.body
    banned_markers = (
        "分析主角",
        "identify the protagonist",
        "three-act structure",
        "三幕式",
        "formal analysis",
    )
    texts = [body.instruction_placeholder, *body.template_placeholders.values()]
    for text in texts:
        lowered = text.lower()
        for marker in banned_markers:
            if marker.lower() in lowered:
                raise ValueError(f"formal prompt marker forbidden in fake pack: {marker}")
        if len(text) > 200:
            raise ValueError("fake placeholder too long")


# Re-export contract factory for tests that need the Phase 2B-P shape.
fake_prompt_pack_manifest = contract_fake_prompt_pack_manifest

__all__ = [
    "FAKE_INSTRUCTION_REFS",
    "FAKE_RESPONSE_SCHEMA_REFS",
    "FAKE_RESPONSE_SCHEMA_REFS_V2",
    "FakePromptInstructionRefs",
    "FakePromptPackServiceManifest",
    "FakeResponseSchemaRefs",
    "SUPPORTED_LOCALES",
    "SUPPORTED_SOURCE_LANGUAGES",
    "assert_no_formal_prompt_bodies",
    "build_fake_prompt_pack",
    "compute_fake_prompt_pack_hash",
    "compute_fake_prompt_pack_signature",
    "fake_prompt_pack_manifest",
    "fake_response_schema_ref",
    "reject_fake_prompt_pack_in_production",
]
