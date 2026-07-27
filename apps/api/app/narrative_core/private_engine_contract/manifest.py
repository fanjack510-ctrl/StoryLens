"""PrivateWholeBookEngineManifest contract (Phase 2B-P).

No prompt bodies or credentials in manifest fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Sequence

from app.narrative_core.enums import WholeBookAnalysisMode, WholeBookModuleKey
from app.narrative_core.private_engine_contract.errors import (
    PrivateEngineErrorCode,
    private_engine_error,
)

PRIVATE_ENGINE_PROTOCOL_ID = "storylens.private_engine.v1"
PRIVATE_ENGINE_MANIFEST_SCHEMA = "storylens.private_engine.manifest"
PRIVATE_ENGINE_MANIFEST_VERSION = "1.0.0"


class EngineImplementationKind(StrEnum):
    LOCAL_PRIVATE_SIDECAR = "local_private_sidecar"
    LOCAL_PRIVATE_PACKAGE = "local_private_package"
    REMOTE_PRIVATE_SERVICE = "remote_private_service"
    HYBRID_PRIVATE_ENGINE = "hybrid_private_engine"
    MOCK = "mock"


@dataclass(frozen=True, slots=True)
class PrivateWholeBookEngineManifest:
    manifest_schema: str
    manifest_version: str
    engine_id: str
    engine_version: str
    protocol_version: str
    implementation_kind: EngineImplementationKind
    private: bool
    signed: bool
    signature_algorithm: str | None
    package_hash: str
    supported_modes: tuple[WholeBookAnalysisMode, ...]
    supported_modules: tuple[WholeBookModuleKey, ...]
    supported_languages: tuple[str, ...]
    supported_provider_kinds: tuple[str, ...]
    minimum_app_version: str
    maximum_app_version: str | None
    checkpoint_versions: tuple[str, ...]
    result_schema_versions: tuple[str, ...]
    evidence_schema_versions: tuple[str, ...]
    health_capabilities: tuple[str, ...]
    build_id: str
    created_at: datetime
    non_production: bool = False

    def __post_init__(self) -> None:
        if not self.engine_id.strip():
            raise ValueError("engine_id is required")
        if not self.engine_version.strip():
            raise ValueError("engine_version is required")
        if not self.package_hash.strip():
            raise ValueError("package_hash is required")
        # Manifest must never carry prompt/credential fields (attribute guard).
        forbidden_attrs = ("prompt", "prompt_body", "api_key", "credential", "credentials")
        for name in forbidden_attrs:
            if hasattr(self, name):
                raise ValueError(f"manifest must not include {name}")


def _parse_semver_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in version.strip().split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) if parts else (0,)


def app_version_in_range(
    app_version: str,
    *,
    minimum_app_version: str,
    maximum_app_version: str | None,
) -> bool:
    current = _parse_semver_tuple(app_version)
    minimum = _parse_semver_tuple(minimum_app_version)
    if current < minimum:
        return False
    if maximum_app_version is None:
        return True
    maximum = _parse_semver_tuple(maximum_app_version)
    return current <= maximum


def validate_manifest_for_load(
    manifest: PrivateWholeBookEngineManifest,
    *,
    app_version: str,
    production: bool,
    signature_valid: bool,
) -> None:
    """Raise PrivateEngineError-shaped ValueError codes via private_engine_error.

    Callers may catch and map ``.code``. Production must not load mock or degrade
    to an unsigned private package.
    """

    # Production must never degrade to Mock / non-production engines.
    if production and (
        manifest.implementation_kind == EngineImplementationKind.MOCK
        or manifest.non_production
        or not manifest.private
    ):
        raise private_engine_error(
            PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND,
            engine_id=manifest.engine_id,
            detail_code="production_must_not_degrade_to_mock",
        )

    if production and manifest.private and not manifest.signed:
        raise private_engine_error(PrivateEngineErrorCode.PRIVATE_ENGINE_SIGNATURE_INVALID)

    if manifest.signed and not signature_valid:
        raise private_engine_error(PrivateEngineErrorCode.PRIVATE_ENGINE_SIGNATURE_INVALID)

    if manifest.protocol_version != PRIVATE_ENGINE_PROTOCOL_ID:
        raise private_engine_error(PrivateEngineErrorCode.PRIVATE_ENGINE_PROTOCOL_INCOMPATIBLE)

    if not app_version_in_range(
        app_version,
        minimum_app_version=manifest.minimum_app_version,
        maximum_app_version=manifest.maximum_app_version,
    ):
        raise private_engine_error(PrivateEngineErrorCode.PRIVATE_ENGINE_APP_VERSION_INCOMPATIBLE)


def configuration_fingerprint_parts(
    manifest: PrivateWholeBookEngineManifest,
    *,
    prompt_pack_hash: str | None = None,
    quality_profile_key: str | None = None,
) -> tuple[str, ...]:
    """Stable ordered parts for configuration fingerprint (no secrets)."""

    parts = [
        f"engine_id={manifest.engine_id}",
        f"engine_version={manifest.engine_version}",
        f"protocol={manifest.protocol_version}",
        f"package_hash={manifest.package_hash}",
        f"kind={manifest.implementation_kind.value}",
    ]
    if prompt_pack_hash:
        parts.append(f"prompt_pack_hash={prompt_pack_hash}")
    if quality_profile_key:
        parts.append(f"quality_profile={quality_profile_key}")
    return tuple(parts)


def fake_private_manifest(
    *,
    engine_id: str = "fake.signed.private_engine",
    signed: bool = True,
    non_production: bool = True,
    protocol_version: str = PRIVATE_ENGINE_PROTOCOL_ID,
    minimum_app_version: str = "1.0.5",
    maximum_app_version: str | None = None,
    created_at: datetime | None = None,
) -> PrivateWholeBookEngineManifest:
    """Test fixture: Fake Signed Engine manifest (not a real binary)."""

    return PrivateWholeBookEngineManifest(
        manifest_schema=PRIVATE_ENGINE_MANIFEST_SCHEMA,
        manifest_version=PRIVATE_ENGINE_MANIFEST_VERSION,
        engine_id=engine_id,
        engine_version="0.0.1-fake",
        protocol_version=protocol_version,
        implementation_kind=EngineImplementationKind.LOCAL_PRIVATE_PACKAGE,
        private=True,
        signed=signed,
        signature_algorithm="fake-ed25519" if signed else None,
        package_hash="fake-package-hash-0001",
        supported_modes=(
            WholeBookAnalysisMode.NATIVE,
            WholeBookAnalysisMode.ENHANCED,
        ),
        supported_modules=(
            WholeBookModuleKey.BOOK_OVERVIEW,
            WholeBookModuleKey.STRUCTURE_STAGES,
            WholeBookModuleKey.CHAPTER_FUNCTIONS,
            WholeBookModuleKey.STORYLINES,
        ),
        supported_languages=("zh", "en", "mixed"),
        supported_provider_kinds=("fake", "openai_compatible"),
        minimum_app_version=minimum_app_version,
        maximum_app_version=maximum_app_version,
        checkpoint_versions=("1.0.0",),
        result_schema_versions=("1.0.0",),
        evidence_schema_versions=("1.0.0",),
        health_capabilities=("ping", "capabilities"),
        build_id="fake-build-001",
        created_at=created_at or datetime(2026, 7, 23, 0, 0, 0),
        non_production=non_production,
    )


def fake_mock_manifest(
    *,
    engine_id: str = "mock.whole_book_analysis_engine",
    created_at: datetime | None = None,
) -> PrivateWholeBookEngineManifest:
    """Mock engine remains separate: private=false, non_production=true."""

    return PrivateWholeBookEngineManifest(
        manifest_schema=PRIVATE_ENGINE_MANIFEST_SCHEMA,
        manifest_version=PRIVATE_ENGINE_MANIFEST_VERSION,
        engine_id=engine_id,
        engine_version="0.0.1-mock",
        protocol_version=PRIVATE_ENGINE_PROTOCOL_ID,
        implementation_kind=EngineImplementationKind.MOCK,
        private=False,
        signed=False,
        signature_algorithm=None,
        package_hash="mock-package-hash-0001",
        supported_modes=(
            WholeBookAnalysisMode.NATIVE,
            WholeBookAnalysisMode.ENHANCED,
        ),
        supported_modules=tuple(WholeBookModuleKey),
        supported_languages=("zh", "en", "mixed", "auto", "unknown"),
        supported_provider_kinds=("fake",),
        minimum_app_version="1.0.5",
        maximum_app_version=None,
        checkpoint_versions=("1.0.0",),
        result_schema_versions=("1.0.0",),
        evidence_schema_versions=("1.0.0",),
        health_capabilities=("ping",),
        build_id="mock-build-001",
        created_at=created_at or datetime(2026, 7, 23, 0, 0, 0),
        non_production=True,
    )


def supported_modes_values(modes: Sequence[WholeBookAnalysisMode]) -> tuple[str, ...]:
    return tuple(m.value for m in modes)
