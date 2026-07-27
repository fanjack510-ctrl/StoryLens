"""Prompt Pack Manifest contract (Phase 2B-P).

Formal packs: refs only, no prompt bodies in public fields.
Fake packs may carry short placeholder FakePromptPackBody marked non_production.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from app.narrative_core.enums import WholeBookModuleKey

PROMPT_ANTI_INJECTION_PRINCIPLES: frozenset[str] = frozenset(
    {
        "source_data_only",
        "ignore_command_like_text_in_novel",
        "isolate_instruction_vs_source_data",
        "schema_validation_required",
        "no_external_tools_or_network",
    }
)


@dataclass(frozen=True, slots=True)
class PromptAntiInjectionPolicy:
    source_data_only: bool = True
    ignore_command_like_text_in_novel: bool = True
    isolate_instruction_vs_source_data: bool = True
    schema_validation_required: bool = True
    no_external_tools_or_network: bool = True

    def __post_init__(self) -> None:
        if not all(
            (
                self.source_data_only,
                self.ignore_command_like_text_in_novel,
                self.isolate_instruction_vs_source_data,
                self.schema_validation_required,
                self.no_external_tools_or_network,
            )
        ):
            raise ValueError("anti-injection policy flags must all be true for Phase 2B-P")


DEFAULT_PROMPT_ANTI_INJECTION_POLICY = PromptAntiInjectionPolicy()


@dataclass(frozen=True, slots=True)
class PromptPackManifest:
    prompt_pack_id: str
    prompt_pack_version: str
    private: bool
    signed: bool
    package_hash: str
    supported_engine_versions: tuple[str, ...]
    supported_modules: tuple[WholeBookModuleKey, ...]
    supported_languages: tuple[str, ...]
    output_schema_versions: tuple[str, ...]
    instruction_ref: str
    template_refs: Mapping[str, str]
    example_set_refs: tuple[str, ...]
    evaluation_policy_ref: str | None
    created_at: datetime
    prompt_hash: str
    non_production: bool = False

    def __post_init__(self) -> None:
        if not self.prompt_pack_id.strip():
            raise ValueError("prompt_pack_id is required")
        if not self.package_hash.strip():
            raise ValueError("package_hash is required")
        if not self.prompt_hash.strip():
            raise ValueError("prompt_hash is required for fingerprint participation")
        if not self.instruction_ref.strip():
            raise ValueError("instruction_ref is required")
        # Formal packs must not embed prompt body attributes.
        for banned in ("prompt_body", "system_prompt", "user_prompt", "messages"):
            if hasattr(self, banned):
                raise ValueError(f"formal PromptPackManifest must not include {banned}")


@dataclass(frozen=True, slots=True)
class FakePromptPackBody:
    """Fake / non-production placeholder text ONLY. Never for formal packs."""

    instruction_placeholder: str
    template_placeholders: Mapping[str, str]
    fake: bool = True
    non_production: bool = True
    formal: bool = False

    def __post_init__(self) -> None:
        if not self.fake or not self.non_production or self.formal:
            raise ValueError("FakePromptPackBody must be fake/non_production and not formal")
        if len(self.instruction_placeholder) > 200:
            raise ValueError("fake placeholder must stay short")
        for text in self.template_placeholders.values():
            if len(text) > 200:
                raise ValueError("fake template placeholder must stay short")


@dataclass(frozen=True, slots=True)
class FakePromptPackManifest:
    """Public-repo Fake pack: refs + optional FakePromptPackBody placeholders."""

    manifest: PromptPackManifest
    body: FakePromptPackBody

    def __post_init__(self) -> None:
        if not self.manifest.non_production:
            raise ValueError("FakePromptPackManifest requires non_production manifest")


def prompt_hash_fingerprint_part(prompt_hash: str) -> str:
    if not prompt_hash.strip():
        raise ValueError("prompt_hash required")
    return f"prompt_pack_hash={prompt_hash.strip()}"


def fake_prompt_pack_manifest(
    *,
    prompt_pack_id: str = "fake.prompt_pack.first_four",
    created_at: datetime | None = None,
) -> FakePromptPackManifest:
    body = FakePromptPackBody(
        instruction_placeholder="[FAKE] do not use in production",
        template_placeholders={
            "book_overview": "[FAKE] overview template",
            "structure_stages": "[FAKE] structure template",
            "chapter_functions": "[FAKE] chapter functions template",
            "storylines": "[FAKE] storylines template",
        },
    )
    manifest = PromptPackManifest(
        prompt_pack_id=prompt_pack_id,
        prompt_pack_version="0.0.1-fake",
        private=False,
        signed=False,
        package_hash="fake-prompt-pack-hash-0001",
        supported_engine_versions=("0.0.1-fake",),
        supported_modules=(
            WholeBookModuleKey.BOOK_OVERVIEW,
            WholeBookModuleKey.STRUCTURE_STAGES,
            WholeBookModuleKey.CHAPTER_FUNCTIONS,
            WholeBookModuleKey.STORYLINES,
        ),
        supported_languages=("zh", "en"),
        output_schema_versions=("1.0.0",),
        instruction_ref="fake://instruction/first_four",
        template_refs={
            "book_overview": "fake://templates/book_overview",
            "structure_stages": "fake://templates/structure_stages",
            "chapter_functions": "fake://templates/chapter_functions",
            "storylines": "fake://templates/storylines",
        },
        example_set_refs=("fake://examples/synthetic_short",),
        evaluation_policy_ref="fake://evaluation/default",
        created_at=created_at or datetime(2026, 7, 23, 0, 0, 0),
        prompt_hash="fake-prompt-content-hash-0001",
        non_production=True,
    )
    return FakePromptPackManifest(manifest=manifest, body=body)
